#pragma once

#include <set>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Estimates a dimensionless per-vertex curvature proxy from the spread of incident
// face normals: 0 on flat patches, growing where neighbouring faces diverge.
// Returns one value per vertex (parallel to `vertices`); vertices with no incident
// face stay 0. Throws std::out_of_range if a face references a vertex index
// outside `vertices`.
std::vector<double> estimate_vertex_curvature(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

// Ranks faces by the mean curvature of their three vertices and selects the top
// `split_ratio` fraction (rounded, clamped to [1, n_faces]). Returns the edge keys
// (sorted vertex-index pairs, as from make_edge_key) of every selected face.
// Throws std::out_of_range if a face indexes past `vertex_curvature`.
std::set<Edge> select_split_edges_by_curvature(
    const std::vector<Face>& faces,
    const std::vector<double>& vertex_curvature,
    double split_ratio
);

}  // namespace mvrmesh
