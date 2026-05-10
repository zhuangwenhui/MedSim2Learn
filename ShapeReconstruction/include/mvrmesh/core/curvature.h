#pragma once

#include <set>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

std::vector<double> estimate_vertex_curvature(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

std::set<Edge> select_split_edges_by_curvature(
    const std::vector<Face>& faces,
    const std::vector<double>& vertex_curvature,
    double split_ratio
);

}  // namespace mvrmesh
