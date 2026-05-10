#include "mvrmesh/core/reconstruction_pipeline.h"

#include <cmath>
#include <stdexcept>
#include <utility>

#include "mvrmesh/backends/cgal/cgal_mesh.h"
#include "mvrmesh/core/compaction.h"
#include "mvrmesh/core/reconstruction.h"

namespace mvrmesh {

namespace {

void validate_sdf_remesh_options(const SdfRemeshOptions& options) {
    if (options.sdf_resolution < 2) {
        throw std::invalid_argument("sdf_resolution must be >= 2");
    }
    if (options.sdf_resolution > kMaxSdfGridResolution) {
        throw std::invalid_argument(
            "sdf_resolution must be <= " + std::to_string(kMaxSdfGridResolution)
        );
    }
    if (!std::isfinite(options.padding_ratio) || options.padding_ratio < 0.0) {
        throw std::invalid_argument("padding_ratio must be non-negative and finite");
    }
    if (!(options.sharp_edge_dihedral_degrees > 0.0 && options.sharp_edge_dihedral_degrees < 180.0)) {
        throw std::invalid_argument("sharp_edge_dihedral_degrees must be in (0, 180)");
    }
    if (!std::isfinite(options.target_edge_length) || options.target_edge_length < 0.0) {
        throw std::invalid_argument("target_edge_length must be finite and non-negative");
    }
    if (options.remesh_iterations < 1) {
        throw std::invalid_argument("remesh_iterations must be >= 1");
    }
}

}  // namespace

SdfRemeshResult reconstruct_and_remesh_surface(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfRemeshOptions& options
) {
    validate_sdf_remesh_options(options);

    const std::pair<std::vector<Vec3>, std::vector<Face>> compact_boundary =
        compact_mesh_to_referenced_vertices(boundary_vertices, boundary_faces);
    if (compact_boundary.first.empty() || compact_boundary.second.empty()) {
        throw std::runtime_error("reconstruct_and_remesh_surface: boundary mesh is empty");
    }

    SdfReconstructionOptions sdf_options;
    sdf_options.grid_resolution = options.sdf_resolution;
    sdf_options.padding_ratio = options.padding_ratio;

    const ReconstructedMesh reconstructed = reconstruct_surface_sdf(
        compact_boundary.first,
        compact_boundary.second,
        sdf_options
    );

    CgalMeshConfig cgal_options;
    cgal_options.sharp_edge_dihedral_degrees = options.sharp_edge_dihedral_degrees;
    cgal_options.target_edge_length = options.target_edge_length;
    cgal_options.remesh_iterations = options.remesh_iterations;

    CgalMeshResult remeshed = run_cgal_mesh(
        reconstructed.vertices,
        reconstructed.faces,
        cgal_options
    );

    std::pair<std::vector<Vec3>, std::vector<Face>> compact_output =
        compact_mesh_to_referenced_vertices(remeshed.vertices, remeshed.faces);
    if (compact_output.first.empty() || compact_output.second.empty()) {
        throw std::runtime_error("reconstruct_and_remesh_surface: output mesh is empty");
    }

    SdfRemeshResult result;
    result.vertices = std::move(compact_output.first);
    result.faces = std::move(compact_output.second);
    return result;
}

}  // namespace mvrmesh
