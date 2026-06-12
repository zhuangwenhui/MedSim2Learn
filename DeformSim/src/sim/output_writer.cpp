// Sample output writing: verified PLYs, the CSV label journal and final
// sorted CSV, optional contact-hash diagnostics, and output consistency
// validation.
#include "sim/output_writer.h"

#include <algorithm>
#include <atomic>
#include <ctime>
#include <mutex>
#include <windows.h>

#include "sim/progress.h"

using namespace std;

static std::vector<CsvRecord> g_csvRecords;
static mutex g_csvRecordsMutex;
// Write-through journal for force labels: PLYs are useless without their CSV
// rows, and the sorted final CSV is only written at the end of the run.
static FILE* g_csvPartialFp = NULL;
static int g_csvPartialCount = 0;
static mutex g_outputStatsMutex;
static mutex g_diagFileMutex;
static atomic<int> g_diagWriteCounter(0);

void Generate_run_string(char* run_str, int max_len) {
    // obtain the current time
    time_t current_time = time(NULL);
    if (current_time == -1) {
        snprintf(run_str, max_len, "run_unknown");
        return;
    }

    // transfer the time to local time
    struct tm* local_time = localtime(&current_time);
    const unsigned long pid = static_cast<unsigned long>(GetCurrentProcessId());
    if (local_time == NULL) {
        snprintf(run_str, max_len, "run_unknown_p%lu", pid);
        return;
    }

    // Format run timestamp as YY_MM_DD_HHMMSS plus the PID: two runs started
    // within the same second must not share an output directory.
    char ts[32] = {0};
    if (strftime(ts, sizeof(ts), "%y_%m_%d_%H%M%S", local_time) == 0) {
        snprintf(run_str, max_len, "run_unknown_p%lu", pid);
        return;
    }
    snprintf(run_str, max_len, "%s_p%lu", ts, pid);
}

void ResetCsvRecords() {
    lock_guard<mutex> lock(g_csvRecordsMutex);
    g_csvRecords.clear();
}

void ResetDiagWriteCounter() {
    g_diagWriteCounter.store(0);
}

bool OpenCsvJournal(const char* path) {
    g_csvPartialFp = fopen(path, "w");
    return g_csvPartialFp != NULL;
}

void CloseCsvJournal() {
    lock_guard<mutex> lock(g_csvRecordsMutex);
    if (g_csvPartialFp != NULL) {
        fclose(g_csvPartialFp);
        g_csvPartialFp = NULL;
    }
}

bool AppendCsvRecord(const std::string& sample_id, float fx, float fy, float fz, float norm) {
    lock_guard<mutex> lock(g_csvRecordsMutex);
    try {
        g_csvRecords.push_back({sample_id, fx, fy, fz, norm});
    } catch (...) {
        return false;
    }
    if (g_csvPartialFp != NULL) {
        fprintf(g_csvPartialFp, "%s,%.9g,%.9g,%.9g,%.9g\n", sample_id.c_str(), fx, fy, fz, norm);
        if ((++g_csvPartialCount % 32) == 0) {
            fflush(g_csvPartialFp);
        }
    }
    return true;
}

static std::vector<CsvRecord> BuildSortedCsvRecordsSnapshot() {
    std::vector<CsvRecord> records;
    {
        lock_guard<mutex> lock(g_csvRecordsMutex);
        records = g_csvRecords;
    }
    std::sort(records.begin(), records.end(),
              [](const CsvRecord& a, const CsvRecord& b) { return a.sample_id < b.sample_id; });
    return records;
}

bool WritePlyAndVerify(Object* object, const std::string& ply_path) {
    if (object == NULL) return false;

    // Write to a temp file and rename into place: a stale PLY from a prior
    // run or a disk-full truncation must never pass as this sample's output.
    const std::string tmp_path = ply_path + ".tmp";
    if (!object->WritePLY(tmp_path)) {
        DeleteFileA(tmp_path.c_str());
        return false;
    }
    if (!MoveFileExA(tmp_path.c_str(), ply_path.c_str(), MOVEFILE_REPLACE_EXISTING)) {
        DeleteFileA(tmp_path.c_str());
        return false;
    }

    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExA(ply_path.c_str(), GetFileExInfoStandard, &data)) {
        return false;
    }
    if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) return false;
    ULONGLONG size = (static_cast<ULONGLONG>(data.nFileSizeHigh) << 32) | data.nFileSizeLow;
    return size > 0;
}

void RecordOutputFailure(OutputStats* stats) {
    if (stats == NULL) {
        return;
    }
    lock_guard<mutex> lock(g_outputStatsMutex);
    ++stats->write_failures;
}

bool WriteSampleOutput(SampleTask& task, const std::string& dir_path, FILE* diag_fp,
                       const SimHyperParams& params, OutputStats* stats) {
    if (!task.object) {
        RecordOutputFailure(stats);
        return false;
    }

    std::string ply_path = dir_path + "/" + task.sample_id + ".ply";
    bool ply_ok = WritePlyAndVerify(task.object.get(), ply_path);
    if (!ply_ok) {
        RecordOutputFailure(stats);
        printf("Error: WritePLY failed for %s\n", task.sample_id.c_str());
        DeleteFileA(ply_path.c_str());
        return false;
    }

    if (!AppendCsvRecord(task.sample_id, task.fx, task.fy, task.fz, task.norm)) {
        RecordOutputFailure(stats);
        printf("Error: CSV buffer append failed for %s\n", task.sample_id.c_str());
        DeleteFileA(ply_path.c_str());
        return false;
    }

    bool diag_ok = true;
    if (params.use_diag_contact_hash && diag_fp != NULL) {
        lock_guard<mutex> lock(g_diagFileMutex);
        diag_ok = (fprintf(diag_fp, "%s,%d,%d,%d,%016llx,%d,%016llx\n", task.sample_id.c_str(),
                           task.contact_i, task.seed_vertex, task.object->nNode, task.mesh_hash,
                           task.selected_count, task.selected_hash) >= 0);
        if (diag_ok && params.diag_flush_interval > 0) {
            int diag_count = g_diagWriteCounter.fetch_add(1) + 1;
            if (diag_count % params.diag_flush_interval == 0) {
                diag_ok = (fflush(diag_fp) == 0);
            }
        }
    }
    if (!diag_ok) {
        RecordOutputFailure(stats);
        printf("Error: diag write failed for %s\n", task.sample_id.c_str());
        DeleteFileA(ply_path.c_str());
        return false;
    }

    {
        lock_guard<mutex> lock(g_outputStatsMutex);
        ++stats->ply_count;
        stats->ply_ids.push_back(task.sample_id);
        if (params.use_diag_contact_hash && diag_fp != NULL) {
            ++stats->diag_count;
            stats->diag_ids.push_back(task.sample_id);
        }
    }

    Update_progress();
    return true;
}

bool WriteFinalSortedCsv(const char* csv_filename, OutputStats* stats) {
    if (csv_filename == NULL || stats == NULL) {
        return false;
    }

    std::vector<CsvRecord> records = BuildSortedCsvRecordsSnapshot();
    FILE* fp = fopen(csv_filename, "w");
    if (fp == NULL) {
        printf("Error: Cannot open file %s\n\n", csv_filename);
        return false;
    }

    bool ok = (fprintf(fp, "SampleID,force_x,force_y,force_z,force_norm\n") >= 0);
    for (size_t i = 0; ok && i < records.size(); ++i) {
        const CsvRecord& record = records[i];
        // %.9g round-trips float exactly, so feeding this CSV back through
        // SIM2LEARN_PARAM_FORCE_LIST_CSV reproduces the run bit-exactly.
        if (fprintf(fp, "%s,%.9g,%.9g,%.9g,%.9g\n", record.sample_id.c_str(), record.fx, record.fy,
                    record.fz, record.norm) < 0) {
            printf("Error: final CSV write failed for %s\n", record.sample_id.c_str());
            ok = false;
        }
    }
    if (ok && fflush(fp) != 0) {
        printf("Error: final CSV flush failed\n");
        ok = false;
    }
    if (fclose(fp) != 0) {
        printf("Error: final CSV close failed\n");
        ok = false;
    }
    if (!ok) {
        return false;
    }

    stats->csv_count = records.size();
    stats->csv_ids.clear();
    stats->csv_ids.reserve(records.size());
    for (size_t i = 0; i < records.size(); ++i) {
        stats->csv_ids.push_back(records[i].sample_id);
    }

    return true;
}

static bool HaveMatchingSampleIds(const std::vector<std::string>& left,
                                  const std::vector<std::string>& right) {
    if (left.size() != right.size()) {
        return false;
    }
    std::vector<std::string> left_sorted = left;
    std::vector<std::string> right_sorted = right;
    std::sort(left_sorted.begin(), left_sorted.end());
    std::sort(right_sorted.begin(), right_sorted.end());
    return left_sorted == right_sorted;
}

bool ValidateOutputConsistency(const OutputStats& output_stats, bool use_diag_contact_hash,
                               int expected_samples, int computed_samples) {
    bool output_ok =
        (output_stats.write_failures == 0 && output_stats.ply_count == output_stats.csv_count &&
         HaveMatchingSampleIds(output_stats.ply_ids, output_stats.csv_ids));
    if (use_diag_contact_hash) {
        output_ok = output_ok && (output_stats.diag_count == output_stats.ply_count) &&
                    (output_stats.diag_ids == output_stats.ply_ids);
    }
    if (output_stats.ply_count != static_cast<size_t>(expected_samples) ||
        computed_samples != expected_samples) {
        output_ok = false;
    }
    return output_ok;
}
