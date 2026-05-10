#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "test_helpers.h"

#include "mvrmesh/pressure/pressure_evaluator.h"
#include "mvrmesh/core/types.h"

namespace {

using mvrmesh::test::require;

void test_deformsim_pressure_tetrahedralizes_closed_surface() {
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

    const mvrmesh::DeformSimPressureResult result =
        mvrmesh::evaluate_deformsim_pressure(vertices, faces, mvrmesh::DeformSimPressureOptions{});

    require(result.success, "TetGen-enabled build should tetrahedralize the closed tetrahedron");
    require(result.tetgen_output_vertex_count >= 4, "TetGen output should include vertices");
    require(result.tetgen_output_tetra_count >= 1, "TetGen output should include tetrahedra");
    require(result.tetgen_output_boundary_face_count >= 4, "TetGen output should include boundary faces");
    require(result.estimated_unique_line_count >= 6, "Pressure estimate should count tetra mesh lines");
    require(
        result.line_capacity_nnode_times_32 == result.tetgen_output_vertex_count * 32,
        "Pressure estimate should match DeformSim line capacity heuristic"
    );
}

void test_deformsim_pressure_json_matches_diagnostic_shape() {
    mvrmesh::DeformSimPressureResult result;
    result.success = true;
    result.switches = "pYQ";
    result.input_ply = "D:/tmp/tiny.ply";
    result.stage = "tetgen_output_validated";
    result.diagnostic = "TetGen completed; diagnostic did not run DeformSim post-processing.";
    result.surface_vertex_count = 4;
    result.surface_face_count = 4;
    result.object_node_count = 4;
    result.object_triangle_count = 4;
    result.bounding_box_valid = true;
    result.bounding_box_min = mvrmesh::Vec3{0.0, 0.0, 0.0};
    result.bounding_box_max = mvrmesh::Vec3{1.0, 1.0, 1.0};
    result.tetgen_firstnumber = 1;
    result.tetgen_output_vertex_count = 4;
    result.tetgen_output_tetra_count = 1;
    result.tetgen_output_boundary_face_count = 4;
    result.estimated_unique_line_count = 6;
    result.line_capacity_nnode_times_32 = 128;
    result.estimated_matrix_node_count = 4;
    result.estimated_matrix_order = 12;
    result.estimated_dense_k_l_bytes = 2304;
    result.estimated_element_scratch_bytes = 1728;
    result.output_vertices = {
        mvrmesh::Vec3{0.0, 0.0, 0.0},
        mvrmesh::Vec3{1.0, 0.0, 0.0},
        mvrmesh::Vec3{0.0, 1.0, 0.0},
        mvrmesh::Vec3{0.0, 0.0, 1.0},
    };
    result.output_tetrahedra = {mvrmesh::Tet{0, 1, 2, 3}};

    const std::string json = mvrmesh::deformsim_pressure_to_json(result);
    require(json.find("\"input_ply\": \"D:/tmp/tiny.ply\"") != std::string::npos, "JSON should include PLY handoff path");
    require(json.find("\"stage\": \"tetgen_output_validated\"") != std::string::npos, "JSON should include diagnostic stage");
    require(json.find("\"surface_vertex_count\": 4") != std::string::npos, "JSON should include surface vertex count");
    require(json.find("\"object_node_count\": 4") != std::string::npos, "JSON should include DeformSim object node count");
    require(json.find("\"bounding_box_valid\": true") != std::string::npos, "JSON should include bounding box validity");
    require(json.find("\"tetgen_output_tetra_count\": 1") != std::string::npos, "JSON should include tetra count");
    require(json.find("\"estimated_unique_line_count\": 6") != std::string::npos, "JSON should include unique line estimate");
    require(json.find("\"line_capacity_nnode_times_32\": 128") != std::string::npos, "JSON should include line capacity");
    require(json.find("\"estimated_dense_k_l_bytes\": 2304") != std::string::npos, "JSON should include dense matrix estimate");
}

void test_deformsim_pressure_json_rejects_out_of_range_boundary_face_index() {
    mvrmesh::DeformSimPressureResult result;
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
        (void)mvrmesh::deformsim_pressure_to_json(result);
    } catch (const std::runtime_error& ex) {
        threw = std::string(ex.what()).find("Boundary face index out of range") != std::string::npos;
    }
    require(threw, "TetGen JSON should reject out-of-range boundary face indices");
}

}  // namespace

int main() {
    try {
        test_deformsim_pressure_tetrahedralizes_closed_surface();
        test_deformsim_pressure_json_matches_diagnostic_shape();
        test_deformsim_pressure_json_rejects_out_of_range_boundary_face_index();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }
    std::cout << "[ok] tetgen evaluator tests passed\n";
    return 0;
}
