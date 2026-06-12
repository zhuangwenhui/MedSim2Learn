// Contact-force vector generation: random cone sampling or exact CSV replay.
#include "sim/force_sampling.h"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <random>
#include <string>

using namespace std;

// Force-sampling RNG: a dedicated engine is immune to the vendored tetgen
// reseeding the CRT PRNG (tetgen calls srand internally) and provides full
// float resolution instead of the 15-bit RAND_MAX lattice of MSVC rand().
// Note: sequences differ from historical rand()-based runs at equal seeds.
static std::mt19937 g_forceRng;

void SeedForceRng(unsigned int seed) {
    g_forceRng.seed(seed);
}

float RandomFloat(float min, float max) {
    std::uniform_real_distribution<float> dist(min, max);
    return dist(g_forceRng);
}

float ComputeForceEuclidean(float x, float y, float z) {
    return sqrtf(x * x + y * y + z * z);
}

float AngleWithZAxis(float x, float y, float z) {
    float mag = ComputeForceEuclidean(x, y, z);
    float cosTheta = (-z) / mag;  // the ratio of the dot product to the magnitude
    return acosf(cosTheta);  // return the value in radian (use acosf to deal with float type)
}

// Parse an explicit force list ("fx,fy,fz" per line, no header) into the force
// vector list, in file order. On any failure (missing/empty/unparseable file)
// returns nullptr so the caller can fail fast: a digital-twin replay must never
// silently fall back to random sampling. On success sets params.num_vector to
// the number of parsed rows so the worker loop iterates exactly those frames.
static std::unique_ptr<std::vector<std::array<float, 4>>>
generateVectorsFromCsv(SimHyperParams& params) {
    std::ifstream fin(params.force_list_csv);
    if (!fin.is_open()) {
        fprintf(stderr, "Error: Cannot open SIM2LEARN_PARAM_FORCE_LIST_CSV: %s\n",
                params.force_list_csv.c_str());
        return nullptr;
    }

    auto vectors = std::make_unique<std::vector<std::array<float, 4>>>();

    std::string line;
    int line_no = 0;
    while (std::getline(fin, line)) {
        ++line_no;
        // Skip fully-blank lines (e.g. a trailing newline) but reject malformed content.
        bool only_ws = true;
        for (char ch : line) {
            if (!isspace(static_cast<unsigned char>(ch))) {
                only_ws = false;
                break;
            }
        }
        if (only_ws) continue;

        float x = 0.0f, y = 0.0f, z = 0.0f;
        char extra = 0;
        // Require exactly three comma-separated floats and nothing trailing.
        if (sscanf(line.c_str(), " %f , %f , %f %c", &x, &y, &z, &extra) != 3) {
            fprintf(stderr, "Error: Malformed force row at %s:%d: '%s' (expected 'fx,fy,fz')\n",
                    params.force_list_csv.c_str(), line_no, line.c_str());
            return nullptr;
        }
        // Real sensor exports contain nan dropouts; one non-finite frame
        // silently poisons the whole displacement field of its sample.
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
            fprintf(stderr, "Error: non-finite force at %s:%d: '%s'\n",
                    params.force_list_csv.c_str(), line_no, line.c_str());
            return nullptr;
        }

        float norm = ComputeForceEuclidean(x, y, z);
        array<float, 4> temp = {x, y, z, norm};
        vectors->push_back(temp);
    }

    if (vectors->empty()) {
        fprintf(stderr, "Error: SIM2LEARN_PARAM_FORCE_LIST_CSV is empty: %s\n",
                params.force_list_csv.c_str());
        return nullptr;
    }

    const int csv_count = static_cast<int>(vectors->size());
    if (getenv("SIM2LEARN_PARAM_NUM_VECTOR") != NULL && params.num_vector != csv_count) {
        printf("Warning: SIM2LEARN_PARAM_NUM_VECTOR=%d ignored, force list CSV provides %d rows\n",
               params.num_vector, csv_count);
    }
    params.num_vector = csv_count;
    printf("Force list CSV: %s (%d explicit vectors; random+cone sampling bypassed)\n",
           params.force_list_csv.c_str(), params.num_vector);
    return vectors;
}

std::unique_ptr<std::vector<std::array<float, 4>>> generateVectors(SimHyperParams& params) {
    // Explicit replay mode: when a force list CSV is provided, use it verbatim and
    // ignore the FORCE_*_MIN/MAX ranges and MIN/MAX_ANGLE_DEG cone entirely.
    if (!params.force_list_csv.empty()) {
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
    while (count < params.num_vector) {
        if (++attempts > max_attempts) {
            fprintf(stderr,
                    "Error: force sampling rejected %lld candidates for %d accepted; "
                    "angle window [%.1f, %.1f] deg likely incompatible with the force ranges\n",
                    attempts, count, params.min_angle_deg, params.max_angle_deg);
            return nullptr;
        }

        float x = RandomFloat(params.force_x_min, params.force_x_max);
        float y = RandomFloat(params.force_y_min, params.force_y_max);
        float z = RandomFloat(params.force_z_min,
                              params.force_z_max);  // make sure the z component is negative

        float angleRad = AngleWithZAxis(x, y, z);
        if (MIN_ANGLE_RAD <= angleRad && angleRad <= MAX_ANGLE_RAD) {
            // store the vector
            float norm = ComputeForceEuclidean(x, y, z);
            array<float, 4> temp = {x, y, z, norm};
            vectors->push_back(temp);
            count++;
        }
    }
    return vectors;
}

void CreateSampleID(char* sampleID, int seed_vertex, int vec_i) {
    sprintf(sampleID, "deformed_s%04d_v%04d", seed_vertex, vec_i);
}
