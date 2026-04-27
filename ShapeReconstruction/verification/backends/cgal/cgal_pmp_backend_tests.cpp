#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/backends/cgal/cgal_pmp_backend.h"
#include "mvrmesh/core/types.h"

#ifndef MVRMESH_CGAL_PMP_ENABLED
#error "CGAL PMP is a required backend in this branch; configure with CGAL instead of compiling without the dependency."
#endif

namespace {

void require(bool cond, const std::string& message) {
    if (!cond) {
        throw std::runtime_error(message);
    }
}

std::vector<mvrmesh::Vec3> tetra_vertices() {
    return {
        mvrmesh::Vec3{0.0, 0.0, 0.0},
        mvrmesh::Vec3{1.0, 0.0, 0.0},
        mvrmesh::Vec3{0.0, 1.0, 0.0},
        mvrmesh::Vec3{0.0, 0.0, 1.0},
    };
}

std::vector<mvrmesh::Face> tetra_faces() {
    return {
        mvrmesh::Face{0, 2, 1},
        mvrmesh::Face{0, 1, 3},
        mvrmesh::Face{1, 2, 3},
        mvrmesh::Face{2, 0, 3},
    };
}

void test_cgal_pmp_backend_availability_contract() {
    const mvrmesh::CgalPmpResult result =
        mvrmesh::run_cgal_pmp_backend(tetra_vertices(), tetra_faces(), mvrmesh::CgalPmpOptions{});

    require(result.success, "CGAL-enabled build should process the closed tetrahedron");
    require(result.output_vertex_count > 0, "CGAL-enabled build should produce vertices");
    require(result.output_face_count > 0, "CGAL-enabled build should produce faces");
    require(result.input_vertex_count == 4, "CGAL result should preserve input vertex count");
    require(result.input_face_count == 4, "CGAL result should preserve input face count");
}

void test_cgal_options_validation() {
    mvrmesh::CgalPmpOptions options;
    options.target_edge_length = -1.0;
    const mvrmesh::CgalPmpResult result =
        mvrmesh::run_cgal_pmp_backend(tetra_vertices(), tetra_faces(), options);

    require(!result.success, "Invalid target edge length should fail");
    require(
        result.diagnostic.find("target edge length") != std::string::npos,
        "Invalid target edge length diagnostic should be explicit"
    );
}

}  // namespace

int main() {
    try {
        test_cgal_pmp_backend_availability_contract();
        test_cgal_options_validation();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] cgal pmp backend tests passed\n";
    return 0;
}
