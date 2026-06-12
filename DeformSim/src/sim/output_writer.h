#pragma once

#include <cstdio>
#include <memory>
#include <string>
#include <vector>

#include "bmgl.h"
#include "sim/hyper_params.h"

// One computed sample on its way to disk: the deformed object plus the
// metadata that goes into the CSV label row and the diag line.
struct SampleTask {
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

struct CsvRecord {
    std::string sample_id;
    float fx = 0.0f;
    float fy = 0.0f;
    float fz = 0.0f;
    float norm = 0.0f;
};

struct OutputStats {
    size_t ply_count = 0;
    size_t csv_count = 0;
    size_t diag_count = 0;
    size_t write_failures = 0;
    std::vector<std::string> ply_ids;
    std::vector<std::string> csv_ids;
    std::vector<std::string> diag_ids;
};

// Formats the run identity "YY_MM_DD_HHMMSS_p<pid>"; two runs started within
// the same second must not share an output directory.
void Generate_run_string(char* run_str, int max_len);

void ResetCsvRecords();
void ResetDiagWriteCounter();

// Opens the write-through label journal ("<final csv>.partial"). Returns
// false when the file cannot be opened; labels then stay in memory only.
bool OpenCsvJournal(const char* path);
void CloseCsvJournal();

// Buffers one label row and mirrors it into the journal (flushed every 32).
bool AppendCsvRecord(const std::string& sample_id, float fx, float fy, float fz, float norm);

// Writes the PLY via temp+rename and verifies a non-empty file exists.
bool WritePlyAndVerify(Object* object, const std::string& ply_path);

void RecordOutputFailure(OutputStats* stats);

// Writes the sample's PLY, label row, and optional diag line; on any failure
// removes the PLY so no orphaned artifact survives.
bool WriteSampleOutput(SampleTask& task, const std::string& dir_path, FILE* diag_fp,
                       const SimHyperParams& params, OutputStats* stats);

// Sorts the buffered labels by sample id and writes the final CSV.
bool WriteFinalSortedCsv(const char* csv_filename, OutputStats* stats);

// Cross-checks PLY/CSV/diag counts and id sets against the expected total.
bool ValidateOutputConsistency(const OutputStats& output_stats, bool use_diag_contact_hash,
                               int expected_samples, int computed_samples);
