#include <cmath>
#include <exception>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/core/algorithms.h"
#include "mvrmesh/core/metrics.h"
#include "mvrmesh/core/pipeline.h"
#include "mvrmesh/core/topology.h"
#include "mvrmesh/core/types.h"

namespace {

void require(bool cond, const std::string& message) {
    if (!cond) {
        throw std::runtime_error(message);
    }
}


void test_normalize_faces_indices() {
    using mvrmesh::Face;

    const std::vector<Face> one_based{Face{1, 2, 3}, Face{3, 4, 5}};
    const std::vector<Face> normalized = mvrmesh::normalize_faces_indices(one_based, 5);
    require(normalized[0] == Face{0, 1, 2}, "1-based faces should normalize to 0-based");
    require(normalized[1] == Face{2, 3, 4}, "1-based faces should normalize to 0-based");

    const std::vector<Face> zero_based{Face{0, 1, 2}, Face{2, 3, 4}};
    const std::vector<Face> kept = mvrmesh::normalize_faces_indices(zero_based, 5);
    require(kept == zero_based, "0-based faces should remain unchanged");
}

void test_boundary_faces_single_tet() {
    using mvrmesh::Tet;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Tet> tets{Tet{0, 1, 2, 3}};
    const std::vector<mvrmesh::Face> faces = mvrmesh::boundary_faces_from_tets(vertices, tets);
    require(faces.size() == 4, "Single tetrahedron should produce 4 boundary faces");
}

void test_build_surface_uses_tet_boundary_without_triangles() {
    using mvrmesh::Tet;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<mvrmesh::Face> triangles;
    const std::vector<Tet> tets{Tet{0, 1, 2, 3}};
    const mvrmesh::BuildResult result = mvrmesh::build_surface(vertices, triangles, tets, mvrmesh::BuildOptions{});
    require(result.mode == mvrmesh::SurfaceMode::DirectSurface, "Tet boundary surface should use direct surface mode");
    require(result.vertices.size() == 4, "Tet boundary surface should keep input vertices");
    require(result.faces.size() == 4, "Single tetrahedron boundary surface should produce 4 faces");
}

void test_adaptive_single_triangle_split() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{Face{0, 1, 2}};

    const auto remeshed = mvrmesh::adaptive_remesh(vertices, faces, 1, 1.0);
    require(remeshed.first.size() == 6, "One fully split triangle should add 3 midpoint vertices");
    require(remeshed.second.size() == 4, "One fully split triangle should create 4 faces");
}

void test_python_round_behavior_for_face_selection() {
    using mvrmesh::Face;

    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{3, 4, 5},
        Face{6, 7, 8},
        Face{9, 10, 11},
        Face{12, 13, 14},
    };
    const std::vector<double> curvature(15, 1.0);
    const std::set<mvrmesh::Edge> edges = mvrmesh::select_split_edges_by_curvature(faces, curvature, 0.5);

    // Python round(5 * 0.5) = round(2.5) = 2 (ties-to-even), so we expect 2 faces selected.
    require(edges.size() == 6, "Split edge count should reflect Python-style tie-to-even rounding");
}

void test_surface_metrics_single_triangle() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{Face{0, 1, 2}};

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces);
    require(metrics.vertex_count == 3, "Metrics should report vertex count");
    require(metrics.face_count == 1, "Metrics should report face count");
    require(metrics.degenerate_face_count == 0, "Single right triangle should not be degenerate");
    require(metrics.boundary_edge_count == 3, "Single triangle should have 3 boundary edges");
    require(metrics.non_manifold_edge_count == 0, "Single triangle should not have non-manifold edges");
    require(metrics.connected_component_count == 1, "Single triangle should be one component");
    require(std::abs(metrics.surface_area - 0.5) < 1e-12, "Single right triangle area should be 0.5");
    require(metrics.bounding_box.valid, "Non-empty vertices should produce valid bounding box");
    require(
        metrics.bounding_box.min.x == 0.0 &&
        metrics.bounding_box.min.y == 0.0 &&
        metrics.bounding_box.min.z == 0.0,
        "Bounding box min should match vertices"
    );
    require(
        metrics.bounding_box.max.x == 1.0 &&
        metrics.bounding_box.max.y == 1.0 &&
        metrics.bounding_box.max.z == 0.0,
        "Bounding box max should match vertices"
    );
}

void test_tetra_mesh_metrics_regular_tetrahedron_quality() {
    using mvrmesh::Tet;
    using mvrmesh::Vec3;

    const double sqrt3 = std::sqrt(3.0);
    const double sqrt_two_thirds = std::sqrt(2.0 / 3.0);
    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.5, sqrt3 / 2.0, 0.0},
        Vec3{0.5, sqrt3 / 6.0, sqrt_two_thirds},
    };
    const std::vector<Tet> tets{Tet{0, 1, 2, 3}};

    const mvrmesh::TetraMeshMetrics metrics = mvrmesh::compute_tetra_mesh_metrics(vertices, tets);
    require(metrics.tetra_count == 1, "Tetra metrics should report tetra count");
    require(metrics.degenerate_tetra_count == 0, "Regular tetrahedron should not be degenerate");
    require(std::abs(metrics.total_volume - (std::sqrt(2.0) / 12.0)) < 1e-12, "Regular tetra volume should match analytic value");
    require(std::abs(metrics.min_tetra_volume - metrics.total_volume) < 1e-12, "Single tetra min volume should match total volume");
    require(std::abs(metrics.max_tetra_volume - metrics.total_volume) < 1e-12, "Single tetra max volume should match total volume");
    require(std::abs(metrics.mean_tetra_volume - metrics.total_volume) < 1e-12, "Single tetra mean volume should match total volume");
    require(std::abs(metrics.min_tetra_quality - 1.0) < 1e-12, "Regular tetra mean-ratio quality should be 1");
    require(std::abs(metrics.max_tetra_quality - 1.0) < 1e-12, "Regular tetra max quality should be 1");
    require(std::abs(metrics.mean_tetra_quality - 1.0) < 1e-12, "Regular tetra mean quality should be 1");
}

void test_tetra_mesh_metrics_degenerate_tetrahedron_quality() {
    using mvrmesh::Tet;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{2.0, 0.0, 0.0},
        Vec3{3.0, 0.0, 0.0},
    };
    const std::vector<Tet> tets{Tet{0, 1, 2, 3}};

    const mvrmesh::TetraMeshMetrics metrics = mvrmesh::compute_tetra_mesh_metrics(vertices, tets);
    require(metrics.tetra_count == 1, "Degenerate tetra metrics should report tetra count");
    require(metrics.degenerate_tetra_count == 1, "Collinear tetrahedron should be degenerate");
    require(metrics.total_volume == 0.0, "Degenerate tetrahedron volume should be zero");
    require(metrics.min_tetra_quality == 0.0, "Degenerate tetrahedron min quality should be zero");
    require(metrics.max_tetra_quality == 0.0, "Degenerate tetrahedron max quality should be zero");
    require(metrics.mean_tetra_quality == 0.0, "Degenerate tetrahedron mean quality should be zero");
}

void test_surface_metrics_degenerate_face() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{2.0, 0.0, 0.0},
    };
    const std::vector<Face> faces{Face{0, 1, 2}};

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces);
    require(metrics.degenerate_face_count == 1, "Collinear triangle should be degenerate");
    require(metrics.surface_area == 0.0, "Collinear triangle area should be zero");
}

void test_surface_metrics_closed_tetrahedron() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Face> faces{
        Face{0, 2, 1},
        Face{0, 1, 3},
        Face{1, 2, 3},
        Face{2, 0, 3},
    };

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces);
    require(metrics.boundary_edge_count == 0, "Closed tetrahedron should have no boundary edges");
    require(metrics.non_manifold_edge_count == 0, "Closed tetrahedron should have no non-manifold edges");
    require(metrics.inconsistent_orientation_edge_count == 0, "Closed tetrahedron should have consistent half-edges");
    require(metrics.duplicate_face_count == 0, "Closed tetrahedron should have no duplicate faces");
    require(metrics.connected_component_count == 1, "Closed tetrahedron should be one component");
}

void test_surface_metrics_duplicate_and_orientation_issues() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{2, 0, 1},
    };

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces);
    require(metrics.duplicate_face_count == 1, "Duplicate face count should count repeated triangle keys");
    require(
        metrics.inconsistent_orientation_edge_count == 3,
        "Duplicate same-orientation triangles should flag all half-edges"
    );
}

void test_surface_metrics_non_manifold_edge() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
        Vec3{0.0, -1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{1, 0, 3},
        Face{0, 1, 4},
    };

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces);
    require(metrics.non_manifold_edge_count == 1, "Three incident triangles should flag one non-manifold edge");
}

void test_surface_metrics_disconnected_components() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{10.0, 0.0, 0.0},
        Vec3{11.0, 0.0, 0.0},
        Vec3{10.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{3, 4, 5},
    };

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces);
    require(metrics.connected_component_count == 2, "Two separate triangles should be two components");
    require(metrics.boundary_edge_count == 6, "Two separate triangles should have six boundary edges");
}

void test_metrics_json_includes_quality_fields() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{2, 0, 1},
    };

    const mvrmesh::SurfaceMetrics metrics = mvrmesh::compute_surface_metrics(vertices, faces, 1e-8);
    const std::string json = mvrmesh::metrics_to_json(metrics);
    require(json.find("\"duplicate_face_count\": 1") != std::string::npos, "JSON should include duplicate face count");
    require(
        json.find("\"inconsistent_orientation_edge_count\": 3") != std::string::npos,
        "JSON should include orientation issue count"
    );
    require(json.find("\"degeneracy_epsilon\":") != std::string::npos, "JSON should include degeneracy epsilon");
}

}  // namespace

int main() {
    try {
        test_normalize_faces_indices();
        test_boundary_faces_single_tet();
        test_build_surface_uses_tet_boundary_without_triangles();
        test_adaptive_single_triangle_split();
        test_python_round_behavior_for_face_selection();
        test_surface_metrics_single_triangle();
        test_tetra_mesh_metrics_regular_tetrahedron_quality();
        test_tetra_mesh_metrics_degenerate_tetrahedron_quality();
        test_surface_metrics_degenerate_face();
        test_surface_metrics_closed_tetrahedron();
        test_surface_metrics_duplicate_and_orientation_issues();
        test_surface_metrics_non_manifold_edge();
        test_surface_metrics_disconnected_components();
        test_metrics_json_includes_quality_fields();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }

    std::cout << "[ok] smoke tests passed\n";
    return 0;
}
