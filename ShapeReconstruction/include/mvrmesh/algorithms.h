#pragma once

#include <set>
#include <utility>
#include <vector>

#include "mvrmesh/types.h"

namespace mvrmesh {

std::pair<std::vector<Vec3>, std::vector<Tet>> subdivide_tetrahedra(
    const std::vector<Vec3>& vertices,
    const std::vector<Tet>& tets
);

std::vector<double> estimate_vertex_curvature(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

std::set<Edge> select_split_edges_by_curvature(
    const std::vector<Face>& faces,
    const std::vector<double>& vertex_curvature,
    double split_ratio
);

std::pair<std::vector<Vec3>, std::vector<Face>> split_faces_with_edge_set(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::set<Edge>& split_edges
);

std::pair<std::vector<Vec3>, std::vector<Face>> adaptive_remesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double split_ratio
);

}  // namespace mvrmesh

