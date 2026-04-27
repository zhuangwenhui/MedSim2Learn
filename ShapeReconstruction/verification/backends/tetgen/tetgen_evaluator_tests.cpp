#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/backends/tetgen/tetgen_evaluator.h"
#include "mvrmesh/core/types.h"

#ifndef MVRMESH_TETGEN_ENABLED
#error "TetGen evaluation is required in this branch; configure TetGen sources instead of compiling without the dependency."
#endif

namespace {

void require(bool cond, const std::string& message) {
    if (!cond) {
        throw std::runtime_error(message);
    }
}

void test_tetgen_evaluation_tetrahedralizes_closed_surface() {
    const std::vector<mvrmesh::Vec3> vertices{
        mvrmesh::Vec3{0.0, 0.0, 0.0},
        mvrmesh::Vec3{1.0, 0.0, 0.0},
        mvrmesh::Vec3{0.0, 1.0, 0.0},
        mvrmesh::Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<mvrmesh::Face> faces{
        mvrmesh::Face{0, 2, 1},
        mvrmesh::Face{0, 1, 3},
        mvrmesh::Face{1, 2, 3},
        mvrmesh::Face{2, 0, 3},
    };

    const mvrmesh::TetGenEvaluationResult result =
        mvrmesh::evaluate_tetgen(vertices, faces, mvrmesh::TetGenEvaluationOptions{});

    require(result.success, "TetGen-enabled build should tetrahedralize the closed tetrahedron");
    require(result.output_vertex_count >= 4, "TetGen output should include vertices");
    require(result.output_tetra_count >= 1, "TetGen output should include tetrahedra");
    require(result.output_boundary_face_count >= 4, "TetGen output should include boundary faces");
}

void test_tetgen_evaluation_json_includes_counts() {
    mvrmesh::TetGenEvaluationResult result;
    result.success = true;
    result.switches = "pYQ";
    result.input_vertex_count = 4;
    result.input_face_count = 4;
    result.output_vertex_count = 4;
    result.output_tetra_count = 1;
    result.output_boundary_face_count = 4;
    result.output_vertices = {
        mvrmesh::Vec3{0.0, 0.0, 0.0},
        mvrmesh::Vec3{1.0, 0.0, 0.0},
        mvrmesh::Vec3{0.0, 1.0, 0.0},
        mvrmesh::Vec3{0.0, 0.0, 1.0},
    };
    result.output_tetrahedra = {mvrmesh::Tet{0, 1, 2, 3}};

    const std::string json = mvrmesh::tetgen_evaluation_to_json(result);
    require(json.find("\"switches\": \"pYQ\"") != std::string::npos, "JSON should include switches");
    require(json.find("\"output_tetra_count\": 1") != std::string::npos, "JSON should include tetra count");
    require(json.find("\"total_volume\":") != std::string::npos, "JSON should include total volume");
    require(json.find("\"min_tetra_quality\":") != std::string::npos, "JSON should include min tetra quality");
    require(json.find("\"mean_tetra_quality\":") != std::string::npos, "JSON should include mean tetra quality");
}

void test_tetgen_json_rejects_out_of_range_boundary_face_index() {
    mvrmesh::TetGenEvaluationResult result;
    result.success = true;
    result.switches = "pYQ";
    result.output_vertices = {
        mvrmesh::Vec3{0.0, 0.0, 0.0},
        mvrmesh::Vec3{1.0, 0.0, 0.0},
        mvrmesh::Vec3{0.0, 1.0, 0.0},
        mvrmesh::Vec3{0.0, 0.0, 1.0},
    };
    result.output_tetrahedra = {mvrmesh::Tet{0, 1, 2, 3}};
    result.output_boundary_faces = {mvrmesh::Face{0, 1, 99}};

    bool threw = false;
    try {
        (void)mvrmesh::tetgen_evaluation_to_json(result);
    } catch (const std::runtime_error& ex) {
        threw = std::string(ex.what()).find("Boundary face index out of range") != std::string::npos;
    }
    require(threw, "TetGen JSON should reject out-of-range boundary face indices");
}

}  // namespace

int main() {
    try {
        test_tetgen_evaluation_tetrahedralizes_closed_surface();
        test_tetgen_evaluation_json_includes_counts();
        test_tetgen_json_rejects_out_of_range_boundary_face_index();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] tetgen evaluator tests passed\n";
    return 0;
}
