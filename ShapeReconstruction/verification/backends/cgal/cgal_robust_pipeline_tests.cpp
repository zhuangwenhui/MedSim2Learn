#include <cmath>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/backends/cgal/cgal_robust_pipeline.h"
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

}  // namespace

int main() {
    try {
        test_repair_clean_tetrahedron_no_change();
        test_repair_removes_duplicate_vertices();
        test_repair_removes_degenerate_face();
        test_repair_fills_simple_quadrilateral_hole();
        test_repair_throws_on_empty_after_repair();
        test_repair_throws_on_out_of_range_index();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] cgal_robust_pipeline_tests (stage 1) passed\n";
    return 0;
}
