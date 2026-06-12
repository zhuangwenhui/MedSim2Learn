// The per-sample worker loop and its thread pool.
#include "sim/worker.h"

#include <atomic>
#include <functional>
#include <memory>
#include <thread>

#include "sim/force_sampling.h"
#include "sim/progress.h"

using namespace std;

static atomic<int> g_nextSampleIndex(0);

static void processObjects(int total_objects, const std::string& dir_path, FILE* diag_fp,
                           OutputStats* output_stats, Surface* surface,
                           const AnnotationData& annotation,
                           const std::vector<std::vector<int>>& contact_regions,
                           const std::vector<std::array<float, 4>>& force_vectors,
                           const SimHyperParams& params, const Object* tetra_template,
                           const Object* matrix_template, const MatrixCacheKey* matrix_cache_key) {
    while (true) {
        int k = g_nextSampleIndex.fetch_add(1);
        if (k >= total_objects) {
            break;
        }

        auto object = std::make_unique<Object>();
        bool used_template_path = false;
        if (params.use_reuse_tetra_template && tetra_template != NULL) {
            used_template_path = CloneTetraTemplate(*tetra_template, object.get());
        }

        if (!used_template_path) {
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
        if (params.use_matrix_solver_cache && matrix_template != NULL && matrix_cache_key != NULL) {
            MatrixCacheKey sample_key = BuildMatrixCacheKey(object.get(), params, mesh_hash);
            if (sample_key.Equals(*matrix_cache_key)) {
                used_matrix_cache = object->CloneMatrixStateFrom(*matrix_template);
                if (!used_matrix_cache) {
                    printf(
                        "Warning: matrix cache clone failed for %s, fallback to ComputeMatrixK\n",
                        sampleID);
                }
            }
        }
        bool solve_ok = true;
        if (!used_matrix_cache) {
            solve_ok = object->ComputeMatrixK();
            object->ReleaseAssemblyScratch();
            if (!solve_ok) {
                printf("Error: stiffness build failed for %s, sample skipped\n", sampleID);
            }
        }

        if (solve_ok && !object->Deform()) {
            solve_ok = false;
            printf("Error: deformation solve failed for %s, sample skipped\n", sampleID);
        }
        object->ReleaseSolverState();
        if (used_matrix_cache) {
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
        MarkSampleComputed();
        MarkSampleInflight();
        if (solve_ok) {
            WriteSampleOutput(task, dir_path, diag_fp, params, output_stats);
        } else {
            // A failed solve must never produce a PLY/CSV pair; count it as
            // a failure so the final consistency check reports it.
            RecordOutputFailure(output_stats);
        }
        MarkSampleRetired();
    }
}

void RunSampleWorkers(unsigned int num_threads, int total_objects, const std::string& dir_path,
                      FILE* diag_fp, OutputStats* output_stats, Surface* surface,
                      const AnnotationData& annotation,
                      const std::vector<std::vector<int>>& contact_regions,
                      const std::vector<std::array<float, 4>>& force_vectors,
                      const SimHyperParams& params, const Object* tetra_template,
                      const Object* matrix_template, const MatrixCacheKey* matrix_cache_key) {
    g_nextSampleIndex.store(0);

    std::vector<thread> threads;
    for (unsigned int t = 0; t < num_threads; t++) {
        threads.emplace_back(processObjects, total_objects, dir_path, diag_fp, output_stats,
                             surface, std::cref(annotation), std::cref(contact_regions),
                             std::cref(force_vectors), std::cref(params), tetra_template,
                             matrix_template, matrix_cache_key);
    }

    for (auto& thread : threads) {
        thread.join();
    }
}
