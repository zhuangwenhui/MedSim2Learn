#pragma once

#include <utility>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Drops vertices not referenced by any face and remaps the faces onto the
// compact vertex list (kept vertices appear in first-reference order).
// Returns the (vertices, faces) pair; an empty `faces` yields an empty mesh.
std::pair<std::vector<Vec3>, std::vector<Face>> compact_mesh_to_referenced_vertices(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

}  // namespace mvrmesh
