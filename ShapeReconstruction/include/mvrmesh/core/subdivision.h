#pragma once

#include <set>
#include <utility>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

std::pair<std::vector<Vec3>, std::vector<Face>> split_faces_with_edge_set(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::set<Edge>& split_edges
);

std::pair<std::vector<Vec3>, std::vector<Face>> uniform_subdivide(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations
);

std::pair<std::vector<Vec3>, std::vector<Face>> adaptive_remesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double split_ratio
);

}  // namespace mvrmesh
