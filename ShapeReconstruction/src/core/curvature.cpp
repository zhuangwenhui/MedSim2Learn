#include "mvrmesh/core/curvature.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <map>
#include <set>
#include <vector>

#include "mvrmesh/core/geometry.h"

namespace mvrmesh {


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
    const int rounded = static_cast<int>(std::round(static_cast<double>(n_faces) * split_ratio));
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

}  // namespace mvrmesh
