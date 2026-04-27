#include "mvrmesh/core/topology.h"

#include <algorithm>
#include <array>
#include <map>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <utility>

#include "mvrmesh/core/geometry.h"

namespace mvrmesh {

namespace {

void validate_vertex_index(const std::vector<Vec3>& vertices, int idx, const char* context) {
    if (idx < 0 || idx >= static_cast<int>(vertices.size())) {
        std::ostringstream oss;
        oss << context << " index out of range: " << idx << ", n_vertices=" << vertices.size();
        throw std::runtime_error(oss.str());
    }
}

std::array<int, 3> sorted_face_key(const Face& face) {
    std::array<int, 3> key{face[0], face[1], face[2]};
    std::sort(key.begin(), key.end());
    return key;
}

}  // namespace

std::vector<Face> normalize_faces_indices(const std::vector<Face>& faces, int n_vertices) {
    if (faces.empty()) {
        return {};
    }

    int min_idx = faces.front()[0];
    int max_idx = faces.front()[0];
    for (const Face& face : faces) {
        for (int idx : face) {
            min_idx = std::min(min_idx, idx);
            max_idx = std::max(max_idx, idx);
        }
    }

    if (min_idx >= 0 && max_idx < n_vertices) {
        return faces;
    }
    if (min_idx >= 1 && max_idx <= n_vertices) {
        std::vector<Face> normalized;
        normalized.reserve(faces.size());
        for (const Face& face : faces) {
            normalized.push_back(Face{face[0] - 1, face[1] - 1, face[2] - 1});
        }
        return normalized;
    }

    std::ostringstream oss;
    oss << "Face index out of range. min=" << min_idx << ", max=" << max_idx
        << ", n_vertices=" << n_vertices;
    throw std::runtime_error(oss.str());
}

std::vector<Tet> normalize_tet_indices(const std::vector<Tet>& tets, int n_vertices) {
    if (tets.empty()) {
        return {};
    }

    int min_idx = tets.front()[0];
    int max_idx = tets.front()[0];
    for (const Tet& tet : tets) {
        for (int idx : tet) {
            min_idx = std::min(min_idx, idx);
            max_idx = std::max(max_idx, idx);
        }
    }

    if (min_idx >= 0 && max_idx < n_vertices) {
        return tets;
    }
    if (min_idx >= 1 && max_idx <= n_vertices) {
        std::vector<Tet> normalized;
        normalized.reserve(tets.size());
        for (const Tet& tet : tets) {
            normalized.push_back(Tet{tet[0] - 1, tet[1] - 1, tet[2] - 1, tet[3] - 1});
        }
        return normalized;
    }

    std::ostringstream oss;
    oss << "Tetra index out of range. min=" << min_idx << ", max=" << max_idx
        << ", n_vertices=" << n_vertices;
    throw std::runtime_error(oss.str());
}

Face oriented_face_outward(const std::vector<Vec3>& vertices, const Face& face, int opposite) {
    validate_vertex_index(vertices, face[0], "face");
    validate_vertex_index(vertices, face[1], "face");
    validate_vertex_index(vertices, face[2], "face");
    validate_vertex_index(vertices, opposite, "opposite");

    const Vec3& vi = vertices[face[0]];
    const Vec3& vj = vertices[face[1]];
    const Vec3& vk = vertices[face[2]];
    const Vec3& vo = vertices[opposite];

    const Vec3 n = cross(vsub(vj, vi), vsub(vk, vi));
    if (dot(n, vsub(vo, vi)) > 0.0) {
        return Face{face[0], face[2], face[1]};
    }
    return face;
}

std::vector<Face> boundary_faces_from_tets(const std::vector<Vec3>& vertices, const std::vector<Tet>& tets) {
    std::map<std::array<int, 3>, std::pair<int, Face>> face_usage;

    for (const Tet& tet : tets) {
        const int a = tet[0];
        const int b = tet[1];
        const int c = tet[2];
        const int d = tet[3];

        const std::array<std::pair<Face, int>, 4> local_faces{
            std::make_pair(Face{a, b, c}, d),
            std::make_pair(Face{a, d, b}, c),
            std::make_pair(Face{a, c, d}, b),
            std::make_pair(Face{b, d, c}, a),
        };

        for (const auto& entry : local_faces) {
            const Face oriented = oriented_face_outward(vertices, entry.first, entry.second);
            const std::array<int, 3> key = sorted_face_key(entry.first);
            auto found = face_usage.find(key);
            if (found == face_usage.end()) {
                face_usage.emplace(key, std::make_pair(1, oriented));
            } else {
                found->second.first += 1;
            }
        }
    }

    std::vector<Face> boundary;
    for (const auto& kv : face_usage) {
        if (kv.second.first == 1) {
            boundary.push_back(kv.second.second);
        }
    }
    return boundary;
}

Face orient_like_face(const std::vector<Vec3>& vertices, const Face& base_face, const Face& tri) {
    validate_vertex_index(vertices, base_face[0], "base_face");
    validate_vertex_index(vertices, base_face[1], "base_face");
    validate_vertex_index(vertices, base_face[2], "base_face");
    validate_vertex_index(vertices, tri[0], "tri");
    validate_vertex_index(vertices, tri[1], "tri");
    validate_vertex_index(vertices, tri[2], "tri");

    const Vec3 base_n = cross(
        vsub(vertices[base_face[1]], vertices[base_face[0]]),
        vsub(vertices[base_face[2]], vertices[base_face[0]])
    );
    const Vec3 n = cross(
        vsub(vertices[tri[1]], vertices[tri[0]]),
        vsub(vertices[tri[2]], vertices[tri[0]])
    );
    if (dot(base_n, n) < 0.0) {
        return Face{tri[0], tri[2], tri[1]};
    }
    return tri;
}

}  // namespace mvrmesh

