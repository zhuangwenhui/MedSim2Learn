#pragma once

#include <cstddef>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct CgalMeshOptions {
    // Stage 2 tunables
    double sharp_edge_dihedral_degrees = 60.0;
    double target_edge_length          = 0.0;   // 0 -> auto = mean edge length of stage 1 output
    int    remesh_iterations           = 3;
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

struct CgalMeshResult {
    std::vector<Vec3>          vertices;
    std::vector<Face>          faces;
    RepairStepReport           repair_report;
    ProtectedRemeshStepReport  remesh_report;
};

CgalMeshResult run_cgal_mesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const CgalMeshOptions& options);

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

RepairStepIO repair_polygon_soup_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces);

ProtectedRemeshStepIO protected_remesh_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double sharp_edge_dihedral_degrees,
    double target_edge_length,
    int    remesh_iterations);

}  // namespace detail
}  // namespace mvrmesh
