#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

inline constexpr int kMaxSdfGridResolution = 160;

struct SdfReconstructionOptions {
    int grid_resolution = 96;
    double padding_ratio = 0.05;
};

struct ReconstructedMesh {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
};

ReconstructedMesh reconstruct_surface_sdf(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfReconstructionOptions& options
);

}  // namespace mvrmesh
