// DeformSim sample-generation entry point. Wires the orchestration modules:
// load env params -> sample/replay force vectors -> read surface PLY ->
// load annotation -> precompute contact regions -> build tetra/matrix
// templates -> run the worker pool -> finalize CSV and validate outputs.
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <direct.h>
#include <memory>
#include <thread>
#include <vector>
#include <windows.h>

#include "bmgl.h"
#include "sim/annotation.h"
#include "sim/force_sampling.h"
#include "sim/hyper_params.h"
#include "sim/output_writer.h"
#include "sim/progress.h"
#include "sim/sample_pipeline.h"
#include "sim/worker.h"

using namespace std;

int main(int argc, char* argv[]) {
    SimHyperParams params = LoadSimHyperParams();

    printf("\nPLY path: %s\n", params.ply_path.c_str());
    printf("Annotation path: %s\n", params.annotation_path.c_str());

    SeedForceRng(params.seed);
    printf("Random seed: %u\n", params.seed);
    printf("Contact hash diagnostics: %s\n", params.use_diag_contact_hash ? "ON" : "OFF");
    printf("Tetra template reuse: %s\n", params.use_reuse_tetra_template ? "ON" : "OFF");
    printf("Solver: LU direct (factor + DGETRS)\n");
    printf("Matrix solver cache: %s\n", params.use_matrix_solver_cache ? "ON" : "OFF");
    printf("Skip normal/area: %s\n", params.use_skip_normal_area ? "ON" : "OFF");
    printf("Output isolation: %s\n", params.isolate_output ? "ON" : "OFF");
    printf("Diag flush interval: %d\n", params.diag_flush_interval);

    auto force_vectors = generateVectors(params);
    if (!force_vectors) {
        printf("Failed to generate contact force vectors\n");
        return 1;
    }

    auto s = std::make_unique<Surface>();
    s->ReadPLY(params.ply_path);
    if (s->nNode == 0 || s->nTriangle == 0) {
        printf("Error: Cannot read PLY file: %s\n", params.ply_path.c_str());
        return 1;
    }
    printf("PLY file read successfully: %d vertices, %d triangles\n\n", s->nNode, s->nTriangle);

    AnnotationData annotation;
    if (!LoadAnnotationJSON(params.annotation_path, s->nNode, annotation)) {
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
    if (params.isolate_output) {
        sprintf(dir_path, "./DeformedSample_ComplexObject_%s", run_str);
    } else {
        sprintf(dir_path, "./DeformedSample_ComplexObject");
    }

    if (_mkdir(dir_path) == 0) {
        printf("Directory created: %s\n", dir_path);
    } else if (errno == EEXIST) {
        if (params.isolate_output) {
            // The isolated directory name embeds timestamp+PID; if it already
            // exists something is reusing this run's identity. Refuse to mix.
            printf("Error: isolated output directory already exists: %s\n", dir_path);
            return 1;
        }
        printf("Warning: reusing existing directory %s; stale *.ply from earlier runs may mix into "
               "this dataset\n",
               dir_path);
    } else {
        printf("Error creating directory: %s\n", dir_path);
        return 1;
    }

    char csv_filename[200];
    sprintf(csv_filename, "%s/SampleID_log%s.csv", dir_path, run_str);

    // Open the label journal: it preserves every force row a crash would
    // otherwise lose, and is removed once the sorted final CSV is on disk.
    char csv_partial_filename[220];
    snprintf(csv_partial_filename, sizeof(csv_partial_filename), "%s.partial", csv_filename);
    if (!OpenCsvJournal(csv_partial_filename)) {
        printf(
            "Warning: cannot open CSV journal %s; labels stay in memory until the end of the run\n",
            csv_partial_filename);
    }

    FILE* diag_fp = NULL;
    char diag_filename[200];
    if (params.use_diag_contact_hash) {
        sprintf(diag_filename, "%s/DiagContactHash.csv", dir_path);
        diag_fp = fopen(diag_filename, "w");
        if (diag_fp == NULL) {
            printf("Error: Cannot open file %s\n\n", diag_filename);
            return 1;
        }
        fprintf(diag_fp,
                "sample_id,contact_i,seed_vertex,n_node,mesh_hash,selected_count,selected_hash\n");
    }

    std::unique_ptr<Object> tetra_template;
    if (params.use_reuse_tetra_template) {
        tetra_template = std::make_unique<Object>();
        ComputeTetrahedralMesh(s.get(), tetra_template.get(), params);
        ApplyMaterialParams(tetra_template.get(), params);
        if (!ValidateTetraTemplate(tetra_template.get())) {
            printf("Warning: tetra template build failed, fallback to per-sample "
                   "tetrahedralization\n");
            tetra_template.reset();
        } else {
            printf("Tetra template ready: YES\n");
        }
    } else {
        printf("Tetra template ready: NO\n");
    }

    std::unique_ptr<Object> matrix_template;
    MatrixCacheKey matrix_cache_key;
    bool matrix_cache_ready = false;
    if (params.use_matrix_solver_cache) {
        matrix_template = std::make_unique<Object>();
        bool matrix_source_ready = false;
        if (tetra_template != NULL) {
            matrix_source_ready = CloneTetraTemplate(*tetra_template, matrix_template.get());
        } else {
            ComputeTetrahedralMesh(s.get(), matrix_template.get(), params);
            matrix_source_ready = true;
        }

        if (matrix_source_ready) {
            ApplyMaterialParams(matrix_template.get(), params);
            ApplyFreezeFromAnnotation(matrix_template.get(), annotation.freeze_vertices);
            unsigned long long matrix_mesh_hash = ComputeMeshHash(matrix_template.get());
            matrix_cache_key = BuildMatrixCacheKey(matrix_template.get(), params, matrix_mesh_hash);
            bool matrix_ok = matrix_template->ComputeMatrixK();
            matrix_template->ReleaseAssemblyScratch();
            if (!matrix_ok) {
                // Same mesh and material for every sample: if the template
                // factorization fails, every per-sample solve fails too.
                printf(
                    "Error: stiffness factorization failed on the template mesh, aborting run\n");
                return 1;
            }
            matrix_cache_ready = true;
            printf("Matrix solver cache ready: YES\n");
        } else {
            params.use_matrix_solver_cache = false;
            matrix_template.reset();
            printf("Warning: matrix solver cache build failed, fallback to per-sample "
                   "ComputeMatrixK\n");
        }
    } else {
        printf("Matrix solver cache ready: NO\n");
    }

    int numObjects =
        static_cast<int>(annotation.contacts.size() * static_cast<size_t>(params.num_vector));
    bool limit_objects = false;
    if (params.max_objects > 0 && params.max_objects < numObjects) {
        numObjects = params.max_objects;
        limit_objects = true;
    }
    printf("Number of samples: %d\n", numObjects);
    printf("Max objects limit: %s\n\n", limit_objects ? "ON" : "OFF");

    unsigned int totalThreads = thread::hardware_concurrency();
    if (totalThreads == 0) {
        totalThreads = 1;
    }

    unsigned int numThreads =
        params.num_threads > 0 ? params.num_threads : std::max(1u, totalThreads / 16);
    if (numThreads > totalThreads) numThreads = totalThreads;
    if (numThreads == 0) numThreads = 1;

    bool mkl_auto_derived = false;
    unsigned int mklThreads =
        ConfigureMklThreads(params, numThreads, totalThreads, mkl_auto_derived);

    printf("Using %u threads (out of %u available, %u reserved for system)\n", numThreads,
           totalThreads, totalThreads - numThreads);
    printf("MKL threads: %u (%s)\n", mklThreads,
           mkl_auto_derived ? "auto-derived" : "from SIM2LEARN_PARAM_MKL_NUM_THREADS");
    printf("Dispatch mode: dynamic (atomic next-sample)\n");

    InitProgressTracking(numObjects);
    ResetDiagWriteCounter();
    ResetCsvRecords();

    OutputStats output_stats;
    StartProgressHeartbeat();

    printf("Starting processing...\n");

    RunSampleWorkers(numThreads, numObjects, std::string(dir_path), diag_fp, &output_stats, s.get(),
                     annotation, contact_regions, *force_vectors, params, tetra_template.get(),
                     matrix_cache_ready ? matrix_template.get() : NULL,
                     matrix_cache_ready ? &matrix_cache_key : NULL);

    StopProgressHeartbeat();
    Print_progress_bar(true);

    if (params.use_diag_contact_hash && diag_fp != NULL && fflush(diag_fp) != 0) {
        ++output_stats.write_failures;
        printf("Error: final diag flush failed\n");
    }

    if (diag_fp != NULL) {
        fclose(diag_fp);
        diag_fp = NULL;
    }
    PrintFinalizingCsvLine(GetComputedTaskCount());
    bool final_csv_ok = WriteFinalSortedCsv(csv_filename, &output_stats);
    if (!final_csv_ok) {
        ++output_stats.write_failures;
    }
    CloseCsvJournal();
    if (final_csv_ok) {
        DeleteFileA(csv_partial_filename);
    } else {
        printf("Note: CSV journal kept at %s\n", csv_partial_filename);
    }

    bool output_ok = ValidateOutputConsistency(output_stats, params.use_diag_contact_hash,
                                               numObjects, GetComputedTaskCount());

    if (!output_ok) {
        printf(
            "Error: output consistency check failed (ply=%zu, csv=%zu, diag=%zu, failures=%zu)\n",
            output_stats.ply_count, output_stats.csv_count, output_stats.diag_count,
            output_stats.write_failures);
        return 1;
    }

    printf("\nProcessing completed successfully.\n");
    printf("Final counters: C=%d, PLY=%d, InFlight=%d\n", GetComputedTaskCount(),
           GetPlyWrittenTaskCount(), GetInflightTaskCount());
    printf("Generated %d samples in directory: %s\n", numObjects, dir_path);

    return 0;
}
