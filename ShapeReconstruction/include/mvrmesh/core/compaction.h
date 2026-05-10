#pragma once

#include <utility>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

std::pair<std::vector<Vec3>, std::vector<Face>> compact_mesh_to_referenced_vertices(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

}  // namespace mvrmesh
