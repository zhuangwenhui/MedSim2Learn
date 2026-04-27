#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct BoundingBox {
    bool valid = false;
    Vec3 min;
    Vec3 max;
};

struct SurfaceMetrics {
    std::size_t vertex_count = 0;
    std::size_t face_count = 0;
    std::size_t degenerate_face_count = 0;
    std::size_t duplicate_face_count = 0;
    std::size_t boundary_edge_count = 0;
    std::size_t non_manifold_edge_count = 0;
    std::size_t inconsistent_orientation_edge_count = 0;
    std::size_t connected_component_count = 0;
    double degeneracy_epsilon = 0.0;
    double surface_area = 0.0;
    BoundingBox bounding_box;
};

struct TetraMeshMetrics {
    std::size_t tetra_count = 0;
    std::size_t degenerate_tetra_count = 0;
    double total_volume = 0.0;
    double min_tetra_volume = 0.0;
    double max_tetra_volume = 0.0;
    double mean_tetra_volume = 0.0;
    double min_tetra_quality = 0.0;
    double max_tetra_quality = 0.0;
    double mean_tetra_quality = 0.0;
};

SurfaceMetrics compute_surface_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double degeneracy_epsilon = 1e-12
);

TetraMeshMetrics compute_tetra_mesh_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Tet>& tetrahedra
);

std::string metrics_to_json(const SurfaceMetrics& metrics);

void write_metrics_json(const std::filesystem::path& path, const SurfaceMetrics& metrics);

}  // namespace mvrmesh
