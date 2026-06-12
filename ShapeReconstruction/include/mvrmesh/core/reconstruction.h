#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Upper bound on SdfReconstructionOptions::grid_resolution; caps the SDF grid
// memory at (resolution + 1)^3 sampled doubles.
inline constexpr int kMaxSdfGridResolution = 160;

// Controls for SDF-based surface reconstruction.
struct SdfReconstructionOptions {
    // Sample cubes per axis, in [2, kMaxSdfGridResolution].
    int grid_resolution = 96;
    // Margin added around the input bounding box, as a fraction of its largest span.
    double padding_ratio = 0.05;
};

// Triangle surface extracted by reconstruct_surface_sdf.
struct ReconstructedMesh {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
};

// Rebuilds a surface from a possibly defective boundary mesh: samples the mesh's
// signed distance on a regular grid (CGAL AABB tree + side-of-mesh queries) and
// extracts the zero level set with marching tetrahedra. Returns a compacted mesh
// with outward-oriented faces. Throws std::runtime_error on invalid options, empty
// input, or CGAL initialization failure.
ReconstructedMesh reconstruct_surface_sdf(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfReconstructionOptions& options
);

}  // namespace mvrmesh
