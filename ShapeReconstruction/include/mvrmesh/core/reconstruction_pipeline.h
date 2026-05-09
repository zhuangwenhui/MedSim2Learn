#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct SdfRemeshOptions {
    int sdf_resolution = 72;
    double padding_ratio = 0.05;
    double sharp_edge_dihedral_degrees = 179.0;
    double target_edge_length = 0.025;
    int remesh_iterations = 3;
};

struct SdfRemeshResult {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
};

SdfRemeshResult reconstruct_and_remesh_surface(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfRemeshOptions& options);

}  // namespace mvrmesh
