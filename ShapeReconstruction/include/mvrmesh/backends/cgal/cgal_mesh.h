#pragma once

#include <cstddef>
#include <vector>

#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

// What the polygon-soup repair step did: sizes before/after, duplicate vertices
// merged, degenerate faces dropped, border holes triangulated, and whether the
// soup could be consistently oriented.
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

// What the feature-protected remesh step did: sizes before/after, sharp edges
// held fixed, and the target edge length and iteration count actually used.
struct ProtectedRemeshStepReport {
    std::size_t input_vertex_count       = 0;
    std::size_t input_face_count         = 0;
    std::size_t output_vertex_count      = 0;
    std::size_t output_face_count        = 0;
    std::size_t sharp_edges_detected     = 0;
    double      target_edge_length_used  = 0.0;
    int         remesh_iterations_used   = 0;
};

// Final mesh from the CGAL backend together with the per-step reports.
struct CgalMeshResult {
    std::vector<Vec3>          vertices;
    std::vector<Face>          faces;
    RepairStepReport           repair_report;
    ProtectedRemeshStepReport  remesh_report;
};

// Repairs the input polygon soup, then isotropically remeshes it while keeping
// sharp edges fixed. Throws std::runtime_error if the input cannot be repaired
// or oriented, or if the remesh options are out of range.
CgalMeshResult run_cgal_mesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const CgalMeshConfig& options);

// Repair step only, no remeshing; `remesh_report` in the result stays
// value-initialized. Same failure behavior as run_cgal_mesh.
CgalMeshResult run_cgal_repair_only(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces);

// Pipeline stages split out so tests can drive them individually.
namespace detail {

// Mesh and report produced by the repair stage.
struct RepairStepIO {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    RepairStepReport  report;
};

// Mesh and report produced by the remesh stage.
struct ProtectedRemeshStepIO {
    std::vector<Vec3>         vertices;
    std::vector<Face>         faces;
    ProtectedRemeshStepReport report;
};

// Step 1: merges duplicate vertices, drops degenerate faces, orients the soup,
// assembles a surface mesh, and triangulates every border hole. Throws
// std::runtime_error on fewer than 3 vertices, an unorientable soup, or a hole
// that cannot be triangulated.
RepairStepIO repair_polygon_soup_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces);

// Step 2: detects sharp edges above the dihedral threshold (degrees) and runs
// isotropic remeshing with those edges protected. A target_edge_length of 0
// means "use the input's mean edge length". Throws std::runtime_error on
// out-of-range parameters or when every edge is sharp.
ProtectedRemeshStepIO protected_remesh_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double sharp_edge_dihedral_degrees,
    double target_edge_length,
    int    remesh_iterations);

}  // namespace detail
}  // namespace mvrmesh
