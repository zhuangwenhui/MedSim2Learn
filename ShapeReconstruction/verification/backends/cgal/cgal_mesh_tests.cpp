#include <cmath>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/backends/cgal/cgal_mesh.h"
#include "mvrmesh/core/types.h"

namespace {

void require(bool cond, const std::string& message) {
    if (!cond) {
        throw std::runtime_error(message);
    }
}

bool message_contains(const std::string& msg, const std::string& needle) {
    return msg.find(needle) != std::string::npos;
}

// ---------- Stage 1: repair_polygon_soup_step ----------

void test_repair_clean_tetrahedron_no_change() {
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

    const auto io = mvrmesh::detail::repair_polygon_soup_step(vertices, faces);
    require(io.report.removed_duplicate_vertices == 0, "no duplicates expected");
    require(io.report.removed_degenerate_faces == 0, "no degenerate faces expected");
    require(io.report.holes_filled == 0, "no holes expected");
    require(io.report.oriented_successfully, "tetrahedron must be orientable");
    require(io.vertices.size() == 4, "vertex count preserved");
    require(io.faces.size() == 4, "face count preserved");
}

void test_repair_only_preserves_simple_triangle() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 1, 2},
    };

    const auto result = mvrmesh::run_cgal_repair_only(vertices, faces);
    require(result.vertices.size() == 3, "repair-only should preserve simple triangle vertices");
    require(result.faces.size() == result.repair_report.output_face_count,
            "repair report face count should match output");
    require(result.repair_report.input_face_count == 1,
            "repair report should record input faces");
    require(!result.faces.empty(), "repair-only should produce at least one face");
    require(result.remesh_report.input_vertex_count == 0,
            "repair-only should not run remesh");
    require(result.remesh_report.input_face_count == 0,
            "repair-only should not run remesh");
    require(result.remesh_report.output_vertex_count == 0,
            "repair-only should not run remesh");
    require(result.remesh_report.output_face_count == 0,
            "repair-only should not run remesh");
    require(result.remesh_report.sharp_edges_detected == 0,
            "repair-only should not run remesh");
}

void test_repair_removes_duplicate_vertices() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    // 5 vertices, indices 0 and 4 coincide; 4 faces still describe a closed tetrahedron
    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
        Vec3{0.0, 0.0, 0.0},  // duplicate of index 0
    };
    const std::vector<Face> faces{
        Face{0, 2, 1},
        Face{4, 1, 3},  // uses duplicate index 4
        Face{1, 2, 3},
        Face{2, 0, 3},
    };

    const auto io = mvrmesh::detail::repair_polygon_soup_step(vertices, faces);
    require(io.report.removed_duplicate_vertices >= 1, "at least one duplicate must be removed");
}

void test_repair_removes_degenerate_face() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    // 5 faces: 4 of a tetrahedron + 1 with a repeated vertex (degenerate)
    const std::vector<Face> faces{
        Face{0, 2, 1},
        Face{0, 1, 3},
        Face{1, 2, 3},
        Face{2, 0, 3},
        Face{0, 0, 1},  // degenerate: repeated index
    };

    const auto io = mvrmesh::detail::repair_polygon_soup_step(vertices, faces);
    require(io.report.removed_degenerate_faces >= 1, "the degenerate face must be removed");
}

void test_repair_fills_simple_quadrilateral_hole() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    // Unit cube vertices
    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},  // 0
        Vec3{1.0, 0.0, 0.0},  // 1
        Vec3{1.0, 1.0, 0.0},  // 2
        Vec3{0.0, 1.0, 0.0},  // 3
        Vec3{0.0, 0.0, 1.0},  // 4
        Vec3{1.0, 0.0, 1.0},  // 5
        Vec3{1.0, 1.0, 1.0},  // 6
        Vec3{0.0, 1.0, 1.0},  // 7
    };
    // 5 faces of cube (10 triangles), missing the +z (top) face -> a 4-edge hole
    const std::vector<Face> faces{
        // -z bottom
        Face{0, 2, 1}, Face{0, 3, 2},
        // -y front
        Face{0, 1, 5}, Face{0, 5, 4},
        // +x right
        Face{1, 2, 6}, Face{1, 6, 5},
        // +y back
        Face{2, 3, 7}, Face{2, 7, 6},
        // -x left
        Face{3, 0, 4}, Face{3, 4, 7},
        // +z top deliberately omitted -> hole bounded by (4,5,6,7)
    };

    const auto io = mvrmesh::detail::repair_polygon_soup_step(vertices, faces);
    require(io.report.holes_filled == 1, "exactly one hole expected");
    require(io.faces.size() >= 12, "hole filling should add at least 2 triangles (10 + 2 = 12)");
}

void test_repair_throws_on_empty_after_repair() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    // All faces have repeated indices -> all degenerate -> nothing remains after repair
    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 0, 1},
        Face{1, 1, 2},
        Face{2, 2, 0},
    };

    bool threw = false;
    try {
        mvrmesh::detail::repair_polygon_soup_step(vertices, faces);
    } catch (const std::runtime_error& ex) {
        threw = true;
        const std::string msg = ex.what();
        require(message_contains(msg, "step 1"), "message must contain 'step 1'");
        require(message_contains(msg, "nothing remains") || message_contains(msg, "valid surface mesh"),
                "message must indicate nothing remains or assembly failed");
    }
    require(threw, "expected runtime_error on all-degenerate input");
}

void test_repair_throws_on_out_of_range_index() {
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
        Face{99, 1, 3},  // index 99 is out of range
    };

    bool threw = false;
    try {
        mvrmesh::detail::repair_polygon_soup_step(vertices, faces);
    } catch (const std::runtime_error& ex) {
        threw = true;
        const std::string msg = ex.what();
        require(message_contains(msg, "step 1"), "message must contain 'step 1'");
        require(message_contains(msg, "out of range"), "message must contain 'out of range'");
    }
    require(threw, "expected runtime_error on out-of-range index");
}

// ---------- Stage 2: protected_remesh_step ----------

void test_remesh_clean_octahedron_runs() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    // Regular octahedron: 6 vertices, 8 faces
    const std::vector<Vec3> vertices{
        Vec3{ 1.0,  0.0,  0.0},
        Vec3{-1.0,  0.0,  0.0},
        Vec3{ 0.0,  1.0,  0.0},
        Vec3{ 0.0, -1.0,  0.0},
        Vec3{ 0.0,  0.0,  1.0},
        Vec3{ 0.0,  0.0, -1.0},
    };
    const std::vector<Face> faces{
        Face{0, 2, 4}, Face{2, 1, 4}, Face{1, 3, 4}, Face{3, 0, 4},
        Face{2, 0, 5}, Face{1, 2, 5}, Face{3, 1, 5}, Face{0, 3, 5},
    };

    // Threshold 130 deg keeps regular octahedron's ~70.53 deg adjacent-face-normal
    // angle below the sharp threshold (so guard does not fire).
    // Target 0.5 < 4/3 * sqrt(2)/4 ensures isotropic_remeshing actually splits edges
    // instead of leaving the input topology untouched.
    const auto io = mvrmesh::detail::protected_remesh_step(
        vertices, faces, /*sharp_edge_dihedral_degrees=*/130.0, /*target_edge_length=*/0.5,
        /*remesh_iterations=*/2);
    require(io.faces.size() > faces.size(),
            "isotropic_remeshing should add faces by splitting edges");
    require(io.report.target_edge_length_used > 0.0,
            "resolved target edge length must be positive");
}

void test_remesh_target_edge_length_auto_resolves_to_mean() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Face> faces{
        Face{0, 2, 1}, Face{0, 1, 3}, Face{1, 2, 3}, Face{2, 0, 3},
    };

    // Threshold 130 deg keeps the corner-tetrahedron's adjacent-face-normal angles
    // (90 deg between the three right-angle faces, ~125 deg involving the slanted
    // face) below the sharp threshold so the over-constraint guard does not fire.
    const auto io = mvrmesh::detail::protected_remesh_step(
        vertices, faces, 130.0, /*target_edge_length=*/0.0, /*remesh_iterations=*/1);
    // Tetrahedron has 6 unique edges with lengths {1, 1, 1, sqrt2, sqrt2, sqrt2}
    // Mean = (3 * 1 + 3 * sqrt2) / 6 = (1 + sqrt(2)) / 2 ~= 1.2071
    const double expected_mean = (1.0 + std::sqrt(2.0)) / 2.0;
    const double diff = std::abs(io.report.target_edge_length_used - expected_mean);
    require(diff < 1e-6, "auto-resolved target edge length must equal mean of input edges");
}

void test_remesh_detects_sharp_edge_in_flat_bipyramid() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    // Flattened bipyramid: regular octahedron with the two apexes pulled close
    // to the xy equator plane. CGAL's detect_sharp_edges marks border edges as
    // feature by default, so an open "tent" cannot satisfy the assertion at
    // any threshold. A closed bipyramid avoids that pitfall: the 4 equator
    // edges have ~180 deg outward-normal angle (sharp), and the 8 apex-to-
    // equator edges have ~0 deg (not sharp). At threshold 60 deg, sharp_count
    // = 4 < total = 12, so the over-constraint guard does not fire.
    const std::vector<Vec3> vertices{
        Vec3{ 0.3,  0.0,  0.0 },
        Vec3{-0.3,  0.0,  0.0 },
        Vec3{ 0.0,  0.3,  0.0 },
        Vec3{ 0.0, -0.3,  0.0 },
        Vec3{ 0.0,  0.0,  0.02},
        Vec3{ 0.0,  0.0, -0.02},
    };
    const std::vector<Face> faces{
        Face{0, 2, 4}, Face{2, 1, 4}, Face{1, 3, 4}, Face{3, 0, 4},
        Face{2, 0, 5}, Face{1, 2, 5}, Face{3, 1, 5}, Face{0, 3, 5},
    };

    const auto io = mvrmesh::detail::protected_remesh_step(
        vertices, faces, /*sharp_edge_dihedral_degrees=*/60.0,
        /*target_edge_length=*/0.5, /*remesh_iterations=*/1);
    require(io.report.sharp_edges_detected >= 1,
            "flat bipyramid must yield at least one sharp equator edge at threshold 60");
}

void test_remesh_throws_when_all_edges_sharp() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Face> faces{
        Face{0, 2, 1}, Face{0, 1, 3}, Face{1, 2, 3}, Face{2, 0, 3},
    };

    bool threw = false;
    try {
        // Threshold of 1.0 degree -> any non-coplanar edges are flagged
        mvrmesh::detail::protected_remesh_step(
            vertices, faces, /*sharp_edge_dihedral_degrees=*/1.0,
            /*target_edge_length=*/0.0, /*remesh_iterations=*/1);
    } catch (const std::runtime_error& ex) {
        threw = true;
        const std::string msg = ex.what();
        require(message_contains(msg, "step 2"), "message must contain 'step 2'");
        require(message_contains(msg, "every edge"), "message must contain 'every edge'");
    }
    require(threw, "expected runtime_error when threshold flags all edges as sharp");
}

// ---------- Orchestrator: run_cgal_mesh ----------

void test_pipeline_happy_path_tetrahedron() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Face> faces{
        Face{0, 2, 1}, Face{0, 1, 3}, Face{1, 2, 3}, Face{2, 0, 3},
    };

    mvrmesh::CgalMeshOptions opts;
    // Override the 60-deg default: the corner tetrahedron's adjacent-face-normal
    // angles (90 deg between right-angle faces, ~125 deg involving the slanted
    // face) all exceed 60 deg, which would make stage 2's all-edges-sharp guard
    // throw before stage 3 runs. 130 deg matches the threshold used in the
    // stage-2 unit tests for the same fixture.
    opts.sharp_edge_dihedral_degrees = 130.0;
    const auto result = mvrmesh::run_cgal_mesh(vertices, faces, opts);
    require(result.repair_report.oriented_successfully, "repair must succeed");
    require(result.remesh_report.target_edge_length_used > 0.0,
            "remesh must record a positive resolved target edge length");
    require(!result.vertices.empty(), "final mesh must be non-empty");
    require(!result.faces.empty(), "final mesh must be non-empty");
}

void test_pipeline_propagates_step1_failure() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{
        Face{0, 0, 1},
        Face{1, 1, 2},
        Face{2, 2, 0},
    };

    mvrmesh::CgalMeshOptions opts;
    bool threw = false;
    try {
        mvrmesh::run_cgal_mesh(vertices, faces, opts);
    } catch (const std::runtime_error& ex) {
        threw = true;
        const std::string msg = ex.what();
        require(message_contains(msg, "step 1"),
                "orchestrator must propagate stage-1 failure with 'step 1' in message");
    }
    require(threw, "expected step-1 failure to propagate as runtime_error");
}

}  // namespace

int main() {
    try {
        test_repair_clean_tetrahedron_no_change();
        test_repair_only_preserves_simple_triangle();
        test_repair_removes_duplicate_vertices();
        test_repair_removes_degenerate_face();
        test_repair_fills_simple_quadrilateral_hole();
        test_repair_throws_on_empty_after_repair();
        test_repair_throws_on_out_of_range_index();
        test_remesh_clean_octahedron_runs();
        test_remesh_target_edge_length_auto_resolves_to_mean();
        test_remesh_detects_sharp_edge_in_flat_bipyramid();
        test_remesh_throws_when_all_edges_sharp();
        test_pipeline_happy_path_tetrahedron();
        test_pipeline_propagates_step1_failure();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] cgal_mesh_tests (full) passed\n";
    return 0;
}
