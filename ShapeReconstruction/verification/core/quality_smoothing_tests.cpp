#include <cmath>
#include <iostream>
#include <algorithm>
#include <cctype>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "test_helpers.h"

#include "mvrmesh/core/compaction.h"
#include "mvrmesh/core/reconstruction.h"
#include "mvrmesh/core/reconstruction_pipeline.h"
#include "mvrmesh/core/metrics.h"
#include "mvrmesh/core/quality_metrics.h"
#include "mvrmesh/core/surface_acceptance.h"
#include "mvrmesh/core/smoothing.h"

namespace {

using mvrmesh::test::require;
using mvrmesh::test::near;
using mvrmesh::test::require_vec3_near;

// Shared tetrahedron fixture used by multiple tests.
const std::vector<mvrmesh::Vec3> kTetraVertices{
    {0.0, 0.0, 0.0}, {1.0, 0.0, 0.0}, {0.0, 1.0, 0.0}, {0.0, 0.0, 1.0}};
const std::vector<mvrmesh::Face> kTetraFaces{
    {0, 2, 1}, {0, 1, 3}, {1, 2, 3}, {2, 0, 3}};

bool all_vertices_are_referenced(const std::vector<mvrmesh::Face>& faces, std::size_t vertex_count) {
    if (vertex_count == 0) {
        return true;
    }
    std::vector<bool> referenced(vertex_count, false);
    for (const mvrmesh::Face& face : faces) {
        for (int idx : face) {
            if (idx < 0 || static_cast<std::size_t>(idx) >= vertex_count) {
                return false;
            }
            referenced[static_cast<std::size_t>(idx)] = true;
        }
    }
    return std::all_of(referenced.begin(), referenced.end(), [](bool hit) { return hit; });
}

double vector_norm(const mvrmesh::Vec3& v) {
    return std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
}

template <typename Fn>
void require_throws_runtime_error(Fn&& fn, const char* message) {
    bool threw = false;
    try {
        fn();
    } catch (const std::runtime_error&) {
        threw = true;
    }
    require(threw, message);
}

template <typename Fn>
void require_throws_invalid_argument(Fn&& fn, const char* message) {
    bool threw = false;
    try {
        fn();
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    require(threw, message);
}

template <typename Fn>
void require_throws_invalid_argument_contains(
    Fn&& fn,
    const std::string& expected_substring,
    const char* message
) {
    bool threw = false;
    try {
        fn();
    } catch (const std::invalid_argument& ex) {
        threw = true;
        require(
            std::string(ex.what()).find(expected_substring) != std::string::npos,
            message
        );
    }
    require(threw, message);
}

void test_equilateral_triangle_quality() {
    const double h = std::sqrt(3.0) * 0.5;
    std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.5, h, 0.0},
    };
    std::vector<mvrmesh::Face> faces{
        {0, 1, 2},
    };

    const mvrmesh::MeshQualityMetrics q = mvrmesh::compute_mesh_quality_metrics(vertices, faces);

    require(q.edge_length.count == 3, "edge stats should see 3 unique edges");
    require(near(q.edge_length.mean, 1.0), "equilateral mean edge length should be 1");
    require(near(q.edge_length.coefficient_of_variation, 0.0), "equilateral edge CV should be 0");
    require(near(q.face_area.mean, std::sqrt(3.0) * 0.25), "equilateral area should match");
    require(near(q.min_angle_degrees.mean, 60.0, 1e-8), "equilateral min angle should be 60 degrees");
    require(q.aspect_ratio.mean < 1.2, "equilateral aspect ratio should be close to 1");
}

void test_shape_comparison_identical_mesh_zero_drift() {
    std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    std::vector<mvrmesh::Face> faces{
        {0, 1, 2},
    };

    const mvrmesh::ShapeComparisonMetrics s =
        mvrmesh::compare_shape_to_reference(vertices, faces, vertices, faces);

    require(near(s.centroid_drift, 0.0), "identical centroid drift should be zero");
    require(near(s.bbox_diag_delta, 0.0), "identical bbox diag delta should be zero");
    require(near(s.surface_area_delta_ratio, 0.0), "identical area delta should be zero");
    require(near(s.vertex_to_reference_distance.max, 0.0), "identical sampled distance should be zero");
}

void test_degenerate_aspect_ratio_is_infinite() {
    std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {2.0, 0.0, 0.0},
    };
    std::vector<mvrmesh::Face> faces{{0, 1, 2}};

    const mvrmesh::MeshQualityMetrics q = mvrmesh::compute_mesh_quality_metrics(vertices, faces);

    require(!std::isfinite(q.aspect_ratio.max), "degenerate triangle aspect ratio should be inf");
}

void test_flipped_adjacent_face_normals_produce_high_dihedral_angle() {
    std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    std::vector<mvrmesh::Face> faces{
        {0, 1, 2},
        {2, 1, 0},
    };

    const mvrmesh::MeshQualityMetrics q = mvrmesh::compute_mesh_quality_metrics(vertices, faces);
    require(q.dihedral_angle_degrees.count >= 1, "flip test should expose shared edge angle");
    require(q.dihedral_angle_degrees.max > 179.0, "flipped adjacent normals should report near-180 degree angle");
}

void test_empty_shapes_do_not_crash_and_count_zero() {
    const mvrmesh::ShapeComparisonMetrics s = mvrmesh::compare_shape_to_reference(
        {},
        {},
        {},
        {}
    );
    require(s.vertex_to_reference_distance.count == 0, "empty candidate/reference should yield zero forward distance samples");
    require(s.reference_to_vertex_distance.count == 0, "empty candidate/reference should yield zero reverse distance samples");
    require(s.symmetric_vertex_distance.count == 0, "empty candidate/reference should yield zero symmetric distance samples");
    require(near(s.bbox_diag_delta, 0.0), "empty candidate/reference should keep zero bbox delta");
    require(near(s.bbox_diag_abs_delta, 0.0), "empty candidate/reference should keep zero bbox abs delta");
}

void test_compare_shape_to_reference_invalid_empty_candidate_throws() {
    const std::vector<mvrmesh::Vec3> current_vertices{};
    const std::vector<mvrmesh::Face> current_faces{{0, 1, 2}};
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> reference_faces{{0, 1, 2}};

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::compare_shape_to_reference(
                current_vertices,
                current_faces,
                reference_vertices,
                reference_faces
            );
        },
        "empty candidate vertices with non-empty candidate faces should throw runtime_error"
    );
}

void test_compare_shape_to_reference_invalid_empty_reference_throws() {
    const std::vector<mvrmesh::Vec3> current_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> current_faces{{0, 1, 2}};
    const std::vector<mvrmesh::Vec3> reference_vertices{};
    const std::vector<mvrmesh::Face> reference_faces{{0, 1, 2}};

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::compare_shape_to_reference(
                current_vertices,
                current_faces,
                reference_vertices,
                reference_faces
            );
        },
        "empty reference vertices with non-empty reference faces should throw runtime_error"
    );
}

void test_empty_candidate_with_reference_has_forward_zero_and_symmetric_samples() {
    const std::vector<mvrmesh::Vec3> current_vertices{};
    const std::vector<mvrmesh::Face> current_faces{};
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> reference_faces{{0, 1, 2}};

    const mvrmesh::ShapeComparisonMetrics s = mvrmesh::compare_shape_to_reference(
        current_vertices,
        current_faces,
        reference_vertices,
        reference_faces
    );

    require(s.vertex_to_reference_distance.count == 0, "empty candidate should have zero forward distance samples");
    require(s.reference_to_vertex_distance.count == reference_vertices.size(),
            "reference-to-candidate should emit samples when candidate is missing");
    require(s.symmetric_vertex_distance.count == reference_vertices.size(),
            "symmetric distance should include reverse samples");
}

void test_nonfinite_aspect_ratio_json_to_null() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {2.0, 0.0, 0.0},
    };
    const std::vector<mvrmesh::Face> faces{{0, 1, 2}};

    const mvrmesh::MeshQualityMetrics q = mvrmesh::compute_mesh_quality_metrics(vertices, faces);
    const std::string qjson = mvrmesh::mesh_quality_to_json(q, 2);

    require(q.aspect_ratio.count == 1, "degenerate mesh should produce non-empty aspect_ratio stats");
    require(qjson.find("\"aspect_ratio\"") != std::string::npos, "aspect_ratio key should exist");
    require(qjson.find("\"min\": null") != std::string::npos, "min should serialize as null for non-finite");
    require(qjson.find("\"max\": null") != std::string::npos, "max should serialize as null for non-finite");
    require(qjson.find("\"mean\": null") != std::string::npos, "mean should serialize as null for non-finite");
    require(qjson.find("\"rms\": null") != std::string::npos, "rms should serialize as null for non-finite");
    require(qjson.find("\"standard_deviation\": null") != std::string::npos,
            "standard_deviation should serialize as null for non-finite");
    require(qjson.find("\"coefficient_of_variation\": null") != std::string::npos,
            "coefficient_of_variation should serialize as null for non-finite");

    std::string qjson_lower = qjson;
    std::transform(
        qjson_lower.begin(),
        qjson_lower.end(),
        qjson_lower.begin(),
        [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); }
    );
    require(qjson_lower.find("inf") == std::string::npos, "non-finite stats should serialize as null, not inf");
    require(qjson_lower.find("nan") == std::string::npos, "non-finite stats should serialize as null, not nan");
}

void test_shape_comparison_json_handles_inf_as_null() {
    const std::vector<mvrmesh::Vec3> current_vertices{};
    const std::vector<mvrmesh::Face> current_faces{};
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> reference_faces{{0, 1, 2}};

    const mvrmesh::ShapeComparisonMetrics s = mvrmesh::compare_shape_to_reference(
        current_vertices,
        current_faces,
        reference_vertices,
        reference_faces
    );

    const std::string sjson = mvrmesh::shape_comparison_to_json(s, 2);
    require(sjson.find("\"reference_to_vertex_distance\"") != std::string::npos,
            "shape comparison json should include reference_to_vertex_distance");
    require(sjson.find("\"symmetric_vertex_distance\"") != std::string::npos,
            "shape comparison json should include symmetric_vertex_distance");

    require(s.reference_to_vertex_distance.count == reference_vertices.size(),
            "reference_to_vertex_distance should include samples for missing candidate");
    require(s.symmetric_vertex_distance.count >= s.reference_to_vertex_distance.count,
            "symmetric distance should include reference side samples");
    require(!std::isfinite(s.reference_to_vertex_distance.mean), "reference_to_vertex_distance mean should be non-finite");

    std::string sjson_lower = sjson;
    std::transform(
        sjson_lower.begin(),
        sjson_lower.end(),
        sjson_lower.begin(),
        [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); }
    );
    require(sjson_lower.find("inf") == std::string::npos, "shape comparison json should serialize non-finite as null");
    require(sjson_lower.find("nan") == std::string::npos, "shape comparison json should serialize non-finite as null");

    require(sjson.find("\"mean\": null") != std::string::npos || sjson.find("\"max\": null") != std::string::npos,
            "shape comparison json should include null for non-finite fields");
}

void test_asymmetric_geometry_is_exposed_in_directional_or_symmetric_distance() {
    std::vector<mvrmesh::Vec3> current_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    std::vector<mvrmesh::Face> current_faces{
        {0, 1, 2},
    };

    std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
        {10.0, 10.0, 0.0},
    };
    std::vector<mvrmesh::Face> reference_faces{
        {0, 1, 2},
        {0, 1, 3},
    };

    const mvrmesh::ShapeComparisonMetrics s =
        mvrmesh::compare_shape_to_reference(current_vertices, current_faces, reference_vertices, reference_faces);

    require(s.reference_to_vertex_distance.max > 0.0, "reference-to-candidate direction should detect far geometry");
    require(
        s.reference_to_vertex_distance.max > s.vertex_to_reference_distance.max,
        "reference-to-candidate direction should expose larger drift"
    );
    require(s.vertex_to_reference_distance.max < s.reference_to_vertex_distance.max, "asymmetry should be directional");
}

void test_taubin_preserves_boundary_when_requested() {
    std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {1.0, 1.0, 0.0},
        {0.0, 1.0, 0.0},
        {0.5, 0.5, 0.2},
    };
    std::vector<mvrmesh::Face> faces{
        {0, 1, 4},
        {1, 2, 4},
        {2, 3, 4},
        {3, 0, 4},
    };

    const std::vector<mvrmesh::Vec3> smoothed =
        mvrmesh::taubin_smooth(vertices, faces, 2, 0.5, -0.53, true);

    require_vec3_near(smoothed[0], vertices[0], "boundary vertex 0 should stay fixed");
    require_vec3_near(smoothed[1], vertices[1], "boundary vertex 1 should stay fixed");
    require_vec3_near(smoothed[2], vertices[2], "boundary vertex 2 should stay fixed");
    require_vec3_near(smoothed[3], vertices[3], "boundary vertex 3 should stay fixed");
    const mvrmesh::Vec3 interior_delta{
        smoothed[4].x - vertices[4].x,
        smoothed[4].y - vertices[4].y,
        smoothed[4].z - vertices[4].z,
    };
    require(vector_norm(interior_delta) > 1e-6, "interior vertex should move by a non-trivial amount");
}

void test_taubin_rejects_duplicate_index_face() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> faces{
        {0, 1, 1},
    };

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::taubin_smooth(vertices, faces, 1, 0.5, -0.53, false);
        },
        "duplicate index in smoothing face should throw runtime_error"
    );
}

void test_taubin_rejects_zero_area_face() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {2.0, 0.0, 0.0},
    };
    const std::vector<mvrmesh::Face> faces{
        {0, 1, 2},
    };

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::taubin_smooth(vertices, faces, 1, 0.5, -0.53, false);
        },
        "zero-area smoothing face should throw runtime_error"
    );
}

void test_taubin_zero_iterations_is_identity() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> faces{
        {0, 1, 2},
    };

    const std::vector<mvrmesh::Vec3> smoothed =
        mvrmesh::taubin_smooth(vertices, faces, 0, 0.5, -0.53, false);

    require(smoothed.size() == vertices.size(), "zero-iteration smoothing should keep vertex count");
    require_vec3_near(smoothed[0], vertices[0], "zero-iteration vertex 0 should be unchanged");
    require_vec3_near(smoothed[1], vertices[1], "zero-iteration vertex 1 should be unchanged");
    require_vec3_near(smoothed[2], vertices[2], "zero-iteration vertex 2 should be unchanged");
}

void test_projection_to_degenerate_reference_triangle_works() {
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {2.0, 0.0, 0.0},
    };
    const std::vector<mvrmesh::Face> reference_faces{{0, 1, 2}};
    const std::vector<mvrmesh::Vec3> moved{{0.25, 1.0, 0.0}};

    const std::vector<mvrmesh::Vec3> projected =
        mvrmesh::project_vertices_to_surface(moved, reference_vertices, reference_faces);

    require(projected.size() == 1, "degenerate-reference projection should preserve vertex count");
    require(near(projected[0].x, 0.25), "degenerate-reference projection should fall back to closest line point x");
    require(near(projected[0].y, 0.0), "degenerate-reference projection should snap to reference line y=0");
    require(near(projected[0].z, 0.0), "degenerate-reference projection should snap to line z=0");
}

void test_projection_returns_to_reference_plane() {
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> reference_faces{{0, 1, 2}};
    const std::vector<mvrmesh::Vec3> moved{{0.25, 0.25, 1.0}};

    const std::vector<mvrmesh::Vec3> projected =
        mvrmesh::project_vertices_to_surface(moved, reference_vertices, reference_faces);

    require(projected.size() == 1, "projection should preserve vertex count");
    require(near(projected[0].x, 0.25), "projection x should match closest point");
    require(near(projected[0].y, 0.25), "projection y should match closest point");
    require(near(projected[0].z, 0.0), "projection z should land on plane");
}

void test_projection_with_empty_reference_faces_returns_input() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.2, 0.3, 1.0},
        {-0.1, 0.4, -2.0},
        {0.7, -0.5, 3.0},
    };
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };

    const std::vector<mvrmesh::Vec3> projected =
        mvrmesh::project_vertices_to_surface(vertices, reference_vertices, {});

    require(projected.size() == vertices.size(), "empty reference faces should keep vertex count");
    require_vec3_near(projected[0], vertices[0], "vertex 0 should be unchanged");
    require_vec3_near(projected[1], vertices[1], "vertex 1 should be unchanged");
    require_vec3_near(projected[2], vertices[2], "vertex 2 should be unchanged");
}

void test_projection_invalid_reference_face_throws_runtime_error() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.25, 0.25, 1.0},
    };
    const std::vector<mvrmesh::Vec3> reference_vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> invalid_reference_faces{
        {0, 1, 9},
    };

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::project_vertices_to_surface(vertices, reference_vertices, invalid_reference_faces);
        },
        "invalid reference face index should throw runtime_error"
    );
}

void test_reconstruct_and_remesh_surface_minimal_success() {
    mvrmesh::SdfRemeshOptions options;
    options.sdf_resolution = 8;
    options.target_edge_length = 0.3;
    options.remesh_iterations = 1;

    const mvrmesh::SdfRemeshResult result =
        mvrmesh::reconstruct_and_remesh_surface(kTetraVertices, kTetraFaces, options);

    require(!result.vertices.empty(), "product SDF remesh should emit vertices");
    require(!result.faces.empty(), "product SDF remesh should emit faces");
    require(all_vertices_are_referenced(result.faces, result.vertices.size()),
            "product SDF remesh should not keep unreferenced vertices");
}

void test_reconstruct_and_remesh_surface_rejects_invalid_target() {
    mvrmesh::SdfRemeshOptions options;
    options.target_edge_length = -0.01;

    require_throws_invalid_argument(
        [&]() {
            (void)mvrmesh::reconstruct_and_remesh_surface({}, {}, options);
        },
        "negative product SDF target edge length should throw invalid_argument"
    );
}

void test_reconstruct_surface_sdf_rejects_low_resolution() {
    mvrmesh::SdfReconstructionOptions options;
    options.grid_resolution = 1;

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::reconstruct_surface_sdf(kTetraVertices, kTetraFaces, options);
        },
        "SDF reconstruction should reject grid_resolution < 2"
    );
}

void test_reconstruct_surface_sdf_rejects_grid_resolution_above_maximum() {
    mvrmesh::SdfReconstructionOptions options;
    options.grid_resolution = mvrmesh::kMaxSdfGridResolution + 1;

    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::reconstruct_surface_sdf(kTetraVertices, kTetraFaces, options);
        },
        "SDF reconstruction should reject grid_resolution above maximum limit"
    );
}

void test_reconstruct_surface_sdf_tetrahedron_produces_closed_triangle_mesh() {
    mvrmesh::SdfReconstructionOptions options;
    options.grid_resolution = 12;
    options.padding_ratio = 0.10;

    const mvrmesh::ReconstructedMesh mesh =
        mvrmesh::reconstruct_surface_sdf(kTetraVertices, kTetraFaces, options);

    require(!mesh.vertices.empty(), "SDF reconstruction should emit vertices");
    require(!mesh.faces.empty(), "SDF reconstruction should emit faces");
    require(all_vertices_are_referenced(mesh.faces, mesh.vertices.size()),
            "SDF reconstruction should not emit unreferenced vertices");
    const mvrmesh::SurfaceMetrics surface = mvrmesh::compute_surface_metrics(mesh.vertices, mesh.faces);
    require(surface.degenerate_face_count == 0, "SDF reconstruction should not emit degenerate faces");
    require(surface.boundary_edge_count == 0, "SDF reconstruction should produce closed mesh with no boundary edges");
    require(surface.non_manifold_edge_count == 0, "SDF reconstruction should not emit non-manifold edges");
    require(surface.inconsistent_orientation_edge_count == 0, "SDF reconstruction should produce consistent face orientation");
    require(surface.connected_component_count == 1, "SDF reconstruction should produce a single connected component");
}

void test_surface_acceptance_passes_clean_single_component() {
    mvrmesh::SurfaceMetrics metrics;
    metrics.degenerate_face_count = 0;
    metrics.boundary_edge_count = 0;
    metrics.non_manifold_edge_count = 0;
    metrics.inconsistent_orientation_edge_count = 0;
    metrics.connected_component_count = 1;

    const mvrmesh::SurfaceAcceptanceResult result =
        mvrmesh::evaluate_surface_acceptance(metrics);

    require(result.accepted, "clean closed surface should pass acceptance gate");
    require(result.failure_reason.empty(), "accepted surface should not have a failure reason");
}

void test_surface_acceptance_rejects_open_surface() {
    mvrmesh::SurfaceMetrics metrics;
    metrics.connected_component_count = 1;
    metrics.boundary_edge_count = 8;

    const mvrmesh::SurfaceAcceptanceResult result =
        mvrmesh::evaluate_surface_acceptance(metrics);

    require(!result.accepted, "open surface should fail acceptance gate");
    require(result.failure_reason.find("boundary_edge_count=8") != std::string::npos,
            "failure reason should include boundary edge count");
}

void test_surface_acceptance_rejects_non_manifold_edges() {
    mvrmesh::SurfaceMetrics metrics;
    metrics.connected_component_count = 1;
    metrics.non_manifold_edge_count = 3;

    const mvrmesh::SurfaceAcceptanceResult result =
        mvrmesh::evaluate_surface_acceptance(metrics);

    require(!result.accepted, "non-manifold surface should fail acceptance gate");
    require(result.failure_reason.find("non_manifold_edge_count=3") != std::string::npos,
            "failure reason should include non-manifold edge count");
}

void test_surface_acceptance_rejects_inconsistent_orientation() {
    mvrmesh::SurfaceMetrics metrics;
    metrics.connected_component_count = 1;
    metrics.inconsistent_orientation_edge_count = 136;

    const mvrmesh::SurfaceAcceptanceResult result =
        mvrmesh::evaluate_surface_acceptance(metrics);

    require(!result.accepted, "inconsistent orientation should fail acceptance gate");
    require(
        result.failure_reason.find("inconsistent_orientation_edge_count=136") != std::string::npos,
        "failure reason should include inconsistent orientation count"
    );
}

void test_surface_acceptance_rejects_fragmented_components() {
    mvrmesh::SurfaceMetrics metrics;
    metrics.connected_component_count = 2;

    const mvrmesh::SurfaceAcceptanceResult result =
        mvrmesh::evaluate_surface_acceptance(metrics);

    require(!result.accepted, "multiple components should fail acceptance gate");
    require(result.failure_reason.find("connected_component_count=2") != std::string::npos,
            "failure reason should include connected component count");
}

void test_fem_budget_classification() {
    mvrmesh::FemBudgetOptions options;
    options.max_recommended_v_tet = 3000;
    options.max_review_v_tet = 5000;

    require(
        mvrmesh::fem_budget_classification_to_string(mvrmesh::FemBudgetClassification::PressureFailed)
        == "pressure_failed",
        "pressure_failed should serialize as pressure_failed"
    );
    require(
        mvrmesh::fem_budget_classification_to_string(mvrmesh::FemBudgetClassification::Recommended)
        == "recommended",
        "Recommended should serialize as recommended"
    );
    require(
        mvrmesh::fem_budget_classification_to_string(mvrmesh::FemBudgetClassification::Review)
        == "review",
        "Review should serialize as review"
    );
    require(
        mvrmesh::fem_budget_classification_to_string(mvrmesh::FemBudgetClassification::OverBudget)
        == "over_budget",
        "OverBudget should serialize as over_budget"
    );

    const mvrmesh::FemBudgetResult failed = mvrmesh::classify_fem_budget(false, 0, options);
    require(failed.classification == mvrmesh::FemBudgetClassification::PressureFailed,
            "tetgen failure should be pressure_failed");
    require(mvrmesh::fem_budget_classification_to_string(failed.classification) == "pressure_failed",
            "tetgen failure classification should serialize correctly");
    require(!failed.recommended, "pressure_failed should not be recommended");
    require(!failed.reviewable, "pressure_failed should not be reviewable");

    const mvrmesh::FemBudgetResult recommended = mvrmesh::classify_fem_budget(true, 3000, options);
    require(recommended.classification == mvrmesh::FemBudgetClassification::Recommended,
            "v_tet=3000 should be recommended");
    require(recommended.recommended, "recommended should set recommended=true");
    require(recommended.reviewable, "recommended should set reviewable=true");
    require(mvrmesh::fem_budget_classification_to_string(recommended.classification) == "recommended",
            "recommended should serialize correctly");

    const mvrmesh::FemBudgetResult review = mvrmesh::classify_fem_budget(true, 5000, options);
    require(review.classification == mvrmesh::FemBudgetClassification::Review,
            "v_tet=5000 should be review");
    require(!review.recommended, "review should not set recommended=true");
    require(review.reviewable, "review should set reviewable=true");
    require(mvrmesh::fem_budget_classification_to_string(review.classification) == "review",
            "review should serialize correctly");

    const mvrmesh::FemBudgetResult over_budget = mvrmesh::classify_fem_budget(true, 5001, options);
    require(over_budget.classification == mvrmesh::FemBudgetClassification::OverBudget,
            "v_tet>5000 should be over_budget");
    require(!over_budget.recommended, "over_budget should not be recommended");
    require(!over_budget.reviewable, "over_budget should not be reviewable");
    require(mvrmesh::fem_budget_classification_to_string(over_budget.classification) == "over_budget",
            "over_budget should serialize correctly");

    mvrmesh::FemBudgetOptions invalid_options;
    invalid_options.max_recommended_v_tet = 3000;
    invalid_options.max_review_v_tet = 2000;
    require_throws_runtime_error(
        [&]() {
            (void)mvrmesh::classify_fem_budget(true, 2500, invalid_options);
        },
        "invalid thresholds should throw runtime_error"
    );

    const mvrmesh::FemBudgetResult boundary = mvrmesh::classify_fem_budget(true, 2500, options);
    require(boundary.classification == mvrmesh::FemBudgetClassification::Recommended,
            "v_tet=2500 should be recommended");
}

void test_compact_mesh_to_referenced_vertices_removes_isolated_vertices() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
        {0.0, 0.0, 1.0},
        {9.0, 9.0, 9.0},
    };
    const std::vector<mvrmesh::Face> faces{
        {0, 1, 2},
        {0, 3, 1},
        {0, 2, 3},
        {1, 3, 2},
    };

    const std::pair<std::vector<mvrmesh::Vec3>, std::vector<mvrmesh::Face>> compacted =
        mvrmesh::compact_mesh_to_referenced_vertices(vertices, faces);

    require(compacted.first.size() == 4, "compacted mesh should drop isolated vertex");
    require(compacted.second.size() == faces.size(), "compacted mesh should preserve face count");
    require(
        all_vertices_are_referenced(compacted.second, compacted.first.size()),
        "all compacted vertices should be referenced by at least one face"
    );
}

void test_compact_mesh_to_referenced_vertices_preserves_face_vertex_order() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},  // 0
        {1.0, 0.0, 0.0},  // 1
        {0.0, 1.0, 0.0},  // 2
        {9.0, 9.0, 9.0},  // 3 (isolated)
    };
    const std::vector<mvrmesh::Face> faces{
        {2, 0, 1},
        {2, 1, 0},
    };

    const std::pair<std::vector<mvrmesh::Vec3>, std::vector<mvrmesh::Face>> compacted =
        mvrmesh::compact_mesh_to_referenced_vertices(vertices, faces);

    require(compacted.first.size() == 3, "compacted mesh should keep only referenced vertices");
    require(compacted.second.size() == 2, "compacted mesh should preserve face count");
    require(compacted.second[0] == mvrmesh::Face{0, 1, 2}, "first remapped face order should be preserved");
    require(compacted.second[1] == mvrmesh::Face{0, 2, 1}, "second remapped face order should be preserved");
}

}  // namespace

int main() {
    try {
        test_equilateral_triangle_quality();
        test_shape_comparison_identical_mesh_zero_drift();
        test_degenerate_aspect_ratio_is_infinite();
        test_flipped_adjacent_face_normals_produce_high_dihedral_angle();
        test_empty_shapes_do_not_crash_and_count_zero();
        test_compare_shape_to_reference_invalid_empty_candidate_throws();
        test_compare_shape_to_reference_invalid_empty_reference_throws();
        test_empty_candidate_with_reference_has_forward_zero_and_symmetric_samples();
        test_nonfinite_aspect_ratio_json_to_null();
        test_shape_comparison_json_handles_inf_as_null();
        test_asymmetric_geometry_is_exposed_in_directional_or_symmetric_distance();
        test_taubin_preserves_boundary_when_requested();
        test_taubin_rejects_duplicate_index_face();
        test_taubin_rejects_zero_area_face();
        test_taubin_zero_iterations_is_identity();
        test_projection_returns_to_reference_plane();
        test_projection_to_degenerate_reference_triangle_works();
        test_projection_with_empty_reference_faces_returns_input();
        test_projection_invalid_reference_face_throws_runtime_error();
        test_reconstruct_and_remesh_surface_minimal_success();
        test_reconstruct_and_remesh_surface_rejects_invalid_target();
        test_reconstruct_surface_sdf_rejects_low_resolution();
        test_reconstruct_surface_sdf_rejects_grid_resolution_above_maximum();
        test_reconstruct_surface_sdf_tetrahedron_produces_closed_triangle_mesh();
        test_surface_acceptance_passes_clean_single_component();
        test_surface_acceptance_rejects_open_surface();
        test_surface_acceptance_rejects_non_manifold_edges();
        test_surface_acceptance_rejects_inconsistent_orientation();
        test_surface_acceptance_rejects_fragmented_components();
        test_fem_budget_classification();
        test_compact_mesh_to_referenced_vertices_removes_isolated_vertices();
        test_compact_mesh_to_referenced_vertices_preserves_face_vertex_order();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] quality/smoothing tests passed\n";
    return 0;
}
