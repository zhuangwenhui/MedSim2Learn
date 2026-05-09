#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct ScalarStats {
    std::size_t count = 0;
    double min = 0.0;
    double max = 0.0;
    double mean = 0.0;
    double rms = 0.0;
    double standard_deviation = 0.0;
    double coefficient_of_variation = 0.0;
};

struct MeshQualityMetrics {
    ScalarStats edge_length;
    ScalarStats face_area;
    ScalarStats min_angle_degrees;
    ScalarStats aspect_ratio;

    // Angle in degrees between neighboring face normals for shared edges that have
    // exactly two incident triangles. Flipped normal orientation can move this
    // toward 180 degrees.
    ScalarStats dihedral_angle_degrees;
};

struct ShapeComparisonMetrics {
    double centroid_drift = 0.0;
    double bbox_diag_delta = 0.0;
    double bbox_diag_abs_delta = 0.0;
    double surface_area_delta_ratio = 0.0;
    ScalarStats vertex_to_reference_distance;
    ScalarStats reference_to_vertex_distance;
    ScalarStats symmetric_vertex_distance;
};

MeshQualityMetrics compute_mesh_quality_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces);

ShapeComparisonMetrics compare_shape_to_reference(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces);

std::string mesh_quality_to_json(const MeshQualityMetrics& metrics, int indent = 2);
std::string shape_comparison_to_json(const ShapeComparisonMetrics& metrics, int indent = 2);

}  // namespace mvrmesh
