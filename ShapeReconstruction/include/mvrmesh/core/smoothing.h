#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// iterations behavior:
// - iterations < 0: throws std::runtime_error
// - iterations == 0: returns vertices unchanged
// - iterations > 0: applies Taubin smoothing passes using lambda then mu
std::vector<Vec3> taubin_smooth(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double lambda,
    double mu,
    bool preserve_boundary);

std::vector<Vec3> project_vertices_to_surface(
    const std::vector<Vec3>& vertices,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces);

}  // namespace mvrmesh
