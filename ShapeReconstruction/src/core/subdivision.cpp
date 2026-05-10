#include "mvrmesh/core/subdivision.h"

#include <cmath>
#include <cstddef>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

#include "mvrmesh/core/curvature.h"
#include "mvrmesh/core/geometry.h"
#include "mvrmesh/core/topology.h"

namespace mvrmesh {

namespace {

int midpoint_index(std::vector<Vec3>& vertices, std::map<Edge, int>& cache, int i, int j) {
    const Edge key = make_edge_key(i, j);
    const auto found = cache.find(key);
    if (found != cache.end()) {
        return found->second;
    }

    const Vec3 mid = vmul(vadd(vertices.at(static_cast<std::size_t>(i)), vertices.at(static_cast<std::size_t>(j))), 0.5);
    const int idx = static_cast<int>(vertices.size());
    vertices.push_back(mid);
    cache.emplace(key, idx);
    return idx;
}

std::pair<std::vector<Vec3>, std::vector<Face>> uniform_subdivide_once(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    std::vector<Vec3> out_vertices = vertices;
    std::map<Edge, int> edge_mid_cache;
    std::vector<Face> out_faces;
    out_faces.reserve(faces.size() * 4);

    for (const Face& face : faces) {
        const int i = face[0];
        const int j = face[1];
        const int k = face[2];

        const int m0 = midpoint_index(out_vertices, edge_mid_cache, i, j);
        const int m1 = midpoint_index(out_vertices, edge_mid_cache, j, k);
        const int m2 = midpoint_index(out_vertices, edge_mid_cache, k, i);

        const Face base{i, j, k};
        const std::vector<Face> created{
            Face{i, m0, m2},
            Face{m0, j, m1},
            Face{m2, m1, k},
            Face{m0, m1, m2},
        };

        for (const Face& tri : created) {
            out_faces.push_back(orient_like_face(out_vertices, base, tri));
        }
    }

    return std::make_pair(std::move(out_vertices), std::move(out_faces));
}

}  // namespace

std::pair<std::vector<Vec3>, std::vector<Face>> split_faces_with_edge_set(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::set<Edge>& split_edges
) {
    std::vector<Vec3> out_vertices = vertices;
    std::map<Edge, int> edge_mid_cache;
    std::vector<Face> out_faces;

    for (const Face& face : faces) {
        const int i = face[0];
        const int j = face[1];
        const int k = face[2];

        const Edge e0 = make_edge_key(i, j);
        const Edge e1 = make_edge_key(j, k);
        const Edge e2 = make_edge_key(k, i);

        std::optional<int> m0;
        std::optional<int> m1;
        std::optional<int> m2;

        if (split_edges.find(e0) != split_edges.end()) {
            m0 = midpoint_index(out_vertices, edge_mid_cache, i, j);
        }
        if (split_edges.find(e1) != split_edges.end()) {
            m1 = midpoint_index(out_vertices, edge_mid_cache, j, k);
        }
        if (split_edges.find(e2) != split_edges.end()) {
            m2 = midpoint_index(out_vertices, edge_mid_cache, k, i);
        }

        const int count = static_cast<int>(m0.has_value()) +
                          static_cast<int>(m1.has_value()) +
                          static_cast<int>(m2.has_value());
        const Face base{i, j, k};
        std::vector<Face> created;

        if (count == 0) {
            created.push_back(base);
        } else if (count == 1) {
            if (m0.has_value()) {
                created.push_back(Face{i, *m0, k});
                created.push_back(Face{*m0, j, k});
            } else if (m1.has_value()) {
                created.push_back(Face{j, *m1, i});
                created.push_back(Face{*m1, k, i});
            } else {
                created.push_back(Face{k, *m2, j});
                created.push_back(Face{*m2, i, j});
            }
        } else if (count == 2) {
            if (m0.has_value() && m1.has_value()) {
                created.push_back(Face{j, *m1, *m0});
                created.push_back(Face{i, *m0, k});
                created.push_back(Face{*m0, *m1, k});
            } else if (m1.has_value() && m2.has_value()) {
                created.push_back(Face{k, *m2, *m1});
                created.push_back(Face{j, *m1, i});
                created.push_back(Face{i, *m1, *m2});
            } else {
                created.push_back(Face{i, *m0, *m2});
                created.push_back(Face{k, *m2, j});
                created.push_back(Face{j, *m2, *m0});
            }
        } else {
            created.push_back(Face{i, *m0, *m2});
            created.push_back(Face{*m0, j, *m1});
            created.push_back(Face{*m2, *m1, k});
            created.push_back(Face{*m0, *m1, *m2});
        }

        for (const Face& tri : created) {
            out_faces.push_back(orient_like_face(out_vertices, base, tri));
        }
    }

    return std::make_pair(std::move(out_vertices), std::move(out_faces));
}

std::pair<std::vector<Vec3>, std::vector<Face>> uniform_subdivide(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations
) {
    if (iterations < 1) {
        throw std::runtime_error("uniform_subdivide iterations must be >= 1");
    }

    std::vector<Vec3> out_vertices = vertices;
    std::vector<Face> out_faces = faces;
    for (int iteration = 0; iteration < iterations; ++iteration) {
        auto subdivided = uniform_subdivide_once(out_vertices, out_faces);
        out_vertices = std::move(subdivided.first);
        out_faces = std::move(subdivided.second);
    }
    return std::make_pair(std::move(out_vertices), std::move(out_faces));
}

std::pair<std::vector<Vec3>, std::vector<Face>> adaptive_remesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double split_ratio
) {
    std::vector<Vec3> out_vertices = vertices;
    std::vector<Face> out_faces = faces;
    for (int iteration = 0; iteration < iterations; ++iteration) {
        const std::vector<double> v_curv = estimate_vertex_curvature(out_vertices, out_faces);
        const std::set<Edge> split_edges = select_split_edges_by_curvature(out_faces, v_curv, split_ratio);
        auto split_result = split_faces_with_edge_set(out_vertices, out_faces, split_edges);
        out_vertices = std::move(split_result.first);
        out_faces = std::move(split_result.second);
    }
    return std::make_pair(std::move(out_vertices), std::move(out_faces));
}

}  // namespace mvrmesh
