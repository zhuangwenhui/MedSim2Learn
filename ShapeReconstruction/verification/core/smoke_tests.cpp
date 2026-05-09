#include <cmath>
#include <exception>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/core/algorithms.h"
#include "mvrmesh/core/io.h"
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

std::size_t count_vertex_near(
    const std::vector<mvrmesh::Vec3>& vertices,
    std::size_t first,
    const mvrmesh::Vec3& expected,
    double epsilon = 1e-12
) {
    std::size_t count = 0;
    for (std::size_t i = first; i < vertices.size(); ++i) {
        if (
            std::abs(vertices[i].x - expected.x) < epsilon &&
            std::abs(vertices[i].y - expected.y) < epsilon &&
            std::abs(vertices[i].z - expected.z) < epsilon
        ) {
            ++count;
        }
    }
    return count;
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

void test_build_surface_uniform_subdivide() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> triangles{Face{0, 1, 2}};
    const std::vector<mvrmesh::Tet> tets;

    mvrmesh::BuildOptions options;
    options.uniform_subdivide = true;
    options.uniform_iterations = 1;

    const mvrmesh::BuildResult result = mvrmesh::build_surface(vertices, triangles, tets, options);
    require(result.mode == mvrmesh::SurfaceMode::UniformSubdivide, "Uniform subdivision should set mode");
    require(result.vertices.size() == 6, "Uniform subdivision should add midpoint vertices");
    require(result.faces.size() == 4, "Uniform subdivision should split one triangle into four faces");
}

void test_build_surface_uniform_taubin_smooth() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Face> triangles{
        Face{0, 2, 1},
        Face{0, 1, 3},
        Face{1, 2, 3},
        Face{2, 0, 3},
    };
    const std::vector<mvrmesh::Tet> tets;

    mvrmesh::BuildOptions uniform_options;
    uniform_options.uniform_subdivide = true;
    uniform_options.uniform_iterations = 1;

    mvrmesh::BuildOptions taubin_options = uniform_options;
    taubin_options.taubin_smooth = true;
    taubin_options.taubin_iterations = 2;

    const mvrmesh::BuildResult uniform = mvrmesh::build_surface(
        vertices,
        triangles,
        tets,
        uniform_options
    );
    const mvrmesh::BuildResult taubin = mvrmesh::build_surface(
        vertices,
        triangles,
        tets,
        taubin_options
    );

    require(taubin.mode == mvrmesh::SurfaceMode::UniformTaubin,
            "Uniform Taubin should set mode");
    require(taubin.vertices.size() == uniform.vertices.size(),
            "Uniform Taubin should keep uniform vertex count");
    require(taubin.faces.size() == uniform.faces.size(),
            "Uniform Taubin should keep uniform face count");

    bool moved_vertex = false;
    for (std::size_t i = 0; i < taubin.vertices.size(); ++i) {
        const Vec3 delta{
            taubin.vertices[i].x - uniform.vertices[i].x,
            taubin.vertices[i].y - uniform.vertices[i].y,
            taubin.vertices[i].z - uniform.vertices[i].z,
        };
        if (std::sqrt(delta.x * delta.x + delta.y * delta.y + delta.z * delta.z) > 1e-12) {
            moved_vertex = true;
            break;
        }
    }
    require(moved_vertex, "Uniform Taubin should alter vertex positions after subdivision");
}

void test_build_surface_taubin_requires_uniform_subdivide() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
    };
    const std::vector<mvrmesh::Face> triangles{{0, 1, 2}};
    const std::vector<mvrmesh::Tet> tets;

    mvrmesh::BuildOptions options;
    options.taubin_smooth = true;

    bool threw = false;
    try {
        (void)mvrmesh::build_surface(vertices, triangles, tets, options);
    } catch (const std::runtime_error& ex) {
        threw = std::string(ex.what()).find("--taubin-smooth requires --uniform-subdivide")
            != std::string::npos;
    }
    require(threw, "Taubin smoothing should require uniform subdivision");
}

void test_build_surface_sdf_reconstruct() {
    const std::vector<mvrmesh::Vec3> vertices{
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
        {0.0, 0.0, 1.0},
    };
    const std::vector<mvrmesh::Face> triangles{
        {0, 2, 1},
        {0, 1, 3},
        {1, 2, 3},
        {2, 0, 3},
    };

    mvrmesh::BuildOptions options;
    options.sdf_reconstruct = true;
    options.sdf_resolution = 8;
    options.sdf_target_edge_length = 0.3;
    options.sdf_remesh_iterations = 1;

    const mvrmesh::BuildResult result =
        mvrmesh::build_surface(vertices, triangles, {}, options);

    require(result.mode == mvrmesh::SurfaceMode::SdfReconstruct,
            "SDF reconstruction should set product mode");
    require(!result.vertices.empty(), "SDF reconstruction should emit vertices");
    require(!result.faces.empty(), "SDF reconstruction should emit faces");
}

void test_build_surface_sdf_reconstruct_conflicts_with_uniform() {
    mvrmesh::BuildOptions options;
    options.sdf_reconstruct = true;
    options.uniform_subdivide = true;

    bool threw = false;
    try {
        (void)mvrmesh::build_surface({}, {}, {}, options);
    } catch (const std::runtime_error& ex) {
        threw = std::string(ex.what()).find("--sdf-reconstruct conflicts with --uniform-subdivide")
            != std::string::npos;
    }
    require(threw, "SDF reconstruction should conflict with uniform subdivision");
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

void test_uniform_subdivide_single_triangle() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{Face{0, 1, 2}};

    const auto subdivided = mvrmesh::uniform_subdivide(vertices, faces, 1);
    require(subdivided.first.size() == 6, "Uniform subdivision should add three midpoint vertices");
    require(subdivided.second.size() == 4, "Uniform subdivision should split one triangle into four faces");

    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.5, 0.0, 0.0}) == 1, "Subdivision should add midpoint on edge 0-1");
    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.5, 0.5, 0.0}) == 1, "Subdivision should add midpoint on edge 1-2");
    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.0, 0.5, 0.0}) == 1, "Subdivision should add midpoint on edge 2-0");
}

void test_uniform_subdivide_reuses_shared_edge_midpoint() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{1.0, 1.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{0, 2, 3},
    };

    const auto subdivided = mvrmesh::uniform_subdivide(vertices, faces, 1);
    require(subdivided.first.size() == 9, "Two triangles sharing one edge should create five unique midpoints");
    require(subdivided.second.size() == 8, "Two triangles should become eight triangles");

    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.5, 0.0, 0.0}) == 1, "Subdivision should add midpoint on edge 0-1");
    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{1.0, 0.5, 0.0}) == 1, "Subdivision should add midpoint on edge 1-2");
    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.5, 1.0, 0.0}) == 1, "Subdivision should add midpoint on edge 2-3");
    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.0, 0.5, 0.0}) == 1, "Subdivision should add midpoint on edge 3-0");
    require(count_vertex_near(subdivided.first, vertices.size(), Vec3{0.5, 0.5, 0.0}) == 1, "Shared diagonal midpoint should be reused once");
}

void test_uniform_subdivide_second_iteration_counts() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{Face{0, 1, 2}};

    const auto subdivided = mvrmesh::uniform_subdivide(vertices, faces, 2);
    require(subdivided.first.size() == 15, "Two uniform iterations on one triangle should create fifteen vertices");
    require(subdivided.second.size() == 16, "Two uniform iterations on one triangle should create sixteen faces");
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

void test_read_ply_round_trip() {
    std::vector<mvrmesh::Vec3> orig_v = {
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
        {0.0, 0.0, 1.0},
    };
    std::vector<mvrmesh::Face> orig_f = {
        {0, 1, 2}, {0, 1, 3}, {0, 2, 3}, {1, 2, 3},
    };

    const std::filesystem::path tmp =
        std::filesystem::temp_directory_path() / "mvrmesh_test_round_trip.ply";
    mvrmesh::write_ply(tmp, orig_v, orig_f);

    std::vector<mvrmesh::Vec3> read_v;
    std::vector<mvrmesh::Face> read_f;
    mvrmesh::read_ply(tmp, read_v, read_f);

    require(read_v.size() == orig_v.size(), "read_ply should preserve vertex count");
    require(read_f.size() == orig_f.size(), "read_ply should preserve face count");
    for (std::size_t i = 0; i < orig_v.size(); ++i) {
        require(std::abs(read_v[i].x - orig_v[i].x) < 1e-6, "x coord round-trip");
        require(std::abs(read_v[i].y - orig_v[i].y) < 1e-6, "y coord round-trip");
        require(std::abs(read_v[i].z - orig_v[i].z) < 1e-6, "z coord round-trip");
    }
    for (std::size_t i = 0; i < orig_f.size(); ++i) {
        require(read_f[i][0] == orig_f[i][0], "face vertex 0 round-trip");
        require(read_f[i][1] == orig_f[i][1], "face vertex 1 round-trip");
        require(read_f[i][2] == orig_f[i][2], "face vertex 2 round-trip");
    }
    std::filesystem::remove(tmp);
}

}  // namespace

int main() {
    try {
        test_normalize_faces_indices();
        test_boundary_faces_single_tet();
        test_build_surface_uses_tet_boundary_without_triangles();
        test_build_surface_uniform_subdivide();
        test_build_surface_uniform_taubin_smooth();
        test_build_surface_taubin_requires_uniform_subdivide();
        test_build_surface_sdf_reconstruct();
        test_build_surface_sdf_reconstruct_conflicts_with_uniform();
        test_adaptive_single_triangle_split();
        test_uniform_subdivide_single_triangle();
        test_uniform_subdivide_reuses_shared_edge_midpoint();
        test_uniform_subdivide_second_iteration_counts();
        test_surface_metrics_single_triangle();
        test_surface_metrics_degenerate_face();
        test_surface_metrics_closed_tetrahedron();
        test_surface_metrics_duplicate_and_orientation_issues();
        test_surface_metrics_non_manifold_edge();
        test_surface_metrics_disconnected_components();
        test_metrics_json_includes_quality_fields();
        test_read_ply_round_trip();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }

    std::cout << "[ok] smoke tests passed\n";
    return 0;
}
