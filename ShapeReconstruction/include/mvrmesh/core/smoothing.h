#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Taubin smoothing: each iteration runs a shrink pass (lambda) then an inflate
// pass (mu) over one-ring neighbour averages, damping high-frequency noise without
// the volume loss of plain Laplacian smoothing. With preserve_boundary, vertices on
// boundary edges keep their input positions. iterations == 0 returns the input
// unchanged. Throws std::runtime_error on duplicate-index or degenerate faces, or
// when iterations < 0.
std::vector<Vec3> taubin_smooth(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double lambda,
    double mu,
    bool preserve_boundary);

// Projects each vertex to its closest point on the reference triangle mesh, by
// brute force over all reference faces. Returns `vertices` unchanged when
// `reference_faces` is empty.
std::vector<Vec3> project_vertices_to_surface(
    const std::vector<Vec3>& vertices,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces);

}  // namespace mvrmesh
