#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "test_helpers.h"

#include "mvrmesh/core/io.h"
#include "mvrmesh/core/mesh_postprocess.h"
#include "mvrmesh/core/types.h"

namespace {

using mvrmesh::test::require;
using mvrmesh::test::near;

#ifndef MVRMESH_FIXTURE_DIR
#error "MVRMESH_FIXTURE_DIR must be defined by CMake"
#endif

const std::filesystem::path kFixtureDir = MVRMESH_FIXTURE_DIR;

void test_parse_mvr_with_bounding_box() {
    const auto parsed = mvrmesh::parse_mvr(kFixtureDir / "tiny_surface_with_bb.mvr");

    require(parsed.bounding_box.valid, "BB should be valid when header present");
    require(near(parsed.bounding_box.x_min, 10.0), "x_min should be 10.0");
    require(near(parsed.bounding_box.x_max, 266.0), "x_max should be 266.0");
    require(near(parsed.bounding_box.y_min, 20.0), "y_min should be 20.0");
    require(near(parsed.bounding_box.y_max, 276.0), "y_max should be 276.0");
    require(near(parsed.bounding_box.z_min, 30.0), "z_min should be 30.0");
    require(near(parsed.bounding_box.z_max, 286.0), "z_max should be 286.0");

    require(parsed.vertices.size() == 4, "vertices should still parse correctly");
    require(parsed.triangles.size() == 4, "triangles should still parse correctly");
}

void test_parse_mvr_without_bounding_box() {
    const auto parsed = mvrmesh::parse_mvr(kFixtureDir / "tiny_surface.mvr");

    require(!parsed.bounding_box.valid, "BB should be invalid when header absent");
    require(parsed.vertices.size() == 4, "vertices should parse without BB");
    require(parsed.triangles.size() == 4, "triangles should parse without BB");
}

void test_quality_fix_breaks_coplanarity() {
    std::vector<mvrmesh::Vec3> vertices = {
        {0.0, 0.0, 0.0},  // 0: original
        {2.0, 0.0, 0.0},  // 1: original
        {0.0, 2.0, 0.0},  // 2: original
        {1.0, 0.0, 0.0},  // 3: midpoint 0-1
        {1.0, 1.0, 0.0},  // 4: midpoint 1-2
        {0.0, 1.0, 0.0},  // 5: midpoint 2-0
    };
    std::vector<mvrmesh::Face> faces = {
        {0, 3, 5},  // bottom-left
        {3, 1, 4},  // bottom-right
        {5, 4, 2},  // top
        {3, 4, 5},  // center
    };

    for (const auto& v : vertices) {
        require(v.z == 0.0, "pre-condition: all vertices should be coplanar at z=0");
    }

    mvrmesh::mesh_quality_fix(vertices, faces);

    bool found_non_coplanar = false;
    for (const auto& v : vertices) {
        if (v.z != 0.0) {
            found_non_coplanar = true;
            break;
        }
    }
    require(found_non_coplanar, "perturbation should break exact coplanarity");

    for (std::size_t i = 0; i < vertices.size(); ++i) {
        require(std::abs(vertices[i].z) < 1e-3,
                "perturbation magnitude should be negligible");
    }

    require(faces.size() == 4, "face count should be preserved");
    require(vertices.size() == 6, "vertex count should be preserved");
}

void test_quality_fix_eliminates_degenerate_triangle() {
    std::vector<mvrmesh::Vec3> vertices = {
        {0.0, 0.0, 0.0},  // 0
        {0.5, 0.0, 0.0},  // 1: collinear with 0 and 2
        {1.0, 0.0, 0.0},  // 2
        {0.0, 1.0, 0.0},  // 3
    };
    std::vector<mvrmesh::Face> faces = {
        {0, 1, 2},  // degenerate (collinear)
        {0, 2, 3},  // valid
    };

    const int fixed = mvrmesh::mesh_quality_fix(vertices, faces);

    for (std::size_t i = 0; i < faces.size(); ++i) {
        const auto& f = faces[i];
        const auto& a = vertices[static_cast<std::size_t>(f[0])];
        const auto& b = vertices[static_cast<std::size_t>(f[1])];
        const auto& c = vertices[static_cast<std::size_t>(f[2])];
        double cx = (b.y - a.y) * (c.z - a.z) - (b.z - a.z) * (c.y - a.y);
        double cy = (b.z - a.z) * (c.x - a.x) - (b.x - a.x) * (c.z - a.z);
        double cz = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
        double area = 0.5 * std::sqrt(cx * cx + cy * cy + cz * cz);
        require(area > 1e-15,
                "all remaining faces should have non-zero area after fix");
    }

    require(fixed >= 0, "fixed count should be non-negative");
}

void test_quality_fix_deterministic() {
    std::vector<mvrmesh::Vec3> v1 = {
        {0.0, 0.0, 0.0}, {1.0, 0.0, 0.0}, {0.0, 1.0, 0.0},
    };
    std::vector<mvrmesh::Face> f1 = {{0, 1, 2}};

    std::vector<mvrmesh::Vec3> v2 = v1;
    std::vector<mvrmesh::Face> f2 = f1;

    mvrmesh::mesh_quality_fix(v1, f1);
    mvrmesh::mesh_quality_fix(v2, f2);

    for (std::size_t i = 0; i < v1.size(); ++i) {
        require(v1[i].x == v2[i].x, "deterministic: x should match");
        require(v1[i].y == v2[i].y, "deterministic: y should match");
        require(v1[i].z == v2[i].z, "deterministic: z should match");
    }
}

void test_restore_physical_coordinates_known_values() {
    std::vector<mvrmesh::Vec3> vertices = {
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
        {0.0, 0.0, 1.0},
    };

    mvrmesh::BoundingBox bb;
    bb.x_min = 10.0; bb.x_max = 266.0;
    bb.y_min = 20.0; bb.y_max = 276.0;
    bb.z_min = 30.0; bb.z_max = 286.0;
    bb.valid = true;

    mvrmesh::restore_physical_coordinates(vertices, bb, 1.0);

    mvrmesh::test::require_vec3_near(vertices[0], {10.0, 20.0, 30.0},
                                      "vertex 0 restored", 1e-9);
    mvrmesh::test::require_vec3_near(vertices[1], {266.0, 20.0, 30.0},
                                      "vertex 1 restored", 1e-9);
    mvrmesh::test::require_vec3_near(vertices[2], {10.0, 276.0, 30.0},
                                      "vertex 2 restored", 1e-9);
    mvrmesh::test::require_vec3_near(vertices[3], {10.0, 20.0, 286.0},
                                      "vertex 3 restored", 1e-9);
}

void test_restore_physical_coordinates_with_voxel_spacing() {
    std::vector<mvrmesh::Vec3> vertices = {
        {0.0, 0.0, 0.0},
        {1.0, 0.0, 0.0},
    };

    mvrmesh::BoundingBox bb;
    bb.x_min = 10.0; bb.x_max = 266.0;
    bb.y_min = 20.0; bb.y_max = 276.0;
    bb.z_min = 30.0; bb.z_max = 286.0;
    bb.valid = true;

    mvrmesh::restore_physical_coordinates(vertices, bb, 0.5);

    mvrmesh::test::require_vec3_near(vertices[0], {5.0, 10.0, 15.0},
                                      "vertex 0 with spacing", 1e-9);
    mvrmesh::test::require_vec3_near(vertices[1], {133.0, 10.0, 15.0},
                                      "vertex 1 with spacing", 1e-9);
}

void test_restore_skips_invalid_bb() {
    std::vector<mvrmesh::Vec3> vertices = {
        {0.5, 0.5, 0.5},
    };
    const mvrmesh::Vec3 original = vertices[0];

    mvrmesh::BoundingBox bb;  // valid = false (default)

    mvrmesh::restore_physical_coordinates(vertices, bb, 1.0);

    require(vertices[0].x == original.x, "should not modify x with invalid BB");
    require(vertices[0].y == original.y, "should not modify y with invalid BB");
    require(vertices[0].z == original.z, "should not modify z with invalid BB");
}

void test_restore_handles_zero_extent_axis() {
    std::vector<mvrmesh::Vec3> vertices = {
        {0.0, 0.0, 0.5},
        {1.0, 1.0, 0.5},
    };

    mvrmesh::BoundingBox bb;
    bb.x_min = 0.0; bb.x_max = 100.0;
    bb.y_min = 0.0; bb.y_max = 200.0;
    bb.z_min = 0.0; bb.z_max = 50.0;
    bb.valid = true;

    mvrmesh::restore_physical_coordinates(vertices, bb, 1.0);

    require(near(vertices[0].x, 0.0), "v0.x restored");
    require(near(vertices[1].x, 100.0), "v1.x restored");
    require(near(vertices[0].y, 0.0), "v0.y restored");
    require(near(vertices[1].y, 200.0), "v1.y restored");
    require(near(vertices[0].z, 0.5), "v0.z should be unchanged (zero extent)");
    require(near(vertices[1].z, 0.5), "v1.z should be unchanged (zero extent)");
}

}  // namespace

int main() {
    return mvrmesh::test::run_tests({
        {test_parse_mvr_with_bounding_box,    "test_parse_mvr_with_bounding_box"},
        {test_parse_mvr_without_bounding_box, "test_parse_mvr_without_bounding_box"},
        {test_quality_fix_breaks_coplanarity, "test_quality_fix_breaks_coplanarity"},
        {test_quality_fix_eliminates_degenerate_triangle, "test_quality_fix_eliminates_degenerate_triangle"},
        {test_quality_fix_deterministic,      "test_quality_fix_deterministic"},
        {test_restore_physical_coordinates_known_values, "test_restore_physical_coordinates_known_values"},
        {test_restore_physical_coordinates_with_voxel_spacing, "test_restore_physical_coordinates_with_voxel_spacing"},
        {test_restore_skips_invalid_bb,       "test_restore_skips_invalid_bb"},
        {test_restore_handles_zero_extent_axis, "test_restore_handles_zero_extent_axis"},
    });
}
