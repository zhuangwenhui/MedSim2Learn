#pragma once

#include <cstddef>
#include <vector>

#include "mvrmesh/backends/tetgen/tetgen_evaluator.h"  // for DeformSimPressureResult
#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct RobustPipelineOptions {
    // Stage 2 tunables
    double sharp_edge_dihedral_degrees = 60.0;
    double target_edge_length          = 0.0;   // 0 -> auto = mean edge length of stage 1 output
    int    remesh_iterations           = 3;

    // Stage 3 tunables
    std::size_t max_dense_kl_bytes     = 4ull * 1024 * 1024 * 1024;  // 4 GiB default
    double      simplify_safety_margin = 0.9;   // not CLI-exposed in v1
};

struct RepairStepReport {
    std::size_t input_vertex_count         = 0;
    std::size_t input_face_count           = 0;
    std::size_t output_vertex_count        = 0;
    std::size_t output_face_count          = 0;
    std::size_t removed_duplicate_vertices = 0;
    std::size_t removed_degenerate_faces   = 0;
    std::size_t holes_filled               = 0;
    bool        oriented_successfully      = false;
};

struct ProtectedRemeshStepReport {
    std::size_t input_vertex_count       = 0;
    std::size_t input_face_count         = 0;
    std::size_t output_vertex_count      = 0;
    std::size_t output_face_count        = 0;
    std::size_t sharp_edges_detected     = 0;
    double      target_edge_length_used  = 0.0;
    int         remesh_iterations_used   = 0;
};

struct SimplifyToBudgetStepReport {
    std::size_t input_vertex_count    = 0;
    std::size_t input_face_count      = 0;
    std::size_t output_vertex_count   = 0;
    std::size_t output_face_count     = 0;
    bool        skipped_within_budget = false;
    std::size_t budget_bytes          = 0;
    std::size_t bytes_initial         = 0;
    std::size_t bytes_final           = 0;
    std::size_t target_vertex_count   = 0;
};

struct RobustPipelineResult {
    std::vector<Vec3>          vertices;
    std::vector<Face>          faces;
    RepairStepReport           repair_report;
    ProtectedRemeshStepReport  remesh_report;
    SimplifyToBudgetStepReport simplify_report;
    DeformSimPressureResult    final_pressure_result;
};

RobustPipelineResult run_cgal_robust_pipeline(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const RobustPipelineOptions& options);

namespace detail {

struct RepairStepIO {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    RepairStepReport  report;
};

struct ProtectedRemeshStepIO {
    std::vector<Vec3>         vertices;
    std::vector<Face>         faces;
    ProtectedRemeshStepReport report;
};

struct SimplifyToBudgetStepIO {
    std::vector<Vec3>          vertices;
    std::vector<Face>          faces;
    SimplifyToBudgetStepReport report;
    DeformSimPressureResult    final_pressure_result;
};

RepairStepIO repair_polygon_soup_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces);

ProtectedRemeshStepIO protected_remesh_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double sharp_edge_dihedral_degrees,
    double target_edge_length,
    int    remesh_iterations);

SimplifyToBudgetStepIO simplify_to_budget_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::size_t max_dense_kl_bytes,
    double      safety_margin);

}  // namespace detail
}  // namespace mvrmesh
