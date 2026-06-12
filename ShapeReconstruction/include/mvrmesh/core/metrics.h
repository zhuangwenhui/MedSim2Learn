#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Validity diagnostics for a triangle surface mesh: element and defect counts
// (degenerate/duplicate faces; boundary, non-manifold, and inconsistently
// wound edges), face-connected component count (isolated vertices ignored),
// total surface area, and the vertex bounding box.
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
    MeshBoundingBox bounding_box;
};

// A face with area <= degeneracy_epsilon counts as degenerate.
SurfaceMetrics compute_surface_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double degeneracy_epsilon = 1e-12
);

// Returns the metrics as a pretty-printed JSON object string (two-space indent,
// 17 significant digits, trailing newline).
std::string metrics_to_json(const SurfaceMetrics& metrics);

}  // namespace mvrmesh
