#include "stdafx.h"
#include <algorithm>
#include <cctype>
#include <string>
#include <nlohmann/json.hpp>
using namespace std;
constexpr int PROGRESS_BAR_WIDTH = 50;
// Progress bar variables
static atomic<int> g_plyWrittenTasks(0);
static atomic<int> g_totalTasks(0);
static atomic<int> g_computedTasks(0);
static atomic<int> g_inflightTasks(0);
static atomic<int> g_nextSampleIndex(0);
static atomic<int> g_diagWriteCounter(0);
static mutex g_progressMutex;
static size_t g_lastProgressRenderLength = 0;
static time_t g_startTime = 0;
static atomic<bool> g_progressHeartbeatStop(false);

static const unsigned long long kFnvOffset64 = 14695981039346656037ULL;
static const unsigned long long kFnvPrime64 = 1099511628211ULL;

struct SimHyperParams
{
    float material_young = 1.0f;
    float material_poisson = 0.40f;

    std::string ply_path = "./plate.ply";
    std::string annotation_path = "./annotation.json";
    // Optional explicit force list (bare "fx,fy,fz" CSV, no header). When set,
    // these vectors replace random+cone sampling for exact per-frame replay.
    std::string force_list_csv = "";

    int num_vector = 100;
    unsigned int seed = 20260328u;
    float force_x_min = -10.0f;
    float force_x_max = 10.0f;
    float force_y_min = -10.0f;
    float force_y_max = 10.0f;
    float force_z_min = -100.0f;
    float force_z_max = -0.1f;
    float min_angle_deg = 0.0f;
    float max_angle_deg = 45.0f;

    bool use_reuse_tetra_template = true;
    bool use_solver_lu = true;
    bool use_matrix_solver_cache = true;
    bool use_skip_normal_area = true;
    bool use_diag_contact_hash = false;
    bool isolate_output = true;
    int max_objects = 0;
    unsigned int num_threads = 4;
    unsigned int mkl_num_threads = 1;
    int diag_flush_interval = 32;
};

struct ContactSeed
{
    int vertex_index;
    int k_ring;
};

struct AnnotationData
{
    std::vector<int> freeze_vertices;
    std::vector<ContactSeed> contacts;
};

struct SampleTask
{
    std::string sample_id;
    std::unique_ptr<Object> object;
    int contact_i = 0;
    int seed_vertex = 0;
    float fx = 0.0f;
    float fy = 0.0f;
    float fz = 0.0f;
    float norm = 0.0f;
    unsigned long long mesh_hash = 0;
    int selected_count = 0;
    unsigned long long selected_hash = 0;
};

struct CsvRecord
{
    std::string sample_id;
    float fx = 0.0f;
    float fy = 0.0f;
    float fz = 0.0f;
    float norm = 0.0f;
};

struct OutputStats
{
    size_t ply_count = 0;
    size_t csv_count = 0;
    size_t diag_count = 0;
    size_t write_failures = 0;
    std::vector<std::string> ply_ids;
    std::vector<std::string> csv_ids;
    std::vector<std::string> diag_ids;
};

struct MatrixCacheKey
{
    unsigned long long mesh_hash = 0;
    unsigned long long freeze_hash = 0;
    unsigned long long material_hash = 0;
    bool solver_lu = false;
    int matrix_node_count = 0;

    bool Equals(const MatrixCacheKey& other) const
    {
        return mesh_hash == other.mesh_hash &&
            freeze_hash == other.freeze_hash &&
            material_hash == other.material_hash &&
            solver_lu == other.solver_lu &&
            matrix_node_count == other.matrix_node_count;
    }
};

static std::vector<CsvRecord> g_csvRecords;
static mutex g_csvRecordsMutex;
// Write-through journal for force labels: PLYs are useless without their CSV
// rows, and the sorted final CSV is only written at the end of the run.
static FILE* g_csvPartialFp = NULL;
static int g_csvPartialCount = 0;
static mutex g_outputStatsMutex;
static mutex g_diagFileMutex;

void Update_progress();
void Print_progress_bar(bool force = false);

static int GetConsoleWidth()
{
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    if (output == INVALID_HANDLE_VALUE || output == NULL)
    {
        return 120;
    }

    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (!GetConsoleScreenBufferInfo(output, &csbi))
    {
        return 120;
    }

    int width = static_cast<int>(csbi.srWindow.Right - csbi.srWindow.Left + 1);
    return (width > 0) ? width : 120;
}

static std::string BuildProgressBarString(float progress_percent, int width)
{
    if (width < 8) width = 8;
    if (width > PROGRESS_BAR_WIDTH) width = PROGRESS_BAR_WIDTH;

    int pos = static_cast<int>(progress_percent * width / 100.0f);
    if (pos > width) pos = width;
    if (pos < 0) pos = 0;

    std::string bar;
    bar.reserve(static_cast<size_t>(width) + 2);
    bar.push_back('[');
    for (int i = 0; i < width; ++i)
    {
        if (i < pos) bar.push_back('=');
        else if (i == pos && pos < width) bar.push_back('>');
        else bar.push_back(' ');
    }
    bar.push_back(']');
    return bar;
}

static std::string BuildProgressLine(int terminal_width, float compute_progress, int compute_completed, int total,
                                     float ply_progress, int ply_written, int inflight,
                                     double rate_samples_per_sec, const char* eta_str)
{
    const int budget = std::max(24, terminal_width - 1);

    char meta_full[192];
    snprintf(meta_full, sizeof(meta_full),
        " C %.2f%% (%d/%d) | PLY %.2f%% (%d/%d) | InFlight %d | %.2f samp/s%s",
        compute_progress, compute_completed, total,
        ply_progress, ply_written, total,
        inflight,
        rate_samples_per_sec, eta_str);

    char meta_compact[160];
    snprintf(meta_compact, sizeof(meta_compact),
        " C %.1f%% %d/%d | PLY %.1f%% %d/%d | IF %d | %.1f sps%s",
        compute_progress, compute_completed, total,
        ply_progress, ply_written, total,
        inflight,
        rate_samples_per_sec, eta_str);

    char meta_minimal[128];
    snprintf(meta_minimal, sizeof(meta_minimal),
        " C %.0f%% | PLY %.0f%% | IF %d%s",
        compute_progress, ply_progress,
        inflight,
        eta_str);

    char meta_tiny[96];
    snprintf(meta_tiny, sizeof(meta_tiny),
        " C%d/%d P%d/%d IF%d%s",
        compute_completed, total,
        ply_written, total,
        inflight,
        eta_str);

    const char* metas[] = { meta_full, meta_compact, meta_minimal, meta_tiny };
    for (const char* meta : metas)
    {
        std::string meta_str(meta);
        int bar_width = budget - static_cast<int>(meta_str.size()) - 1;
        if (bar_width < 8) continue;

        std::string line = BuildProgressBarString(ply_progress, bar_width);
        line += meta_str;
        if (static_cast<int>(line.size()) <= budget)
        {
            return line;
        }
    }

    std::string fallback(meta_tiny);
    if (static_cast<int>(fallback.size()) > budget)
    {
        fallback = fallback.substr(0, static_cast<size_t>(budget));
    }
    return fallback;
}

static void RenderProgressLineUnlocked(const std::string& line, bool append_newline)
{
    const size_t clear_length = (g_lastProgressRenderLength > line.size()) ? g_lastProgressRenderLength : line.size();
    printf("\r");
    for (size_t i = 0; i < clear_length; ++i) printf(" ");
    if (append_newline)
    {
        printf("\r%s\n", line.c_str());
        g_lastProgressRenderLength = 0;
    }
    else
    {
        printf("\r%s", line.c_str());
        g_lastProgressRenderLength = line.size();
    }
    fflush(stdout);
}

static void PrintFinalizingCsvLine(int buffered_records)
{
    lock_guard<mutex> lock(g_progressMutex);
    const int terminal_width = GetConsoleWidth();
    const int budget = std::max(24, terminal_width - 1);

    char stage[160];
    snprintf(stage, sizeof(stage), " Finalizing CSV... sorting/writing %d buffered records", buffered_records);
    std::string line(stage);
    if (static_cast<int>(line.size()) > budget)
    {
        line = line.substr(0, static_cast<size_t>(budget));
    }

    RenderProgressLineUnlocked(line, true);
}

static void HashBytes64(unsigned long long& hash, const void* data, size_t length)
{
    const unsigned char* bytes = static_cast<const unsigned char*>(data);
    for (size_t i = 0; i < length; ++i)
    {
        hash ^= static_cast<unsigned long long>(bytes[i]);
        hash *= kFnvPrime64;
    }
}

static unsigned long long ComputeMeshHash(const Object* object)
{
    unsigned long long hash = kFnvOffset64;
    for (int i = 0; i < object->nNode; ++i)
    {
        HashBytes64(hash, &object->vertex[i].new_coord.x, sizeof(float));
        HashBytes64(hash, &object->vertex[i].new_coord.y, sizeof(float));
        HashBytes64(hash, &object->vertex[i].new_coord.z, sizeof(float));
    }
    return hash;
}

static bool ParseBoolStrict(const char* raw, bool& value)
{
    if (raw == NULL || raw[0] == '\0') return false;
    if (strcmp(raw, "0") == 0)
    {
        value = false;
        return true;
    }
    if (strcmp(raw, "1") == 0)
    {
        value = true;
        return true;
    }
    return false;
}

static bool ParseFloatStrict(const char* raw, float& value)
{
    if (raw == NULL || raw[0] == '\0') return false;
    char* endPtr = NULL;
    float parsed = strtof(raw, &endPtr);
    // Reject nan/inf: every range check downstream is NaN-transparent.
    if (endPtr != raw && *endPtr == '\0' && std::isfinite(parsed))
    {
        value = parsed;
        return true;
    }
    return false;
}

static bool ParseIntStrict(const char* raw, int& value)
{
    if (raw == NULL || raw[0] == '\0') return false;
    char* endPtr = NULL;
    long parsed = strtol(raw, &endPtr, 10);
    if (endPtr != raw && *endPtr == '\0')
    {
        value = static_cast<int>(parsed);
        return true;
    }
    return false;
}

static bool ParseUIntStrict(const char* raw, unsigned int& value)
{
    if (raw == NULL || raw[0] == '\0') return false;
    char* endPtr = NULL;
    unsigned long parsed = strtoul(raw, &endPtr, 10);
    if (endPtr != raw && *endPtr == '\0')
    {
        value = static_cast<unsigned int>(parsed);
        return true;
    }
    return false;
}

static const char* PickEnv(const char* primary, const char* legacy)
{
    const char* value = getenv(primary);
    if (value != NULL && value[0] != '\0') return value;
    if (legacy != NULL)
    {
        value = getenv(legacy);
        if (value != NULL && value[0] != '\0') return value;
    }
    return NULL;
}

static void LoadBoolParam(bool& target, const char* primary, const char* legacy = NULL)
{
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    bool parsed = target;
    if (ParseBoolStrict(raw, parsed))
    {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n",
           primary, (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadFloatParam(float& target, const char* primary, const char* legacy = NULL)
{
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    float parsed = target;
    if (ParseFloatStrict(raw, parsed))
    {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n",
           primary, (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadIntParam(int& target, const char* primary, const char* legacy = NULL, bool require_positive = false)
{
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    int parsed = target;
    if (ParseIntStrict(raw, parsed) && (!require_positive || parsed > 0))
    {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n",
           primary, (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadUIntParam(unsigned int& target, const char* primary, const char* legacy = NULL)
{
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    unsigned int parsed = target;
    if (ParseUIntStrict(raw, parsed))
    {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n",
           primary, (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadStringParam(std::string& target, const char* primary, const char* legacy = NULL)
{
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    target = raw;
}

static bool LoadAnnotationJSON(const std::string& path, int nNode, AnnotationData& out)
{
    std::ifstream fin(path);
    if (!fin.is_open())
    {
        printf("Error: Cannot open annotation file: %s\n", path.c_str());
        return false;
    }

    nlohmann::json doc;
    out.freeze_vertices.clear();
    out.contacts.clear();

    // One guard for the whole load: parse_error, type_error and out_of_range
    // all derive from json::exception; a typo'd key or wrong-typed field must
    // produce a clean error, not terminate the process.
    try
    {
        fin >> doc;

        if (doc.contains("freeze") && doc["freeze"].is_object() && doc["freeze"].contains("vertices"))
        {
            if (!doc["freeze"]["vertices"].is_array())
            {
                printf("Error: 'freeze.vertices' must be an array in %s\n", path.c_str());
                return false;
            }
            for (const auto& v : doc["freeze"]["vertices"])
            {
                int idx = v.get<int>();
                if (idx < 0 || idx >= nNode)
                {
                    printf("Error: freeze vertex index %d out of range [0, %d)\n", idx, nNode);
                    return false;
                }
                out.freeze_vertices.push_back(idx);
            }
        }

        std::unordered_set<int> freeze_set(out.freeze_vertices.begin(), out.freeze_vertices.end());
        std::unordered_set<int> seed_set;

        if (!doc.contains("contacts") || !doc["contacts"].is_array() || doc["contacts"].empty())
        {
            printf("Error: annotation file must contain a non-empty 'contacts' array\n");
            return false;
        }

        for (const auto& c : doc["contacts"])
        {
            ContactSeed cs;
            cs.vertex_index = c.at("seed").get<int>();
            cs.k_ring = c.at("k_ring").get<int>();

            if (cs.vertex_index < 0 || cs.vertex_index >= nNode)
            {
                printf("Error: contact seed index %d out of range [0, %d)\n", cs.vertex_index, nNode);
                return false;
            }
            if (freeze_set.count(cs.vertex_index))
            {
                printf("Error: contact seed %d is also in freeze list\n", cs.vertex_index);
                return false;
            }
            if (seed_set.count(cs.vertex_index))
            {
                printf("Error: duplicate contact seed index %d\n", cs.vertex_index);
                return false;
            }
            if (cs.k_ring < 1)
            {
                printf("Error: k_ring must be >= 1, got %d for seed %d\n", cs.k_ring, cs.vertex_index);
                return false;
            }

            seed_set.insert(cs.vertex_index);
            out.contacts.push_back(cs);
        }
    }
    catch (const nlohmann::json::exception& e)
    {
        printf("Error: invalid annotation JSON in %s: %s\n", path.c_str(), e.what());
        return false;
    }

    printf("Annotation loaded: %zu freeze vertices, %zu contact seeds\n",
           out.freeze_vertices.size(), out.contacts.size());
    return true;
}

static std::vector<int> SelectKRingNeighbors(int seed, int k, const Vertex* vertices, int nNode,
                                              const std::unordered_set<int>& freeze_set)
{
    std::unordered_set<int> visited;
    visited.insert(seed);
    std::vector<int> frontier;
    frontier.push_back(seed);

    for (int hop = 0; hop < k; ++hop)
    {
        std::vector<int> next_frontier;
        for (int v : frontier)
        {
            for (int u : vertices[v].neighborVertex)
            {
                if (u >= 0 && u < nNode && visited.find(u) == visited.end())
                {
                    visited.insert(u);
                    next_frontier.push_back(u);
                }
            }
        }
        frontier = std::move(next_frontier);
    }

    std::vector<int> result;
    result.reserve(visited.size());
    for (int v : visited)
    {
        if (freeze_set.find(v) == freeze_set.end())
        {
            result.push_back(v);
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

static std::vector<std::vector<int>> PrecomputeContactRegions(
    const AnnotationData& annotation, const Vertex* vertices, int nNode)
{
    std::unordered_set<int> freeze_set(
        annotation.freeze_vertices.begin(), annotation.freeze_vertices.end());

    std::vector<std::vector<int>> regions;
    regions.reserve(annotation.contacts.size());

    for (size_t i = 0; i < annotation.contacts.size(); ++i)
    {
        const ContactSeed& cs = annotation.contacts[i];
        std::vector<int> region = SelectKRingNeighbors(
            cs.vertex_index, cs.k_ring, vertices, nNode, freeze_set);
        printf("  Contact seed %d (k=%d): %zu vertices in region\n",
               cs.vertex_index, cs.k_ring, region.size());
        regions.push_back(std::move(region));
    }

    return regions;
}

static SimHyperParams LoadSimHyperParams()
{
    SimHyperParams params;

    LoadFloatParam(params.material_young, "SIM2LEARN_PARAM_MATERIAL_YOUNG");
    LoadFloatParam(params.material_poisson, "SIM2LEARN_PARAM_MATERIAL_POISSON");

    LoadStringParam(params.ply_path, "SIM2LEARN_PARAM_PLY_PATH");
    LoadStringParam(params.annotation_path, "SIM2LEARN_PARAM_ANNOTATION_PATH");
    LoadStringParam(params.force_list_csv, "SIM2LEARN_PARAM_FORCE_LIST_CSV");

    LoadIntParam(params.num_vector, "SIM2LEARN_PARAM_NUM_VECTOR", NULL, true);
    LoadUIntParam(params.seed, "SIM2LEARN_PARAM_SEED");
    LoadFloatParam(params.force_x_min, "SIM2LEARN_PARAM_FORCE_X_MIN");
    LoadFloatParam(params.force_x_max, "SIM2LEARN_PARAM_FORCE_X_MAX");
    LoadFloatParam(params.force_y_min, "SIM2LEARN_PARAM_FORCE_Y_MIN");
    LoadFloatParam(params.force_y_max, "SIM2LEARN_PARAM_FORCE_Y_MAX");
    LoadFloatParam(params.force_z_min, "SIM2LEARN_PARAM_FORCE_Z_MIN");
    LoadFloatParam(params.force_z_max, "SIM2LEARN_PARAM_FORCE_Z_MAX");
    LoadFloatParam(params.min_angle_deg, "SIM2LEARN_PARAM_MIN_ANGLE_DEG");
    LoadFloatParam(params.max_angle_deg, "SIM2LEARN_PARAM_MAX_ANGLE_DEG");

    LoadBoolParam(params.use_reuse_tetra_template, "SIM2LEARN_PARAM_USE_REUSE_TETRA_TEMPLATE", "SIM2LEARN_REUSE_TETRA_TEMPLATE");
    LoadBoolParam(params.use_solver_lu, "SIM2LEARN_PARAM_USE_SOLVER_LU", "SIM2LEARN_SOLVER_USE_LU");
    if (!params.use_solver_lu)
    {
        printf("Warning: SIM2LEARN_PARAM_USE_SOLVER_LU=0 is no longer supported; the LU direct solver is the only path\n");
        params.use_solver_lu = true;
    }
    LoadBoolParam(params.use_matrix_solver_cache, "SIM2LEARN_PARAM_USE_MATRIX_SOLVER_CACHE", "SIM2LEARN_CACHE_MATRIX_SOLVER");
    LoadBoolParam(params.use_skip_normal_area, "SIM2LEARN_PARAM_SKIP_NORMAL_AREA", "SIM2LEARN_SKIP_NORMAL_AREA");
    LoadBoolParam(params.use_diag_contact_hash, "SIM2LEARN_PARAM_USE_DIAG_CONTACT_HASH", "SIM2LEARN_DIAG_CONTACT_HASH");
    LoadBoolParam(params.isolate_output, "SIM2LEARN_PARAM_ISOLATE_OUTPUT", "SIM2LEARN_ISOLATE_OUTPUT");
    LoadIntParam(params.max_objects, "SIM2LEARN_PARAM_MAX_OBJECTS", "SIM2LEARN_MAX_OBJECTS", true);
    LoadUIntParam(params.mkl_num_threads, "SIM2LEARN_PARAM_MKL_NUM_THREADS", "SIM2LEARN_MKL_NUM_THREADS");
    LoadIntParam(params.diag_flush_interval, "SIM2LEARN_PARAM_DIAG_FLUSH_INTERVAL", NULL, true);
    {
        int parsed_threads = static_cast<int>(params.num_threads);
        LoadIntParam(parsed_threads, "SIM2LEARN_PARAM_NUM_THREADS", "SIM2LEARN_NUM_THREADS", true);
        if (parsed_threads > 0)
        {
            params.num_threads = static_cast<unsigned int>(parsed_threads);
        }
    }

    if (params.num_vector <= 0)
    {
        printf("Warning: invalid SIM2LEARN_PARAM_NUM_VECTOR=%d, fallback to default\n", params.num_vector);
        params.num_vector = 100;
    }
    if (params.material_young <= 0.0f)
    {
        printf("Warning: invalid material young=%.3f, fallback to default\n", params.material_young);
        params.material_young = 1.0f;
    }
    if (params.material_poisson <= -1.0f || params.material_poisson >= 0.5f)
    {
        printf("Warning: invalid material poisson=%.3f, fallback to default\n", params.material_poisson);
        params.material_poisson = 0.40f;
    }
    if (params.min_angle_deg < 0.0f || params.max_angle_deg < params.min_angle_deg)
    {
        printf("Warning: invalid angle range [%.3f, %.3f], fallback to default\n", params.min_angle_deg, params.max_angle_deg);
        params.min_angle_deg = 0.0f;
        params.max_angle_deg = 45.0f;
    }
    if (params.force_x_min > params.force_x_max)
    {
        printf("Warning: invalid force X range [%.3f, %.3f], fallback to default\n", params.force_x_min, params.force_x_max);
        params.force_x_min = -10.0f;
        params.force_x_max = 10.0f;
    }
    if (params.force_y_min > params.force_y_max)
    {
        printf("Warning: invalid force Y range [%.3f, %.3f], fallback to default\n", params.force_y_min, params.force_y_max);
        params.force_y_min = -10.0f;
        params.force_y_max = 10.0f;
    }
    if (params.force_z_min > params.force_z_max)
    {
        printf("Warning: invalid force Z range [%.3f, %.3f], fallback to default\n", params.force_z_min, params.force_z_max);
        params.force_z_min = -100.0f;
        params.force_z_max = -0.1f;
    }
    if (params.diag_flush_interval <= 0)
    {
        printf("Warning: invalid diag_flush_interval=%d, fallback to default\n", params.diag_flush_interval);
        params.diag_flush_interval = 32;
    }

    return params;
}

static unsigned int ConfigureMklThreads(const SimHyperParams& params, unsigned int app_threads, unsigned int hardware_threads, bool& auto_derived)
{
    auto_derived = (params.mkl_num_threads == 0);
    unsigned int derived = params.mkl_num_threads;
    if (derived == 0)
    {
        // Avoid over-subscription: when app is already parallel, keep MKL single-threaded.
        derived = (app_threads > 1) ? 1u : std::max(1u, hardware_threads / 2u);
    }

    if (derived > hardware_threads) derived = hardware_threads;
    if (derived == 0) derived = 1u;

    if (!auto_derived && app_threads * derived > hardware_threads)
    {
        printf("Warning: thread oversubscription: %u app threads x %u MKL threads exceeds %u hardware threads\n",
               app_threads, derived, hardware_threads);
    }

    // Control MKL through its own service API only: the previous omp_set_*
    // calls bound to the compiler's OpenMP runtime (vcomp), not to MKL's
    // libiomp5md, and linking both runtimes is an Intel-documented hazard.
    mkl_set_dynamic(0);
    mkl_set_num_threads(static_cast<int>(derived));
    return derived;
}

static void ResetCsvRecords()
{
    lock_guard<mutex> lock(g_csvRecordsMutex);
    g_csvRecords.clear();
}

static bool AppendCsvRecord(const std::string& sample_id, float fx, float fy, float fz, float norm)
{
    lock_guard<mutex> lock(g_csvRecordsMutex);
    try
    {
        g_csvRecords.push_back({ sample_id, fx, fy, fz, norm });
    }
    catch (...)
    {
        return false;
    }
    if (g_csvPartialFp != NULL)
    {
        fprintf(g_csvPartialFp, "%s,%.9g,%.9g,%.9g,%.9g\n", sample_id.c_str(), fx, fy, fz, norm);
        if ((++g_csvPartialCount % 32) == 0)
        {
            fflush(g_csvPartialFp);
        }
    }
    return true;
}

static std::vector<CsvRecord> BuildSortedCsvRecordsSnapshot()
{
    std::vector<CsvRecord> records;
    {
        lock_guard<mutex> lock(g_csvRecordsMutex);
        records = g_csvRecords;
    }
    std::sort(records.begin(), records.end(), [](const CsvRecord& a, const CsvRecord& b)
    {
        return a.sample_id < b.sample_id;
    });
    return records;
}

static bool WritePlyAndVerify(Object* object, const std::string& ply_path)
{
    if (object == NULL) return false;

    // Write to a temp file and rename into place: a stale PLY from a prior
    // run or a disk-full truncation must never pass as this sample's output.
    const std::string tmp_path = ply_path + ".tmp";
    if (!object->WritePLY(tmp_path))
    {
        DeleteFileA(tmp_path.c_str());
        return false;
    }
    if (!MoveFileExA(tmp_path.c_str(), ply_path.c_str(), MOVEFILE_REPLACE_EXISTING))
    {
        DeleteFileA(tmp_path.c_str());
        return false;
    }

    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExA(ply_path.c_str(), GetFileExInfoStandard, &data))
    {
        return false;
    }
    if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) return false;
    ULONGLONG size = (static_cast<ULONGLONG>(data.nFileSizeHigh) << 32) | data.nFileSizeLow;
    return size > 0;
}

static void ApplyMaterialParams(Object* object, const SimHyperParams& params)
{
    if (object == NULL) return;
    for (int i = 0; i < object->nTetra; ++i)
    {
        object->tetra[i].young = params.material_young;
        object->tetra[i].poisson = params.material_poisson;
    }
}

static MatrixCacheKey BuildMatrixCacheKey(const Object* object, const SimHyperParams& params, unsigned long long mesh_hash)
{
    MatrixCacheKey key;
    if (object == NULL) return key;

    key.mesh_hash = mesh_hash;
    key.solver_lu = params.use_solver_lu;

    unsigned long long freeze_hash = kFnvOffset64;
    int matrix_node_count = 0;
    for (int i = 0; i < object->nNode; ++i)
    {
        if (object->vertex[i].isFreeze)
        {
            unsigned long long freeze_index = static_cast<unsigned long long>(i);
            HashBytes64(freeze_hash, &freeze_index, sizeof(freeze_index));
        }
        else
        {
            ++matrix_node_count;
        }
    }
    key.freeze_hash = freeze_hash;
    key.matrix_node_count = matrix_node_count;

    unsigned long long material_hash = kFnvOffset64;
    HashBytes64(material_hash, &params.material_young, sizeof(params.material_young));
    HashBytes64(material_hash, &params.material_poisson, sizeof(params.material_poisson));
    key.material_hash = material_hash;

    return key;
}

static void ApplyFreezeFromAnnotation(Object* object, const std::vector<int>& freeze_vertices)
{
    for (int idx : freeze_vertices)
    {
        if (idx >= 0 && idx < object->nNode)
        {
            object->vertex[idx].isFreeze = true;
        }
    }
}

static void ApplyContactRegion(Object* object, const std::vector<int>& region,
                                float fx, float fy, float fz,
                                int& selected_count, unsigned long long& selected_hash)
{
    selected_count = 0;
    selected_hash = kFnvOffset64;

    if (region.empty()) return;
    const float inv_n = 1.0f / static_cast<float>(region.size());

    for (int idx : region)
    {
        if (idx >= 0 && idx < object->nNode)
        {
            object->vertex[idx].isSelect = true;
            object->vertex[idx].force = Vector3f(fx, fy, fz) * inv_n;
            unsigned long long selected_index = static_cast<unsigned long long>(idx);
            HashBytes64(selected_hash, &selected_index, sizeof(selected_index));
            ++selected_count;
        }
    }
}

static bool ValidateTetraTemplate(const Object* object)
{
    if (object == NULL) return false;
    if (object->nNode <= 0 || object->nTriangle <= 0 || object->nTetra <= 0) return false;
    if (object->vertex == NULL || object->triangle == NULL || object->tetra == NULL) return false;

    for (int i = 0; i < object->nTetra; ++i)
    {
        if (object->tetra[i].Ke != NULL || object->tetra[i].Se != NULL)
        {
            return false;
        }
    }

    return true;
}

static bool CloneTetraTemplate(const Object& template_object, Object* work_object)
{
    if (work_object == NULL) return false;
    if (!ValidateTetraTemplate(&template_object)) return false;

    work_object->isDispVertex = template_object.isDispVertex;
    work_object->isDispLine = template_object.isDispLine;
    work_object->isDispSurface = template_object.isDispSurface;
    work_object->isDispVolume = template_object.isDispVolume;
    work_object->type = template_object.type;
    work_object->m_count = template_object.m_count;
    work_object->center = template_object.center;
    work_object->min = template_object.min;
    work_object->max = template_object.max;
    work_object->area = template_object.area;
    work_object->volume = template_object.volume;
    work_object->omega = template_object.omega;
    work_object->lambda = template_object.lambda;
    work_object->flag = template_object.flag;

    work_object->InitVertex(template_object.nNode);
    for (int i = 0; i < template_object.nNode; ++i)
    {
        work_object->vertex[i] = template_object.vertex[i];
        work_object->vertex[i].isFreeze = false;
        work_object->vertex[i].isSelect = false;
        work_object->vertex[i].force.Init();
    }

    if (template_object.nLine > 0)
    {
        work_object->InitLine(template_object.nLine);
        for (int i = 0; i < template_object.nLine; ++i)
        {
            work_object->line[i] = template_object.line[i];
        }
    }

    if (template_object.nTriangle > 0)
    {
        work_object->InitTriangle(template_object.nTriangle);
        for (int i = 0; i < template_object.nTriangle; ++i)
        {
            work_object->triangle[i] = template_object.triangle[i];
        }
    }

    if (template_object.nTetra > 0)
    {
        work_object->InitTetrahedron(template_object.nTetra);
        for (int i = 0; i < template_object.nTetra; ++i)
        {
            for (int j = 0; j < 4; ++j)
            {
                work_object->tetra[i].set[j] = template_object.tetra[i].set[j];
            }
            work_object->tetra[i].young = template_object.tetra[i].young;
            work_object->tetra[i].poisson = template_object.tetra[i].poisson;
            work_object->tetra[i].volume = template_object.tetra[i].volume;
            work_object->tetra[i].stress = template_object.tetra[i].stress;
            work_object->tetra[i].Ke = 0;
            work_object->tetra[i].Se = 0;
        }
    }

    return true;
}

void ComputeTetrahedralMesh(Surface *in, Object *out, const SimHyperParams& params)
{

	// Tetrahedral mesh generation
	int nNode = in->nNode;
	int nTriangle = in->nTriangle;

	out->InitVertex(nNode);
	out->InitTriangle(nTriangle);

	for (int i = 0; i < nNode; i++)
	{
		out->vertex[i].new_coord = in->vertex[i].new_coord;
		out->vertex[i].coord = in->vertex[i].new_coord;
		out->vertex[i].isFreeze = in->vertex[i].isFreeze;
		out->vertex[i].isSelect = in->vertex[i].isSelect;
	}

	for (int i = 0; i < nTriangle; i++)
	{
		out->triangle[i].set[0] = in->triangle[i].set[0];
		out->triangle[i].set[1] = in->triangle[i].set[1];
		out->triangle[i].set[2] = in->triangle[i].set[2];
	}

	// Compute the quality of the tetrahedral mesh
	out->ComputeQualityTetrahedralMesh("pY");

	for (int i = 0; i < out->nNode; i++)
	{
		out->vertex[i].coord = out->vertex[i].new_coord;
		out->vertex[i].isFreeze = false;
		out->vertex[i].isSelect = false;
		out->vertex[i].force.Init();
	}

	if (!params.use_skip_normal_area)
	{
		out->ComputeNormal();
		out->ComputeArea();
	}
}

static void RecordOutputFailure(OutputStats* stats)
{
    if (stats == NULL)
    {
        return;
    }
    lock_guard<mutex> lock(g_outputStatsMutex);
    ++stats->write_failures;
}

static bool WriteSampleOutput(SampleTask& task, const std::string& dir_path, FILE* diag_fp, const SimHyperParams& params, OutputStats* stats)
{
    if (!task.object)
    {
        RecordOutputFailure(stats);
        return false;
    }

    std::string ply_path = dir_path + "/" + task.sample_id + ".ply";
    bool ply_ok = WritePlyAndVerify(task.object.get(), ply_path);
    if (!ply_ok)
    {
        RecordOutputFailure(stats);
        printf("Error: WritePLY failed for %s\n", task.sample_id.c_str());
        DeleteFileA(ply_path.c_str());
        return false;
    }

    if (!AppendCsvRecord(task.sample_id, task.fx, task.fy, task.fz, task.norm))
    {
        RecordOutputFailure(stats);
        printf("Error: CSV buffer append failed for %s\n", task.sample_id.c_str());
        DeleteFileA(ply_path.c_str());
        return false;
    }

    bool diag_ok = true;
    if (params.use_diag_contact_hash && diag_fp != NULL)
    {
        lock_guard<mutex> lock(g_diagFileMutex);
        diag_ok = (fprintf(diag_fp, "%s,%d,%d,%d,%016llx,%d,%016llx\n",
            task.sample_id.c_str(), task.contact_i, task.seed_vertex,
            task.object->nNode, task.mesh_hash, task.selected_count, task.selected_hash) >= 0);
        if (diag_ok && params.diag_flush_interval > 0)
        {
            int diag_count = g_diagWriteCounter.fetch_add(1) + 1;
            if (diag_count % params.diag_flush_interval == 0)
            {
                diag_ok = (fflush(diag_fp) == 0);
            }
        }
    }
    if (!diag_ok)
    {
        RecordOutputFailure(stats);
        printf("Error: diag write failed for %s\n", task.sample_id.c_str());
        DeleteFileA(ply_path.c_str());
        return false;
    }

    {
        lock_guard<mutex> lock(g_outputStatsMutex);
        ++stats->ply_count;
        stats->ply_ids.push_back(task.sample_id);
        if (params.use_diag_contact_hash && diag_fp != NULL)
        {
            ++stats->diag_count;
            stats->diag_ids.push_back(task.sample_id);
        }
    }

    Update_progress();
    return true;
}

static bool WriteFinalSortedCsv(const char* csv_filename, OutputStats* stats)
{
    if (csv_filename == NULL || stats == NULL)
    {
        return false;
    }

    std::vector<CsvRecord> records = BuildSortedCsvRecordsSnapshot();
    FILE* fp = fopen(csv_filename, "w");
    if (fp == NULL)
    {
        printf("Error: Cannot open file %s\n\n", csv_filename);
        return false;
    }

    bool ok = (fprintf(fp, "SampleID,force_x,force_y,force_z,force_norm\n") >= 0);
    for (size_t i = 0; ok && i < records.size(); ++i)
    {
        const CsvRecord& record = records[i];
        if (fprintf(fp, "%s,%.3f,%.3f,%.3f,%.3f\n",
            record.sample_id.c_str(), record.fx, record.fy, record.fz, record.norm) < 0)
        {
            printf("Error: final CSV write failed for %s\n", record.sample_id.c_str());
            ok = false;
        }
    }
    if (ok && fflush(fp) != 0)
    {
        printf("Error: final CSV flush failed\n");
        ok = false;
    }
    if (fclose(fp) != 0)
    {
        printf("Error: final CSV close failed\n");
        ok = false;
    }
    if (!ok)
    {
        return false;
    }

    stats->csv_count = records.size();
    stats->csv_ids.clear();
    stats->csv_ids.reserve(records.size());
    for (size_t i = 0; i < records.size(); ++i)
    {
        stats->csv_ids.push_back(records[i].sample_id);
    }

    return true;
}

static bool HaveMatchingSampleIds(const std::vector<std::string>& left, const std::vector<std::string>& right)
{
    if (left.size() != right.size())
    {
        return false;
    }
    std::vector<std::string> left_sorted = left;
    std::vector<std::string> right_sorted = right;
    std::sort(left_sorted.begin(), left_sorted.end());
    std::sort(right_sorted.begin(), right_sorted.end());
    return left_sorted == right_sorted;
}

static bool ValidateOutputConsistency(const OutputStats& output_stats, bool use_diag_contact_hash, int expected_samples, int computed_samples)
{
    bool output_ok = (output_stats.write_failures == 0 &&
        output_stats.ply_count == output_stats.csv_count &&
        HaveMatchingSampleIds(output_stats.ply_ids, output_stats.csv_ids));
    if (use_diag_contact_hash)
    {
        output_ok = output_ok && (output_stats.diag_count == output_stats.ply_count) && (output_stats.diag_ids == output_stats.ply_ids);
    }
    if (output_stats.ply_count != static_cast<size_t>(expected_samples) || computed_samples != expected_samples)
    {
        output_ok = false;
    }
    return output_ok;
}

void Generate_run_string(char *run_str, int max_len)
{
	// obtain the current time
	time_t current_time = time(NULL);
	if (current_time == -1)
	{
		snprintf(run_str, max_len, "run_unknown");
		return;
	}

	// transfer the time to local time
	struct tm *local_time = localtime(&current_time);
	const unsigned long pid = static_cast<unsigned long>(GetCurrentProcessId());
	if (local_time == NULL)
	{
		snprintf(run_str, max_len, "run_unknown_p%lu", pid);
		return;
	}

	// Format run timestamp as YY_MM_DD_HHMMSS plus the PID: two runs started
	// within the same second must not share an output directory.
	char ts[32] = { 0 };
	if (strftime(ts, sizeof(ts), "%y_%m_%d_%H%M%S", local_time) == 0)
	{
		snprintf(run_str, max_len, "run_unknown_p%lu", pid);
		return;
	}
	snprintf(run_str, max_len, "%s_p%lu", ts, pid);
}
static void BuildEtaString(char* eta_str, size_t eta_len, int completed, int total, double rate_samples_per_sec)
{
	eta_str[0] = '\0';
	if (completed <= 0 || total <= 0 || rate_samples_per_sec <= 1e-9)
	{
		snprintf(eta_str, eta_len, " ETA: calculating...");
		return;
	}

	int remaining = total - completed;
	if (remaining <= 0)
	{
		snprintf(eta_str, eta_len, " ETA: <1s");
		return;
	}

	long eta_seconds = static_cast<long>(remaining / rate_samples_per_sec);
	if (eta_seconds > 3600)
	{
		snprintf(eta_str, eta_len, " ETA: %ldh%02ldm", eta_seconds / 3600, (eta_seconds % 3600) / 60);
	}
	else if (eta_seconds > 60)
	{
		snprintf(eta_str, eta_len, " ETA: %ldm%02lds", eta_seconds / 60, eta_seconds % 60);
	}
	else if (eta_seconds > 0)
	{
		snprintf(eta_str, eta_len, " ETA: %lds", eta_seconds);
	}
	else
	{
		snprintf(eta_str, eta_len, " ETA: <1s");
	}
}

void Print_progress_bar(bool force)
{
	lock_guard<mutex> lock(g_progressMutex);

	const int total = g_totalTasks.load();
	if (total <= 0) return;

	int ply_written = g_plyWrittenTasks.load();
	int compute_completed = g_computedTasks.load();
	int inflight = g_inflightTasks.load();
	if (ply_written > total) ply_written = total;
	if (compute_completed > total) compute_completed = total;
	if (inflight < 0) inflight = 0;

	float ply_progress = (static_cast<float>(ply_written) / total) * 100.0f;
	float compute_progress = (static_cast<float>(compute_completed) / total) * 100.0f;

	static time_t last_tick = 0;
	static int last_completed = 0;
	static double ewma_rate = 0.0;

	time_t now = time(NULL);
	if (last_tick == 0)
	{
		last_tick = now;
		last_completed = ply_written;
	}
	else
	{
		double dt = difftime(now, last_tick);
		if (dt >= 1.0)
		{
			int delta_completed = ply_written - last_completed;
			double instant_rate = (delta_completed > 0) ? (static_cast<double>(delta_completed) / dt) : 0.0;
			if (ewma_rate <= 1e-9) ewma_rate = instant_rate;
			else ewma_rate = 0.7 * ewma_rate + 0.3 * instant_rate;
			last_tick = now;
			last_completed = ply_written;
		}
	}

	double elapsed = (g_startTime > 0) ? difftime(now, g_startTime) : 0.0;
	double fallback_rate = (elapsed > 0.0 && ply_written > 0) ? (static_cast<double>(ply_written) / elapsed) : 0.0;
	double rate_samples_per_sec = (ewma_rate > 1e-9) ? ewma_rate : fallback_rate;

	char eta_str[64];
	BuildEtaString(eta_str, sizeof(eta_str), ply_written, total, rate_samples_per_sec);

	if (!force)
	{
		static time_t last_render = 0;
		if (difftime(now, last_render) < 1.0 && ply_written < total)
		{
			return;
		}
		last_render = now;
	}

	const int terminal_width = GetConsoleWidth();
	const std::string line = BuildProgressLine(terminal_width, compute_progress, compute_completed, total,
		ply_progress, ply_written, inflight, rate_samples_per_sec, eta_str);
	RenderProgressLineUnlocked(line, false);
}

static void ProgressHeartbeatProc()
{
	while (!g_progressHeartbeatStop.load())
	{
		this_thread::sleep_for(chrono::seconds(1));
		if (g_progressHeartbeatStop.load()) break;
		Print_progress_bar(false);
	}
}

void Update_progress()
{
	int completed = g_plyWrittenTasks.fetch_add(1) + 1;
	int total = g_totalTasks.load();

	int update_interval;
	if (total <= 500) update_interval = 20;
	else if (total <= 2000) update_interval = 10;
	else if (total <= 10000) update_interval = 5;
	else update_interval = 2;

	if (completed % update_interval == 0 || completed == total)
	{
		if (total > 0)
		{
			Print_progress_bar(completed == total);
		}
	}
}

float RandomFloat(float min, float max)
{
	return min + (float)rand() / RAND_MAX * (max - min);
}

float ComputeForceEuclidean(float x, float y, float z)
{
	return sqrtf(x * x + y * y + z * z);
}

float AngleWithZAxis(float x, float y, float z)
{
	float mag = ComputeForceEuclidean(x, y, z);
	float cosTheta = (-z) / mag; // the ratio of the dot product to the magnitude
	return acosf(cosTheta);		 // return the value in radian (use acosf to deal with float type)
}

// Parse an explicit force list ("fx,fy,fz" per line, no header) into the force
// vector list, in file order. On any failure (missing/empty/unparseable file)
// returns nullptr so the caller can fail fast: a digital-twin replay must never
// silently fall back to random sampling. On success sets params.num_vector to
// the number of parsed rows so processObjects iterates exactly those frames.
static std::unique_ptr<std::vector<std::array<float, 4>>> generateVectorsFromCsv(SimHyperParams& params)
{
	std::ifstream fin(params.force_list_csv);
	if (!fin.is_open())
	{
		fprintf(stderr, "Error: Cannot open SIM2LEARN_PARAM_FORCE_LIST_CSV: %s\n", params.force_list_csv.c_str());
		return nullptr;
	}

	auto vectors = std::make_unique<std::vector<std::array<float, 4>>>();

	std::string line;
	int line_no = 0;
	while (std::getline(fin, line))
	{
		++line_no;
		// Skip fully-blank lines (e.g. a trailing newline) but reject malformed content.
		bool only_ws = true;
		for (char ch : line)
		{
			if (!isspace(static_cast<unsigned char>(ch))) { only_ws = false; break; }
		}
		if (only_ws) continue;

		float x = 0.0f, y = 0.0f, z = 0.0f;
		char extra = 0;
		// Require exactly three comma-separated floats and nothing trailing.
		if (sscanf(line.c_str(), " %f , %f , %f %c", &x, &y, &z, &extra) != 3)
		{
			fprintf(stderr, "Error: Malformed force row at %s:%d: '%s' (expected 'fx,fy,fz')\n",
			        params.force_list_csv.c_str(), line_no, line.c_str());
			return nullptr;
		}
		// Real sensor exports contain nan dropouts; one non-finite frame
		// silently poisons the whole displacement field of its sample.
		if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z))
		{
			fprintf(stderr, "Error: non-finite force at %s:%d: '%s'\n",
			        params.force_list_csv.c_str(), line_no, line.c_str());
			return nullptr;
		}

		float norm = ComputeForceEuclidean(x, y, z);
		array<float, 4> temp = {x, y, z, norm};
		vectors->push_back(temp);
	}

	if (vectors->empty())
	{
		fprintf(stderr, "Error: SIM2LEARN_PARAM_FORCE_LIST_CSV is empty: %s\n", params.force_list_csv.c_str());
		return nullptr;
	}

	const int csv_count = static_cast<int>(vectors->size());
	if (getenv("SIM2LEARN_PARAM_NUM_VECTOR") != NULL && params.num_vector != csv_count)
	{
		printf("Warning: SIM2LEARN_PARAM_NUM_VECTOR=%d ignored, force list CSV provides %d rows\n",
		       params.num_vector, csv_count);
	}
	params.num_vector = csv_count;
	printf("Force list CSV: %s (%d explicit vectors; random+cone sampling bypassed)\n",
	       params.force_list_csv.c_str(), params.num_vector);
	return vectors;
}

std::unique_ptr<std::vector<std::array<float, 4>>> generateVectors(SimHyperParams& params)
{
	// Explicit replay mode: when a force list CSV is provided, use it verbatim and
	// ignore the FORCE_*_MIN/MAX ranges and MIN/MAX_ANGLE_DEG cone entirely.
	if (!params.force_list_csv.empty())
	{
		return generateVectorsFromCsv(params);
	}

	// this ANGLE need literature endoresement
	const float MIN_ANGLE_RAD = params.min_angle_deg * M_PI / 180.0f;
	const float MAX_ANGLE_RAD = params.max_angle_deg * M_PI / 180.0f;

	auto vectors = std::make_unique<std::vector<std::array<float, 4>>>();
	vectors->reserve(params.num_vector);

	int count = 0;
	// Rejection sampling must be bounded: an angle window that does not
	// intersect the force box would otherwise spin forever before any output.
	long long attempts = 0;
	const long long max_attempts = 10000LL * static_cast<long long>(params.num_vector);
	while (count < params.num_vector)
	{
		if (++attempts > max_attempts)
		{
			fprintf(stderr, "Error: force sampling rejected %lld candidates for %d accepted; "
			        "angle window [%.1f, %.1f] deg likely incompatible with the force ranges\n",
			        attempts, count, params.min_angle_deg, params.max_angle_deg);
			return nullptr;
		}

		float x = RandomFloat(params.force_x_min, params.force_x_max);
		float y = RandomFloat(params.force_y_min, params.force_y_max);
		float z = RandomFloat(params.force_z_min, params.force_z_max); // make sure the z component is negative

		float angleRad = AngleWithZAxis(x, y, z);
		if (MIN_ANGLE_RAD <= angleRad && angleRad <= MAX_ANGLE_RAD)
		{
			// store the vector
			float norm = ComputeForceEuclidean(x, y, z);
			array<float, 4> temp = {x, y, z, norm};
			vectors->push_back(temp);
			count++;
		}
	}
	return vectors;
}

void CreateSampleID(char *sampleID, int seed_vertex, int vec_i)
{
	sprintf(sampleID, "deformed_s%04d_v%04d", seed_vertex, vec_i);
}

void processObjects(int total_objects, const std::string& dir_path, FILE* diag_fp, OutputStats* output_stats, Surface* surface,
                    const AnnotationData& annotation,
                    const std::vector<std::vector<int>>& contact_regions,
                    const std::vector<std::array<float, 4>>& force_vectors,
                    const SimHyperParams& params, const Object* tetra_template,
                    const Object* matrix_template, const MatrixCacheKey* matrix_cache_key)
{
    while (true)
    {
        int k = g_nextSampleIndex.fetch_add(1);
        if (k >= total_objects)
        {
            break;
        }

        auto object = std::make_unique<Object>();
        bool used_template_path = false;
        if (params.use_reuse_tetra_template && tetra_template != NULL)
        {
            used_template_path = CloneTetraTemplate(*tetra_template, object.get());
        }

        if (!used_template_path)
        {
            ComputeTetrahedralMesh(surface, object.get(), params);
        }
        ApplyMaterialParams(object.get(), params);
        unsigned long long mesh_hash = ComputeMeshHash(object.get());

        int contact_i = k / params.num_vector;
        int vec_i = k % params.num_vector;

        int seed_vertex = annotation.contacts[contact_i].vertex_index;
        const std::vector<int>& region = contact_regions[contact_i];

        const auto& force_vector = force_vectors[vec_i];
        float fx = force_vector[0];
        float fy = force_vector[1];
        float fz = force_vector[2];
        float norm = force_vector[3];

        char sampleID[100] = "";
        CreateSampleID(sampleID, seed_vertex, vec_i);

        int selected_count = 0;
        unsigned long long selected_hash = kFnvOffset64;
        ApplyContactRegion(object.get(), region, fx, fy, fz, selected_count, selected_hash);
        ApplyFreezeFromAnnotation(object.get(), annotation.freeze_vertices);

        bool used_matrix_cache = false;
        if (params.use_matrix_solver_cache && matrix_template != NULL && matrix_cache_key != NULL)
        {
            MatrixCacheKey sample_key = BuildMatrixCacheKey(object.get(), params, mesh_hash);
            if (sample_key.Equals(*matrix_cache_key))
            {
                used_matrix_cache = object->CloneMatrixStateFrom(*matrix_template);
                if (!used_matrix_cache)
                {
                    printf("Warning: matrix cache clone failed for %s, fallback to ComputeMatrixK\n", sampleID);
                }
            }
        }
        bool solve_ok = true;
        if (!used_matrix_cache)
        {
            solve_ok = object->ComputeMatrixK();
            object->ReleaseAssemblyScratch();
            if (!solve_ok)
            {
                printf("Error: stiffness build failed for %s, sample skipped\n", sampleID);
            }
        }

        if (solve_ok && !object->Deform())
        {
            solve_ok = false;
            printf("Error: deformation solve failed for %s, sample skipped\n", sampleID);
        }
        object->ReleaseSolverState();
        if (used_matrix_cache)
        {
            object->ReleaseAssemblyScratch();
        }

        SampleTask task;
        task.sample_id = sampleID;
        task.object = std::move(object);
        task.contact_i = contact_i;
        task.seed_vertex = seed_vertex;
        task.fx = fx;
        task.fy = fy;
        task.fz = fz;
        task.norm = norm;
        task.mesh_hash = mesh_hash;
        task.selected_count = selected_count;
        task.selected_hash = selected_hash;
        g_computedTasks.fetch_add(1);
        g_inflightTasks.fetch_add(1);
        if (solve_ok)
        {
            WriteSampleOutput(task, dir_path, diag_fp, params, output_stats);
        }
        else
        {
            // A failed solve must never produce a PLY/CSV pair; count it as
            // a failure so the final consistency check reports it.
            RecordOutputFailure(output_stats);
        }
        g_inflightTasks.fetch_sub(1);
    }
}

int main(int argc, char* argv[])
{
	SimHyperParams params = LoadSimHyperParams();

	printf("\nPLY path: %s\n", params.ply_path.c_str());
	printf("Annotation path: %s\n", params.annotation_path.c_str());

	srand(params.seed);
	printf("Random seed: %u\n", params.seed);
	printf("Contact hash diagnostics: %s\n", params.use_diag_contact_hash ? "ON" : "OFF");
	printf("Tetra template reuse: %s\n", params.use_reuse_tetra_template ? "ON" : "OFF");
	printf("Solver: LU direct (factor + DGETRS)\n");
	printf("Matrix solver cache: %s\n", params.use_matrix_solver_cache ? "ON" : "OFF");
	printf("Skip normal/area: %s\n", params.use_skip_normal_area ? "ON" : "OFF");
	printf("Output isolation: %s\n", params.isolate_output ? "ON" : "OFF");
	printf("Diag flush interval: %d\n", params.diag_flush_interval);

	auto force_vectors = generateVectors(params);
	if (!force_vectors)
	{
		printf("Failed to generate contact force vectors\n");
		return 1;
	}

	auto s = std::make_unique<Surface>();
	s->ReadPLY(params.ply_path);
	if (s->nNode == 0 || s->nTriangle == 0)
	{
		printf("Error: Cannot read PLY file: %s\n", params.ply_path.c_str());
		return 1;
	}
	printf("PLY file read successfully: %d vertices, %d triangles\n\n", s->nNode, s->nTriangle);

	AnnotationData annotation;
	if (!LoadAnnotationJSON(params.annotation_path, s->nNode, annotation))
	{
		printf("Error: Failed to load annotation file\n");
		return 1;
	}

	printf("Precomputing contact regions...\n");
	std::vector<std::vector<int>> contact_regions =
		PrecomputeContactRegions(annotation, s->vertex.data(), s->nNode);
	printf("Contact regions ready: %zu seeds\n\n", contact_regions.size());

	char dir_path[200];
	char run_str[100];
	Generate_run_string(run_str, sizeof(run_str));
	if (params.isolate_output)
	{
		sprintf(dir_path, "./DeformedSample_ComplexObject_%s", run_str);
	}
	else
	{
		sprintf(dir_path, "./DeformedSample_ComplexObject");
	}

	if (_mkdir(dir_path) == 0)
	{
		printf("Directory created: %s\n", dir_path);
	}
	else if (errno == EEXIST)
	{
		if (params.isolate_output)
		{
			// The isolated directory name embeds timestamp+PID; if it already
			// exists something is reusing this run's identity. Refuse to mix.
			printf("Error: isolated output directory already exists: %s\n", dir_path);
			return 1;
		}
		printf("Warning: reusing existing directory %s; stale *.ply from earlier runs may mix into this dataset\n", dir_path);
	}
	else
	{
		printf("Error creating directory: %s\n", dir_path);
		return 1;
	}

	char csv_filename[200];
	sprintf(csv_filename, "%s/SampleID_log%s.csv", dir_path, run_str);

	// Open the label journal: it preserves every force row a crash would
	// otherwise lose, and is removed once the sorted final CSV is on disk.
	char csv_partial_filename[220];
	snprintf(csv_partial_filename, sizeof(csv_partial_filename), "%s.partial", csv_filename);
	g_csvPartialFp = fopen(csv_partial_filename, "w");
	if (g_csvPartialFp == NULL)
	{
		printf("Warning: cannot open CSV journal %s; labels stay in memory until the end of the run\n", csv_partial_filename);
	}

	FILE* diag_fp = NULL;
	char diag_filename[200];
	if (params.use_diag_contact_hash)
	{
		sprintf(diag_filename, "%s/DiagContactHash.csv", dir_path);
		diag_fp = fopen(diag_filename, "w");
		if (diag_fp == NULL)
		{
			printf("Error: Cannot open file %s\n\n", diag_filename);
			return 1;
		}
		fprintf(diag_fp, "sample_id,contact_i,seed_vertex,n_node,mesh_hash,selected_count,selected_hash\n");
	}

	std::unique_ptr<Object> tetra_template;
	if (params.use_reuse_tetra_template)
	{
		tetra_template = std::make_unique<Object>();
		ComputeTetrahedralMesh(s.get(), tetra_template.get(), params);
		ApplyMaterialParams(tetra_template.get(), params);
		if (!ValidateTetraTemplate(tetra_template.get()))
		{
			printf("Warning: tetra template build failed, fallback to per-sample tetrahedralization\n");
			tetra_template.reset();
		}
		else
		{
			printf("Tetra template ready: YES\n");
		}
	}
	else
	{
		printf("Tetra template ready: NO\n");
	}

	std::unique_ptr<Object> matrix_template;
	MatrixCacheKey matrix_cache_key;
	bool matrix_cache_ready = false;
	if (params.use_matrix_solver_cache)
	{
		matrix_template = std::make_unique<Object>();
		bool matrix_source_ready = false;
		if (tetra_template != NULL)
		{
			matrix_source_ready = CloneTetraTemplate(*tetra_template, matrix_template.get());
		}
		else
		{
			ComputeTetrahedralMesh(s.get(), matrix_template.get(), params);
			matrix_source_ready = true;
		}

		if (matrix_source_ready)
		{
			ApplyMaterialParams(matrix_template.get(), params);
			ApplyFreezeFromAnnotation(matrix_template.get(), annotation.freeze_vertices);
			unsigned long long matrix_mesh_hash = ComputeMeshHash(matrix_template.get());
			matrix_cache_key = BuildMatrixCacheKey(matrix_template.get(), params, matrix_mesh_hash);
			bool matrix_ok = matrix_template->ComputeMatrixK();
			matrix_template->ReleaseAssemblyScratch();
			if (!matrix_ok)
			{
				// Same mesh and material for every sample: if the template
				// factorization fails, every per-sample solve fails too.
				printf("Error: stiffness factorization failed on the template mesh, aborting run\n");
				return 1;
			}
			matrix_cache_ready = true;
			printf("Matrix solver cache ready: YES\n");
		}
		else
		{
			params.use_matrix_solver_cache = false;
			matrix_template.reset();
			printf("Warning: matrix solver cache build failed, fallback to per-sample ComputeMatrixK\n");
		}
	}
	else
	{
		printf("Matrix solver cache ready: NO\n");
	}

	int numObjects = static_cast<int>(annotation.contacts.size() * static_cast<size_t>(params.num_vector));
	bool limit_objects = false;
	if (params.max_objects > 0 && params.max_objects < numObjects)
	{
		numObjects = params.max_objects;
		limit_objects = true;
	}
	printf("Number of samples: %d\n", numObjects);
	printf("Max objects limit: %s\n\n", limit_objects ? "ON" : "OFF");

	unsigned int totalThreads = thread::hardware_concurrency();
	if (totalThreads == 0)
	{
		totalThreads = 1;
	}

	unsigned int numThreads = params.num_threads > 0 ? params.num_threads : std::max(1u, totalThreads / 16);
	if (numThreads > totalThreads) numThreads = totalThreads;
	if (numThreads == 0) numThreads = 1;

	bool mkl_auto_derived = false;
	unsigned int mklThreads = ConfigureMklThreads(params, numThreads, totalThreads, mkl_auto_derived);

	printf("Using %u threads (out of %u available, %u reserved for system)\n", numThreads, totalThreads, totalThreads - numThreads);
	printf("MKL threads: %u (%s)\n", mklThreads, mkl_auto_derived ? "auto-derived" : "from SIM2LEARN_PARAM_MKL_NUM_THREADS");
	printf("Dispatch mode: dynamic (atomic next-sample)\n");

	g_totalTasks.store(numObjects);
	g_plyWrittenTasks.store(0);
	g_computedTasks.store(0);
	g_inflightTasks.store(0);
	g_nextSampleIndex.store(0);
	g_diagWriteCounter.store(0);
	g_startTime = time(NULL);
	ResetCsvRecords();
	g_progressHeartbeatStop.store(false);

	OutputStats output_stats;
	std::thread progress_thread(ProgressHeartbeatProc);

	printf("Starting processing...\n");

	std::vector<thread> threads;
	for (unsigned int t = 0; t < numThreads; t++)
	{
		threads.emplace_back(processObjects, numObjects, std::string(dir_path), diag_fp, &output_stats, s.get(),
			std::cref(annotation), std::cref(contact_regions),
			std::cref(*force_vectors), std::cref(params), tetra_template.get(),
			matrix_cache_ready ? matrix_template.get() : NULL,
			matrix_cache_ready ? &matrix_cache_key : NULL);
	}

	for (auto& thread : threads)
	{
		thread.join();
	}

	g_progressHeartbeatStop.store(true);
	if (progress_thread.joinable())
	{
		progress_thread.join();
	}
	Print_progress_bar(true);

	if (params.use_diag_contact_hash && diag_fp != NULL && fflush(diag_fp) != 0)
	{
		++output_stats.write_failures;
		printf("Error: final diag flush failed\n");
	}

	if (diag_fp != NULL)
	{
		fclose(diag_fp);
		diag_fp = NULL;
	}
	PrintFinalizingCsvLine(g_computedTasks.load());
	bool final_csv_ok = WriteFinalSortedCsv(csv_filename, &output_stats);
	if (!final_csv_ok)
	{
		++output_stats.write_failures;
	}
	{
		lock_guard<mutex> lock(g_csvRecordsMutex);
		if (g_csvPartialFp != NULL)
		{
			fclose(g_csvPartialFp);
			g_csvPartialFp = NULL;
		}
	}
	if (final_csv_ok)
	{
		DeleteFileA(csv_partial_filename);
	}
	else
	{
		printf("Note: CSV journal kept at %s\n", csv_partial_filename);
	}

	bool output_ok = ValidateOutputConsistency(output_stats, params.use_diag_contact_hash, numObjects, g_computedTasks.load());

	if (!output_ok)
	{
		printf("Error: output consistency check failed (ply=%zu, csv=%zu, diag=%zu, failures=%zu)\n",
			output_stats.ply_count, output_stats.csv_count, output_stats.diag_count, output_stats.write_failures);
		return 1;
	}

	printf("\nProcessing completed successfully.\n");
	printf("Final counters: C=%d, PLY=%d, InFlight=%d\n",
		g_computedTasks.load(), g_plyWrittenTasks.load(), g_inflightTasks.load());
	printf("Generated %d samples in directory: %s\n", numObjects, dir_path);

	return 0;
}
