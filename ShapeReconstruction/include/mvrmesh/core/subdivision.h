#pragma once

#include <set>
#include <utility>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Splits faces against `split_edges` (sorted vertex-index keys, as from
// make_edge_key): a face with 1/2/3 marked edges becomes 2/3/4 triangles sharing
// midpoint vertices with neighbouring faces; unmarked faces pass through. Returns
// the new vertex list (originals first, midpoints appended) and faces oriented
// like their source face.
std::pair<std::vector<Vec3>, std::vector<Face>> split_faces_with_edge_set(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::set<Edge>& split_edges
);

// Applies `iterations` rounds of 4-to-1 midpoint subdivision to every face.
// Throws std::runtime_error if iterations < 1.
std::pair<std::vector<Vec3>, std::vector<Face>> uniform_subdivide(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations
);

// Curvature-adaptive refinement: each round estimates per-vertex curvature, marks
// the edges of the highest-curvature `split_ratio` fraction of faces, and splits
// them. iterations <= 0 returns the input unchanged.
std::pair<std::vector<Vec3>, std::vector<Face>> adaptive_remesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double split_ratio
);

}  // namespace mvrmesh
