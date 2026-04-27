#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/backends/gmsh/gmsh_evaluator.h"
#include "mvrmesh/core/types.h"

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

void test_gmsh_evaluation_tetrahedralizes_closed_surface() {
    const mvrmesh::GmshEvaluationResult result =
        mvrmesh::evaluate_gmsh(tetra_vertices(), tetra_faces(), mvrmesh::GmshEvaluationOptions{});

    require(result.success, "Gmsh should tetrahedralize the closed tetrahedron");
    require(result.output_vertex_count >= 4, "Gmsh output should include vertices");
    require(result.output_tetra_count >= 1, "Gmsh output should include tetrahedra");
    require(result.input_vertex_count == 4, "Gmsh result should preserve input vertex count");
    require(result.input_face_count == 4, "Gmsh result should preserve input face count");
}

void test_gmsh_rejects_out_of_range_face_index() {
    std::vector<mvrmesh::Face> faces = tetra_faces();
    faces[0][2] = 99;

    const mvrmesh::GmshEvaluationResult result =
        mvrmesh::evaluate_gmsh(tetra_vertices(), faces, mvrmesh::GmshEvaluationOptions{});

    require(!result.success, "Gmsh evaluator should reject out-of-range face indices");
    require(
        result.diagnostic.find("out of range") != std::string::npos,
        "Gmsh diagnostic should mention out-of-range indices"
    );
}

void test_gmsh_json_includes_counts() {
    mvrmesh::GmshEvaluationResult result;
    result.success = true;
    result.algorithm3d = 10;
    result.input_vertex_count = 4;
    result.input_face_count = 4;
    result.output_vertex_count = 5;
    result.output_tetra_count = 2;
    result.output_boundary_face_count = 4;
    result.steiner_vertex_count = 1;
    result.output_vertices = tetra_vertices();
    result.output_tetrahedra = {mvrmesh::Tet{0, 1, 2, 3}};

    const std::string json = mvrmesh::gmsh_evaluation_to_json(result);
    require(json.find("\"algorithm3d\": 10") != std::string::npos, "JSON should include algorithm3d");
    require(json.find("\"output_tetra_count\": 2") != std::string::npos, "JSON should include tetra count");
    require(json.find("\"steiner_vertex_count\": 1") != std::string::npos, "JSON should include steiner count");
    require(json.find("\"total_volume\":") != std::string::npos, "JSON should include total volume");
    require(json.find("\"min_tetra_quality\":") != std::string::npos, "JSON should include min tetra quality");
    require(json.find("\"mean_tetra_quality\":") != std::string::npos, "JSON should include mean tetra quality");
}

}  // namespace

int main() {
    try {
        test_gmsh_evaluation_tetrahedralizes_closed_surface();
        test_gmsh_rejects_out_of_range_face_index();
        test_gmsh_json_includes_counts();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] gmsh evaluator tests passed\n";
    return 0;
}
