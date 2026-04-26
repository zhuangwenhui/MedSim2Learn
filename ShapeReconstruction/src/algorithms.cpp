#include "mvrmesh/algorithms.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

#include "mvrmesh/geometry.h"
#include "mvrmesh/topology.h"

namespace mvrmesh {

namespace {

Edge make_edge_key(int i, int j) {
    if (i < j) {
        return Edge{i, j};
    }
    return Edge{j, i};
}

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

int py_round_nonnegative_to_int(double value) {
    const double floor_v = std::floor(value);
    const double frac = value - floor_v;
    const double eps = 1e-12;

    if (frac > 0.5 + eps) {
        return static_cast<int>(floor_v + 1.0);
    }
    if (frac < 0.5 - eps) {
        return static_cast<int>(floor_v);
    }

    const int lower = static_cast<int>(floor_v);
    if ((lower % 2) == 0) {
        return lower;
    }
    return lower + 1;
}

}  // namespace

std::vector<double> estimate_vertex_curvature(const std::vector<Vec3>& vertices, const std::vector<Face>& faces) {
    std::map<int, std::vector<int>> incident;
    std::vector<Vec3> face_normals;
    face_normals.reserve(faces.size());

    for (int fidx = 0; fidx < static_cast<int>(faces.size()); ++fidx) {
        const Face& face = faces[static_cast<std::size_t>(fidx)];
        const Vec3 n = face_normal(
            vertices.at(static_cast<std::size_t>(face[0])),
            vertices.at(static_cast<std::size_t>(face[1])),
            vertices.at(static_cast<std::size_t>(face[2]))
        );
        face_normals.push_back(n);
        incident[face[0]].push_back(fidx);
        incident[face[1]].push_back(fidx);
        incident[face[2]].push_back(fidx);
    }

    std::vector<double> curvature(vertices.size(), 0.0);
    for (int vidx = 0; vidx < static_cast<int>(vertices.size()); ++vidx) {
        const auto found = incident.find(vidx);
        if (found == incident.end()) {
            continue;
        }

        Vec3 avg{0.0, 0.0, 0.0};
        for (int fidx : found->second) {
            avg = vadd(avg, face_normals[static_cast<std::size_t>(fidx)]);
        }
        const Vec3 v_n = normalize(avg);

        double c_sum = 0.0;
        for (int fidx : found->second) {
            const Vec3& n = face_normals[static_cast<std::size_t>(fidx)];
            const double d = std::max(-1.0, std::min(1.0, std::abs(dot(v_n, n))));
            c_sum += 1.0 - d;
        }
        curvature[static_cast<std::size_t>(vidx)] = c_sum / static_cast<double>(found->second.size());
    }

    return curvature;
}

std::set<Edge> select_split_edges_by_curvature(
    const std::vector<Face>& faces,
    const std::vector<double>& vertex_curvature,
    double split_ratio
) {
    std::vector<std::pair<double, int>> face_scores;
    face_scores.reserve(faces.size());

    for (int fidx = 0; fidx < static_cast<int>(faces.size()); ++fidx) {
        const Face& face = faces[static_cast<std::size_t>(fidx)];
        const double score = (
            vertex_curvature.at(static_cast<std::size_t>(face[0])) +
            vertex_curvature.at(static_cast<std::size_t>(face[1])) +
            vertex_curvature.at(static_cast<std::size_t>(face[2]))
        ) / 3.0;
        face_scores.emplace_back(score, fidx);
    }

    std::sort(face_scores.begin(), face_scores.end(), [](const auto& lhs, const auto& rhs) {
        if (lhs.first == rhs.first) {
            return lhs.second > rhs.second;
        }
        return lhs.first > rhs.first;
    });

    const int n_faces = static_cast<int>(faces.size());
    const int rounded = py_round_nonnegative_to_int(static_cast<double>(n_faces) * split_ratio);
    const int target = std::max(1, std::min(n_faces, rounded));

    std::set<int> selected_face_indices;
    for (int i = 0; i < target && i < static_cast<int>(face_scores.size()); ++i) {
        selected_face_indices.insert(face_scores[static_cast<std::size_t>(i)].second);
    }

    std::set<Edge> split_edges;
    for (int fidx = 0; fidx < static_cast<int>(faces.size()); ++fidx) {
        if (selected_face_indices.find(fidx) == selected_face_indices.end()) {
            continue;
        }

        const Face& face = faces[static_cast<std::size_t>(fidx)];
        split_edges.insert(make_edge_key(face[0], face[1]));
        split_edges.insert(make_edge_key(face[1], face[2]));
        split_edges.insert(make_edge_key(face[2], face[0]));
    }

    return split_edges;
}

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
