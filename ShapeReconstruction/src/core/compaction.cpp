#include "mvrmesh/core/compaction.h"

#include <cstddef>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace mvrmesh {

std::pair<std::vector<Vec3>, std::vector<Face>> compact_mesh_to_referenced_vertices(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    if (faces.empty()) {
        return std::make_pair(std::vector<Vec3>{}, std::vector<Face>{});
    }

    std::vector<int> old_to_new(vertices.size(), -1);
    std::vector<Vec3> compact_vertices;
    compact_vertices.reserve(vertices.size());
    std::vector<Face> compact_faces;
    compact_faces.reserve(faces.size());

    auto map_index = [&](int idx) -> int {
        if (idx < 0 || static_cast<std::size_t>(idx) >= vertices.size()) {
            std::ostringstream oss;
            oss << "compact_mesh_to_referenced_vertices index out of range: " << idx
                << ", n_vertices=" << vertices.size();
            throw std::runtime_error(oss.str());
        }
        int& mapped = old_to_new[static_cast<std::size_t>(idx)];
        if (mapped >= 0) {
            return mapped;
        }
        mapped = static_cast<int>(compact_vertices.size());
        compact_vertices.push_back(vertices[static_cast<std::size_t>(idx)]);
        return mapped;
    };

    for (const Face& face : faces) {
        compact_faces.push_back(Face{
            map_index(face[0]),
            map_index(face[1]),
            map_index(face[2]),
        });
    }

    return std::make_pair(std::move(compact_vertices), std::move(compact_faces));
}

}  // namespace mvrmesh
