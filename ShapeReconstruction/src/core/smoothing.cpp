#include "mvrmesh/core/smoothing.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <limits>
#include <stdexcept>
#include <sstream>
#include <utility>
#include <vector>

#include "mvrmesh/core/geometry.h"

namespace mvrmesh {

namespace {

constexpr double kDegenerateEdgeEpsilon = 1e-12;
constexpr double kDegenerateTriangleEpsilon = 1e-12;

void add_unique_neighbor(std::vector<int>& neighbors, int v) {
    if (std::find(neighbors.begin(), neighbors.end(), v) == neighbors.end()) {
        neighbors.push_back(v);
    }
}

std::pair<int, int> make_edge_key(int i, int j) {
    if (i < j) {
        return {i, j};
    }
    return {j, i};
}

void validate_face_index(const std::vector<Vec3>& vertices, int idx) {
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertices.size()) {
        std::ostringstream oss;
        oss << "Face index out of range for smoothing: " << idx
            << ", n_vertices=" << vertices.size();
        throw std::runtime_error(oss.str());
    }
}

void validate_face_indices(const std::vector<Vec3>& vertices, const std::vector<Face>& faces) {
    for (const Face& face : faces) {
        validate_face_index(vertices, face[0]);
        validate_face_index(vertices, face[1]);
        validate_face_index(vertices, face[2]);
    }
}

void validate_face_geometry(const std::vector<Vec3>& vertices, const std::vector<Face>& faces) {
    for (const Face& face : faces) {
        if (face[0] == face[1] || face[1] == face[2] || face[2] == face[0]) {
            std::ostringstream oss;
            oss << "Taubin smoothing face has duplicate vertex indices: ("
                << face[0] << ", " << face[1] << ", " << face[2] << ")";
            throw std::runtime_error(oss.str());
        }

        const Vec3& a = vertices[static_cast<std::size_t>(face[0])];
        const Vec3& b = vertices[static_cast<std::size_t>(face[1])];
        const Vec3& c = vertices[static_cast<std::size_t>(face[2])];
        const Vec3 cross_prod = cross(vsub(b, a), vsub(c, a));
        const double area_sq = dot(cross_prod, cross_prod);
        if (area_sq <= kDegenerateTriangleEpsilon * kDegenerateTriangleEpsilon) {
            std::ostringstream oss;
            oss << "Taubin smoothing face is degenerate (zero or near-zero area): ("
                << face[0] << ", " << face[1] << ", " << face[2] << ")";
            throw std::runtime_error(oss.str());
        }
    }
}

void build_vertex_adjacency(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::vector<std::vector<int>>& adjacency,
    std::vector<bool>& is_boundary
) {
    adjacency.assign(vertices.size(), {});
    is_boundary.assign(vertices.size(), false);
    if (faces.empty()) {
        return;
    }

    std::map<std::pair<int, int>, int> edge_count;
    for (const Face& face : faces) {
        const int v0 = face[0];
        const int v1 = face[1];
        const int v2 = face[2];

        const auto e01 = make_edge_key(v0, v1);
        const auto e12 = make_edge_key(v1, v2);
        const auto e20 = make_edge_key(v2, v0);
        ++edge_count[e01];
        ++edge_count[e12];
        ++edge_count[e20];

        add_unique_neighbor(adjacency[v0], v1);
        add_unique_neighbor(adjacency[v1], v0);
        add_unique_neighbor(adjacency[v1], v2);
        add_unique_neighbor(adjacency[v2], v1);
        add_unique_neighbor(adjacency[v2], v0);
        add_unique_neighbor(adjacency[v0], v2);
    }

    for (const auto& entry : edge_count) {
        if (entry.second == 1) {
            is_boundary[entry.first.first] = true;
            is_boundary[entry.first.second] = true;
        }
    }
}

void apply_laplacian_pass(
    const std::vector<Vec3>& input,
    const std::vector<std::vector<int>>& adjacency,
    double weight,
    std::vector<Vec3>& output
) {
    output.resize(input.size());
    for (std::size_t i = 0; i < input.size(); ++i) {
        const std::vector<int>& neighbors = adjacency[i];
        if (neighbors.empty()) {
            output[i] = input[i];
            continue;
        }
        Vec3 sum{0.0, 0.0, 0.0};
        for (int j : neighbors) {
            sum = vadd(sum, input[static_cast<std::size_t>(j)]);
        }
        const double inv_degree = 1.0 / static_cast<double>(neighbors.size());
        const Vec3 average = vmul(sum, inv_degree);
        output[i] = vadd(input[i], vmul(vsub(average, input[i]), weight));
    }
}

void restore_boundary_vertices(
    std::vector<Vec3>& output,
    const std::vector<Vec3>& source,
    const std::vector<bool>& is_boundary
) {
    for (std::size_t i = 0; i < output.size() && i < is_boundary.size(); ++i) {
        if (is_boundary[i]) {
            output[i] = source[i];
        }
    }
}

double clamp01(double value) {
    if (value < 0.0) {
        return 0.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

double segment_parameter_clamped(double numerator, double denominator) {
    if (std::abs(denominator) <= kDegenerateEdgeEpsilon) {
        return 0.0;
    }
    return clamp01(numerator / denominator);
}

Vec3 closest_point_to_segment(const Vec3& p, const Vec3& a, const Vec3& b) {
    const Vec3 ab = vsub(b, a);
    const Vec3 ap = vsub(p, a);
    const double t = segment_parameter_clamped(dot(ap, ab), dot(ab, ab));
    return vadd(a, vmul(ab, t));
}

Vec3 closest_point_on_triangle(const Vec3& p, const Vec3& a, const Vec3& b, const Vec3& c) {
    const Vec3 ab = vsub(b, a);
    const Vec3 ac = vsub(c, a);
    const Vec3 ap = vsub(p, a);
    const Vec3 bp = vsub(p, b);
    const Vec3 cp = vsub(p, c);

    const double area_cross_sq = dot(cross(ab, ac), cross(ab, ac));
    if (area_cross_sq <= kDegenerateEdgeEpsilon * kDegenerateEdgeEpsilon) {
        const double d_ab = dot(vsub(closest_point_to_segment(p, a, b), p), vsub(closest_point_to_segment(p, a, b), p));
        const double d_ac = dot(vsub(closest_point_to_segment(p, a, c), p), vsub(closest_point_to_segment(p, a, c), p));
        const double d_bc = dot(vsub(closest_point_to_segment(p, b, c), p), vsub(closest_point_to_segment(p, b, c), p));
        const double best = std::min(d_ab, std::min(d_ac, d_bc));
        if (best == d_ab) {
            return closest_point_to_segment(p, a, b);
        }
        if (best == d_ac) {
            return closest_point_to_segment(p, a, c);
        }
        return closest_point_to_segment(p, b, c);
    }

    const double d1 = dot(ab, ap);
    const double d2 = dot(ac, ap);
    if (d1 <= 0.0 && d2 <= 0.0) {
        return a;
    }

    const double d3 = dot(ab, bp);
    const double d4 = dot(ac, bp);
    if (d3 >= 0.0 && d4 <= d3) {
        return b;
    }

    const double d5 = dot(ab, cp);
    const double d6 = dot(ac, cp);
    if (d6 >= 0.0 && d5 <= d6) {
        return c;
    }

    const double vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0) {
        const double t = segment_parameter_clamped(d1, d1 - d3);
        return vadd(a, vmul(ab, t));
    }

    const double vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0) {
        const double t = segment_parameter_clamped(d2, d2 - d6);
        return vadd(a, vmul(ac, t));
    }

    const double va = d3 * d6 - d5 * d4;
    if (va <= 0.0 && (d4 - d2) >= 0.0 && (d5 - d3) >= 0.0) {
        const double denom = (d4 - d2) + (d5 - d3);
        const double t = segment_parameter_clamped(d4 - d2, denom);
        return vadd(b, vmul(vsub(c, b), t));
    }

    const double inv_denom = 1.0 / (va + vb + vc);
    const double v = vb * inv_denom;
    const double w = vc * inv_denom;
    return vadd(a, vadd(vmul(ab, v), vmul(ac, w)));
}

Vec3 project_vertex_to_reference(
    const Vec3& vertex,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces
) {
    Vec3 best_point = vertex;
    double best_d2 = std::numeric_limits<double>::infinity();
    for (const Face& face : reference_faces) {
        const Vec3& a = reference_vertices[static_cast<std::size_t>(face[0])];
        const Vec3& b = reference_vertices[static_cast<std::size_t>(face[1])];
        const Vec3& c = reference_vertices[static_cast<std::size_t>(face[2])];
        const Vec3 candidate = closest_point_on_triangle(vertex, a, b, c);
        const double d2 = dot(vsub(candidate, vertex), vsub(candidate, vertex));
        if (d2 < best_d2) {
            best_d2 = d2;
            best_point = candidate;
        }
    }
    return best_point;
}

}  // namespace

std::vector<Vec3> taubin_smooth(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    int iterations,
    double lambda,
    double mu,
    bool preserve_boundary
) {
    if (iterations < 0) {
        throw std::runtime_error("taubin_smooth iterations must be >= 0");
    }
    if (iterations == 0) {
        return vertices;
    }

    validate_face_indices(vertices, faces);
    validate_face_geometry(vertices, faces);

    std::vector<std::vector<int>> adjacency;
    std::vector<bool> is_boundary;
    build_vertex_adjacency(vertices, faces, adjacency, is_boundary);

    std::vector<Vec3> current = vertices;
    for (int iteration = 0; iteration < iterations; ++iteration) {
        std::vector<Vec3> laplacian_pass;
        apply_laplacian_pass(current, adjacency, lambda, laplacian_pass);
        if (preserve_boundary) {
            restore_boundary_vertices(laplacian_pass, current, is_boundary);
        }

        std::vector<Vec3> smoothed;
        apply_laplacian_pass(laplacian_pass, adjacency, mu, smoothed);
        if (preserve_boundary) {
            restore_boundary_vertices(smoothed, laplacian_pass, is_boundary);
        }
        current = std::move(smoothed);
    }
    return current;
}

std::vector<Vec3> project_vertices_to_surface(
    const std::vector<Vec3>& vertices,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces
) {
    validate_face_indices(reference_vertices, reference_faces);

    std::vector<Vec3> projected;
    projected.reserve(vertices.size());

    if (reference_faces.empty()) {
        return vertices;
    }

    for (const Vec3& vertex : vertices) {
        projected.push_back(project_vertex_to_reference(vertex, reference_vertices, reference_faces));
    }
    return projected;
}

}  // namespace mvrmesh
