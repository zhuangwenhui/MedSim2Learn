#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Summary statistics over a set of scalar samples. count == 0 means no samples
// were collected and every other field stays 0. If any sample is NaN, all
// fields except count become NaN; infinite samples leave min/max meaningful but
// turn the moment fields infinite.
struct ScalarStats {
    std::size_t count = 0;
    double min = 0.0;
    double max = 0.0;
    double mean = 0.0;
    double rms = 0.0;
    double standard_deviation = 0.0;
    double coefficient_of_variation = 0.0;
};

// Triangle-quality statistics for one mesh. edge_length covers each undirected
// edge once; min_angle_degrees is the smallest corner angle per face;
// aspect_ratio is longest edge over shortest altitude (infinite for degenerate
// faces).
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

// Geometric agreement between a mesh and a reference mesh. centroid_drift is
// the distance between vertex centroids; bbox_diag_delta is the current-minus-
// reference bounding-box diagonal (signed; the abs variant alongside);
// surface_area_delta_ratio is (current - reference) / reference area. The
// distance stats hold nearest point-to-surface distances in each direction plus
// their pooled symmetric set.
struct ShapeComparisonMetrics {
    double centroid_drift = 0.0;
    double bbox_diag_delta = 0.0;
    double bbox_diag_abs_delta = 0.0;
    double surface_area_delta_ratio = 0.0;
    ScalarStats vertex_to_reference_distance;
    ScalarStats reference_to_vertex_distance;
    ScalarStats symmetric_vertex_distance;
};

// Returns zeroed stats for an empty mesh.
MeshQualityMetrics compute_mesh_quality_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces);

// Measures how far `vertices`/`faces` drifted from the reference mesh.
ShapeComparisonMetrics compare_shape_to_reference(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const std::vector<Vec3>& reference_vertices,
    const std::vector<Face>& reference_faces);

// JSON object serialization; `indent` is the number of spaces per nesting
// level. Non-finite values are emitted as null. No trailing newline.
std::string mesh_quality_to_json(const MeshQualityMetrics& metrics, int indent = 2);
std::string shape_comparison_to_json(const ShapeComparisonMetrics& metrics, int indent = 2);

}  // namespace mvrmesh
