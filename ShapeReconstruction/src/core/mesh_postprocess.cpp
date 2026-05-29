#include "mvrmesh/core/mesh_postprocess.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <unordered_set>
#include <vector>

namespace mvrmesh {

namespace {

double edge_length_sq(const Vec3& a, const Vec3& b) {
    const double dx = b.x - a.x;
    const double dy = b.y - a.y;
    const double dz = b.z - a.z;
    return dx * dx + dy * dy + dz * dz;
}

double triangle_area(const Vec3& a, const Vec3& b, const Vec3& c) {
    const double abx = b.x - a.x, aby = b.y - a.y, abz = b.z - a.z;
    const double acx = c.x - a.x, acy = c.y - a.y, acz = c.z - a.z;
    const double cx = aby * acz - abz * acy;
    const double cy = abz * acx - abx * acz;
    const double cz = abx * acy - aby * acx;
    return 0.5 * std::sqrt(cx * cx + cy * cy + cz * cz);
}

double compute_min_edge_length(const std::vector<Vec3>& vertices,
                               const std::vector<Face>& faces) {
    double min_sq = std::numeric_limits<double>::max();
    for (const auto& f : faces) {
        const auto& a = vertices[static_cast<std::size_t>(f[0])];
        const auto& b = vertices[static_cast<std::size_t>(f[1])];
        const auto& c = vertices[static_cast<std::size_t>(f[2])];
        min_sq = std::min(min_sq, edge_length_sq(a, b));
        min_sq = std::min(min_sq, edge_length_sq(b, c));
        min_sq = std::min(min_sq, edge_length_sq(c, a));
    }
    return std::sqrt(min_sq);
}

}  // namespace

int mesh_quality_fix(std::vector<Vec3>& vertices, std::vector<Face>& faces) {
    if (vertices.empty() || faces.empty()) {
        return 0;
    }

    // -- Step 1: Vertex perturbation (always runs) --
    const double min_edge = compute_min_edge_length(vertices, faces);
    const double epsilon = min_edge * 1e-6;

    std::mt19937_64 rng(42);  // deterministic seed
    std::uniform_real_distribution<double> dist(-epsilon, epsilon);

    for (auto& v : vertices) {
        v.x += dist(rng);
        v.y += dist(rng);
        v.z += dist(rng);
    }

    std::cout << "[info] mesh_quality_fix: perturbed " << vertices.size()
              << " vertices, epsilon=" << epsilon << "\n";

    // -- Step 2: Degenerate triangle detection and removal --
    const double area_threshold = min_edge * min_edge * 1e-8;
    int fixed_count = 0;

    std::vector<std::size_t> degenerate_indices;
    for (std::size_t i = 0; i < faces.size(); ++i) {
        const auto& f = faces[i];
        const auto& a = vertices[static_cast<std::size_t>(f[0])];
        const auto& b = vertices[static_cast<std::size_t>(f[1])];
        const auto& c = vertices[static_cast<std::size_t>(f[2])];
        if (triangle_area(a, b, c) < area_threshold) {
            degenerate_indices.push_back(i);
        }
    }

    if (!degenerate_indices.empty()) {
        for (auto it = degenerate_indices.rbegin();
             it != degenerate_indices.rend(); ++it) {
            faces.erase(faces.begin() + static_cast<std::ptrdiff_t>(*it));
            ++fixed_count;
        }
        std::cout << "[info] mesh_quality_fix: removed " << fixed_count
                  << " degenerate triangles\n";
    }

    // -- Step 3: Remove duplicate faces --
    auto face_key = [](const Face& f) -> std::array<int, 3> {
        std::array<int, 3> sorted = f;
        std::sort(sorted.begin(), sorted.end());
        return sorted;
    };

    struct ArrayHash {
        std::size_t operator()(const std::array<int, 3>& a) const {
            std::size_t h = 0;
            for (int v : a) {
                h ^= std::hash<int>{}(v) + 0x9e3779b9 + (h << 6) + (h >> 2);
            }
            return h;
        }
    };

    std::unordered_set<std::array<int, 3>, ArrayHash> seen;
    std::vector<Face> unique_faces;
    unique_faces.reserve(faces.size());
    int dup_count = 0;
    for (const auto& f : faces) {
        auto key = face_key(f);
        if (seen.insert(key).second) {
            unique_faces.push_back(f);
        } else {
            ++dup_count;
        }
    }
    if (dup_count > 0) {
        faces = std::move(unique_faces);
        std::cout << "[info] mesh_quality_fix: removed " << dup_count
                  << " duplicate faces\n";
    }

    return fixed_count;
}

void restore_physical_coordinates(
    std::vector<Vec3>& vertices,
    const BoundingBox& bounding_box,
    double voxel_spacing_mm) {
    if (!bounding_box.valid) {
        std::cout << "[warn] restore_physical_coordinates: "
                     "no valid bounding box, skipping\n";
        return;
    }
    if (vertices.empty()) {
        return;
    }

    // Compute current vertex bounding box.
    double v_x_min = vertices[0].x, v_x_max = vertices[0].x;
    double v_y_min = vertices[0].y, v_y_max = vertices[0].y;
    double v_z_min = vertices[0].z, v_z_max = vertices[0].z;
    for (const auto& v : vertices) {
        v_x_min = std::min(v_x_min, v.x);
        v_x_max = std::max(v_x_max, v.x);
        v_y_min = std::min(v_y_min, v.y);
        v_y_max = std::max(v_y_max, v.y);
        v_z_min = std::min(v_z_min, v.z);
        v_z_max = std::max(v_z_max, v.z);
    }

    const double v_x_span = v_x_max - v_x_min;
    const double v_y_span = v_y_max - v_y_min;
    const double v_z_span = v_z_max - v_z_min;
    const double bb_x_span = bounding_box.x_max - bounding_box.x_min;
    const double bb_y_span = bounding_box.y_max - bounding_box.y_min;
    const double bb_z_span = bounding_box.z_max - bounding_box.z_min;

    std::cout << "[info] restore_physical_coordinates: "
              << "vertex BB [" << v_x_min << ".." << v_x_max
              << "] x [" << v_y_min << ".." << v_y_max
              << "] x [" << v_z_min << ".." << v_z_max << "]\n";

    for (auto& v : vertices) {
        if (v_x_span > 0.0 && bb_x_span > 0.0) {
            v.x = (bounding_box.x_min +
                   (v.x - v_x_min) / v_x_span * bb_x_span) *
                  voxel_spacing_mm;
        } else if (v_x_span == 0.0) {
            v.x = (v.x + bounding_box.x_min) * voxel_spacing_mm;
        }
        if (v_y_span > 0.0 && bb_y_span > 0.0) {
            v.y = (bounding_box.y_min +
                   (v.y - v_y_min) / v_y_span * bb_y_span) *
                  voxel_spacing_mm;
        } else if (v_y_span == 0.0) {
            v.y = (v.y + bounding_box.y_min) * voxel_spacing_mm;
        }
        if (v_z_span > 0.0 && bb_z_span > 0.0) {
            v.z = (bounding_box.z_min +
                   (v.z - v_z_min) / v_z_span * bb_z_span) *
                  voxel_spacing_mm;
        } else if (v_z_span == 0.0) {
            v.z = (v.z + bounding_box.z_min) * voxel_spacing_mm;
        }
    }

    // Log restored bounding box.
    double rx_min = vertices[0].x, rx_max = vertices[0].x;
    double ry_min = vertices[0].y, ry_max = vertices[0].y;
    double rz_min = vertices[0].z, rz_max = vertices[0].z;
    for (const auto& v : vertices) {
        rx_min = std::min(rx_min, v.x);
        rx_max = std::max(rx_max, v.x);
        ry_min = std::min(ry_min, v.y);
        ry_max = std::max(ry_max, v.y);
        rz_min = std::min(rz_min, v.z);
        rz_max = std::max(rz_max, v.z);
    }
    std::cout << "[info] restore_physical_coordinates: "
              << "restored BB [" << rx_min << ".." << rx_max
              << "] x [" << ry_min << ".." << ry_max
              << "] x [" << rz_min << ".." << rz_max
              << "] mm\n";
}

}  // namespace mvrmesh
