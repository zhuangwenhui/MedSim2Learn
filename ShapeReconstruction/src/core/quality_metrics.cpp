#include "mvrmesh/core/quality_metrics.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/core/geometry.h"
#include "mvrmesh/core/topology.h"

namespace mvrmesh {

namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr double kDegenerateEdgeEpsilon = 1e-12;

std::string indent_spaces(int level, int indent) {
    return std::string(static_cast<std::size_t>(std::max(0, level * indent)), ' ');
}

std::string stable_double_to_string(double value) {
    if (std::isnan(value)) {
        return "null";
    }
    if (std::isinf(value)) {
        return "null";
    }
    std::ostringstream out;
    out << std::setprecision(17) << value;
    return out.str();
}

double to_degrees(double radians) {
    return radians * 180.0 / kPi;
}

double clamp_minus_one_to_one(double value) {
    if (value < -1.0) {
        return -1.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

double edge_length(const Vec3& a, const Vec3& b) {
    return norm(vsub(a, b));
}

double triangle_min_angle_degrees(
    double l_ab,
    double l_bc,
    double l_ca
) {
    if (l_ab <= kDegenerateEdgeEpsilon || l_bc <= kDegenerateEdgeEpsilon || l_ca <= kDegenerateEdgeEpsilon) {
        return 0.0;
    }

    const double ab2 = l_ab * l_ab;
    const double bc2 = l_bc * l_bc;
    const double ca2 = l_ca * l_ca;

    // Clamp for acos stability -- floating-point rounding can push dot products slightly outside [-1, 1].
    const double cos_alpha = clamp_minus_one_to_one((ab2 + ca2 - bc2) / (2.0 * l_ab * l_ca));
    const double cos_beta = clamp_minus_one_to_one((ab2 + bc2 - ca2) / (2.0 * l_ab * l_bc));
    const double cos_gamma = clamp_minus_one_to_one((bc2 + ca2 - ab2) / (2.0 * l_bc * l_ca));

    const double alpha = to_degrees(std::acos(cos_alpha));
    const double beta = to_degrees(std::acos(cos_beta));
    const double gamma = to_degrees(std::acos(cos_gamma));

    return std::min({alpha, beta, gamma});
}

double triangle_aspect_ratio(
    double l_ab,
    double l_bc,
    double l_ca,
    double area
) {
    const double longest_edge = std::max(l_ab, std::max(l_bc, l_ca));
    const double alt_ab = (l_ab > kDegenerateEdgeEpsilon) ? (2.0 * area / l_ab) : 0.0;
    const double alt_bc = (l_bc > kDegenerateEdgeEpsilon) ? (2.0 * area / l_bc) : 0.0;
    const double alt_ca = (l_ca > kDegenerateEdgeEpsilon) ? (2.0 * area / l_ca) : 0.0;
    const double shortest_altitude = std::min(alt_ab, std::min(alt_bc, alt_ca));
    if (shortest_altitude <= kDegenerateEdgeEpsilon || area <= kDegenerateEdgeEpsilon) {
        return std::numeric_limits<double>::infinity();
    }
    return longest_edge / shortest_altitude;
}

double bbox_diagonal(const std::vector<Vec3>& vertices) {
    const MeshBoundingBox box = compute_bbox(vertices);
    if (!box.valid) {
        return 0.0;
    }
    return norm(vsub(box.max, box.min));
}

Vec3 centroid(const std::vector<Vec3>& vertices) {
    if (vertices.empty()) {
        return Vec3{0.0, 0.0, 0.0};
    }

    Vec3 sum{0.0, 0.0, 0.0};
    for (const Vec3& vertex : vertices) {
        sum = vadd(sum, vertex);
    }
    const double inv_count = 1.0 / static_cast<double>(vertices.size());
    return vmul(sum, inv_count);
}

ScalarStats compute_scalar_stats(const std::vector<double>& values) {
    ScalarStats stats;
    if (values.empty()) {
        return stats;
    }

    stats.count = values.size();
    stats.min = std::numeric_limits<double>::infinity();
    stats.max = -std::numeric_limits<double>::infinity();
    bool has_infinite = false;
    bool has_nan = false;

    double sum = 0.0;
    double sumsq = 0.0;
    for (double value : values) {
        if (std::isnan(value)) {
            has_nan = true;
        }
        if (std::isinf(value)) {
            has_infinite = true;
        }
        if (!std::isnan(value)) {
            stats.min = std::min(stats.min, value);
            stats.max = std::max(stats.max, value);
        }
        sum += value;
        sumsq += value * value;
    }

    if (has_nan) {
        stats.min = std::numeric_limits<double>::quiet_NaN();
        stats.mean = std::numeric_limits<double>::quiet_NaN();
        stats.max = std::numeric_limits<double>::quiet_NaN();
        stats.rms = std::numeric_limits<double>::quiet_NaN();
        stats.standard_deviation = std::numeric_limits<double>::quiet_NaN();
        stats.coefficient_of_variation = std::numeric_limits<double>::quiet_NaN();
        return stats;
    }

    if (has_infinite) {
        stats.mean = std::numeric_limits<double>::infinity();
        stats.rms = std::numeric_limits<double>::infinity();
        stats.standard_deviation = std::numeric_limits<double>::infinity();
        stats.coefficient_of_variation = std::numeric_limits<double>::infinity();
        return stats;
    }

    stats.mean = sum / static_cast<double>(values.size());
    stats.rms = std::sqrt(sumsq / static_cast<double>(values.size()));

    double variance = 0.0;
    for (double value : values) {
        const double d = value - stats.mean;
        variance += d * d;
    }
    variance /= static_cast<double>(values.size());
    stats.standard_deviation = std::sqrt(variance);
    if (stats.mean != 0.0) {
        stats.coefficient_of_variation = stats.standard_deviation / std::abs(stats.mean);
    } else {
        stats.coefficient_of_variation = 0.0;
    }
    return stats;
}

std::vector<double> nearest_vertex_distances(
    const std::vector<Vec3>& source_vertices,
    const std::vector<Vec3>& target_vertices,
    const std::vector<Face>& target_faces
) {
    std::vector<double> distances;
    if (source_vertices.empty() || target_faces.empty() || target_vertices.empty()) {
        distances.assign(source_vertices.size(), std::numeric_limits<double>::infinity());
        return distances;
    }

    distances.reserve(source_vertices.size());
    for (const Vec3& vertex : source_vertices) {
        double best = std::numeric_limits<double>::infinity();
        for (const Face& face : target_faces) {
            const Vec3& a = target_vertices[static_cast<std::size_t>(face[0])];
            const Vec3& b = target_vertices[static_cast<std::size_t>(face[1])];
            const Vec3& c = target_vertices[static_cast<std::size_t>(face[2])];
            const double d = norm(vsub(closest_point_on_triangle(vertex, a, b, c), vertex));
            if (d < best) {
                best = d;
            }
        }
        if (best < std::numeric_limits<double>::infinity()) {
            distances.push_back(best);
        }
    }
    return distances;
}

void write_scalar_stats(
    std::ostringstream& out,
    const std::string& key,
    const ScalarStats& stats,
    int indent,
    int level
) {
    const int nested = level + 1;
    out << indent_spaces(level, indent) << '"' << key << "\": {\n";
    out << indent_spaces(nested, indent) << "\"count\": " << stats.count << ",\n";
    out << indent_spaces(nested, indent) << "\"min\": " << stable_double_to_string(stats.min) << ",\n";
    out << indent_spaces(nested, indent) << "\"max\": " << stable_double_to_string(stats.max) << ",\n";
    out << indent_spaces(nested, indent) << "\"mean\": " << stable_double_to_string(stats.mean) << ",\n";
    out << indent_spaces(nested, indent) << "\"rms\": " << stable_double_to_string(stats.rms) << ",\n";
    out << indent_spaces(nested, indent) << "\"standard_deviation\": "
        << stable_double_to_string(stats.standard_deviation) << ",\n";
    out << indent_spaces(nested, indent) << "\"coefficient_of_variation\": "
        << stable_double_to_string(stats.coefficient_of_variation) << "\n";
    out << indent_spaces(level, indent) << "}";
}

}  // namespace

MeshQualityMetrics compute_mesh_quality_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    validate_face_indices(vertices, faces, "mesh quality metrics");

    MeshQualityMetrics metrics;
    if (faces.empty() || vertices.empty()) {
        return metrics;
    }

    std::vector<double> edge_lengths;
    std::vector<double> face_areas;
    std::vector<double> min_angles;
    std::vector<double> aspect_ratios;
    std::map<Edge, std::vector<int>> edge_faces;
    std::map<Edge, double> unique_edges;
    std::vector<Vec3> face_normals;
    face_normals.reserve(faces.size());

    for (std::size_t fi = 0; fi < faces.size(); ++fi) {
        const Face& face = faces[fi];
        const Vec3& a = vertices[static_cast<std::size_t>(face[0])];
        const Vec3& b = vertices[static_cast<std::size_t>(face[1])];
        const Vec3& c = vertices[static_cast<std::size_t>(face[2])];

        const double l_ab = edge_length(a, b);
        const double l_bc = edge_length(b, c);
        const double l_ca = edge_length(c, a);
        const double area = triangle_area(a, b, c);

        const Edge ab_key = make_edge_key(face[0], face[1]);
        const Edge bc_key = make_edge_key(face[1], face[2]);
        const Edge ca_key = make_edge_key(face[2], face[0]);
        edge_faces[ab_key].push_back(static_cast<int>(fi));
        edge_faces[bc_key].push_back(static_cast<int>(fi));
        edge_faces[ca_key].push_back(static_cast<int>(fi));

        if (unique_edges.find(ab_key) == unique_edges.end()) {
            unique_edges[ab_key] = l_ab;
        }
        if (unique_edges.find(bc_key) == unique_edges.end()) {
            unique_edges[bc_key] = l_bc;
        }
        if (unique_edges.find(ca_key) == unique_edges.end()) {
            unique_edges[ca_key] = l_ca;
        }

        face_areas.push_back(area);
        min_angles.push_back(triangle_min_angle_degrees(l_ab, l_bc, l_ca));
        aspect_ratios.push_back(triangle_aspect_ratio(l_ab, l_bc, l_ca, area));

        const Vec3 fn = normalize(cross(vsub(b, a), vsub(c, a)));
        face_normals.push_back(fn);
    }

    edge_lengths.reserve(unique_edges.size());
    for (const auto& entry : unique_edges) {
        edge_lengths.push_back(entry.second);
    }

    metrics.edge_length = compute_scalar_stats(edge_lengths);
    metrics.face_area = compute_scalar_stats(face_areas);
    metrics.min_angle_degrees = compute_scalar_stats(min_angles);
    metrics.aspect_ratio = compute_scalar_stats(aspect_ratios);

    std::vector<double> dihedral_angles;
    dihedral_angles.reserve(edge_faces.size());
    for (const auto& entry : edge_faces) {
        const auto& adjacent = entry.second;
        if (adjacent.size() != 2) {
            continue;
        }

        const Vec3& n0 = face_normals[static_cast<std::size_t>(adjacent[0])];
        const Vec3& n1 = face_normals[static_cast<std::size_t>(adjacent[1])];
        const double n0_len = norm(n0);
        const double n1_len = norm(n1);
        if (n0_len <= kDegenerateEdgeEpsilon || n1_len <= kDegenerateEdgeEpsilon) {
            continue;
        }

        const double cos_angle = clamp_minus_one_to_one(dot(n0, n1) / (n0_len * n1_len));
        dihedral_angles.push_back(to_degrees(std::acos(cos_angle)));
    }

    metrics.dihedral_angle_degrees = compute_scalar_stats(dihedral_angles);
    return metrics;
}

ShapeComparisonMetrics compare_shape_to_reference(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces
) {
    validate_face_indices(vertices, faces, "shape comparison");
    validate_face_indices(reference_vertices, reference_faces, "shape comparison reference");

    ShapeComparisonMetrics metrics{};

    if (!vertices.empty() && !reference_vertices.empty()) {
        const Vec3 c = centroid(vertices);
        const Vec3 c_ref = centroid(reference_vertices);
        metrics.centroid_drift = norm(vsub(c, c_ref));
    }

    const double bbox_ref = bbox_diagonal(reference_vertices);
    const double bbox_current = bbox_diagonal(vertices);
    metrics.bbox_diag_delta = bbox_current - bbox_ref;
    metrics.bbox_diag_abs_delta = std::abs(metrics.bbox_diag_delta);

    auto triangle_areas = [&](const std::vector<Vec3>& verts, const std::vector<Face>& tris) {
        double total = 0.0;
        for (const Face& face : tris) {
            const Vec3& a = verts[static_cast<std::size_t>(face[0])];
            const Vec3& b = verts[static_cast<std::size_t>(face[1])];
            const Vec3& c = verts[static_cast<std::size_t>(face[2])];
            total += triangle_area(a, b, c);
        }
        return total;
    };

    const double ref_area = triangle_areas(reference_vertices, reference_faces);
    const double curr_area = triangle_areas(vertices, faces);
    if (std::abs(ref_area) <= kDegenerateEdgeEpsilon) {
        metrics.surface_area_delta_ratio = 0.0;
    } else {
        metrics.surface_area_delta_ratio = (curr_area - ref_area) / ref_area;
    }

    const std::vector<double> vertex_to_reference =
        nearest_vertex_distances(vertices, reference_vertices, reference_faces);
    const std::vector<double> reference_to_vertex =
        nearest_vertex_distances(reference_vertices, vertices, faces);
    metrics.vertex_to_reference_distance = compute_scalar_stats(vertex_to_reference);
    metrics.reference_to_vertex_distance = compute_scalar_stats(reference_to_vertex);

    std::vector<double> symmetric_vertex_distance;
    symmetric_vertex_distance.reserve(vertex_to_reference.size() + reference_to_vertex.size());
    symmetric_vertex_distance.insert(
        symmetric_vertex_distance.end(),
        vertex_to_reference.begin(),
        vertex_to_reference.end()
    );
    symmetric_vertex_distance.insert(
        symmetric_vertex_distance.end(),
        reference_to_vertex.begin(),
        reference_to_vertex.end()
    );
    metrics.symmetric_vertex_distance = compute_scalar_stats(symmetric_vertex_distance);
    return metrics;
}

std::string mesh_quality_to_json(const MeshQualityMetrics& metrics, int indent) {
    std::ostringstream out;
    out << "{\n";
    write_scalar_stats(out, "edge_length", metrics.edge_length, indent, 1);
    out << ",\n";
    write_scalar_stats(out, "face_area", metrics.face_area, indent, 1);
    out << ",\n";
    write_scalar_stats(out, "min_angle_degrees", metrics.min_angle_degrees, indent, 1);
    out << ",\n";
    write_scalar_stats(out, "aspect_ratio", metrics.aspect_ratio, indent, 1);
    out << ",\n";
    write_scalar_stats(out, "dihedral_angle_degrees", metrics.dihedral_angle_degrees, indent, 1);
    out << "\n}";
    return out.str();
}

std::string shape_comparison_to_json(const ShapeComparisonMetrics& metrics, int indent) {
    std::ostringstream out;
    out << "{\n";
    out << indent_spaces(1, indent) << "\"centroid_drift\": "
        << stable_double_to_string(metrics.centroid_drift) << ",\n";
    out << indent_spaces(1, indent) << "\"bbox_diag_delta\": "
        << stable_double_to_string(metrics.bbox_diag_delta) << ",\n";
    out << indent_spaces(1, indent) << "\"bbox_diag_abs_delta\": "
        << stable_double_to_string(metrics.bbox_diag_abs_delta) << ",\n";
    out << indent_spaces(1, indent) << "\"surface_area_delta_ratio\": "
        << stable_double_to_string(metrics.surface_area_delta_ratio) << ",\n";
    write_scalar_stats(out, "vertex_to_reference_distance", metrics.vertex_to_reference_distance, indent, 1);
    out << ",\n";
    write_scalar_stats(
        out,
        "reference_to_vertex_distance",
        metrics.reference_to_vertex_distance,
        indent,
        1
    );
    out << ",\n";
    write_scalar_stats(out, "symmetric_vertex_distance", metrics.symmetric_vertex_distance, indent, 1);
    out << "\n}";
    return out.str();
}

}  // namespace mvrmesh
