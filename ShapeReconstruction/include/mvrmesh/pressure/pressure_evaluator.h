#pragma once

#include <cstddef>
#include <filesystem>
#include <sstream>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Escape a string for embedding inside a JSON string literal. Shared by every
// writer that emits JSON by hand (pressure evaluator and pressure metrics);
// Windows backslash paths in particular must not leak through unescaped.
inline std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
        case '\\':
            out << "\\\\";
            break;
        case '"':
            out << "\\\"";
            break;
        case '\n':
            out << "\\n";
            break;
        case '\r':
            out << "\\r";
            break;
        case '\t':
            out << "\\t";
            break;
        default:
            out << ch;
            break;
        }
    }
    return out.str();
}

struct DeformSimPressureOptions {
    std::string switches = "pYQ";
    std::string input_ply;
    double degeneracy_epsilon = 1e-12;
};

struct DeformSimIndexStats {
    int min_index = 0;
    int max_index = -1;
    std::size_t out_of_range_count = 0;
};

struct DeformSimPressureResult {
    bool success = false;
    std::string switches;
    std::string input_ply;
    std::string stage = "startup";
    std::string diagnostic;
    std::size_t surface_vertex_count = 0;
    std::size_t surface_face_count = 0;
    std::size_t object_node_count = 0;
    std::size_t object_triangle_count = 0;
    DeformSimIndexStats surface_face_indices;
    DeformSimIndexStats object_face_indices;
    std::size_t degenerate_surface_triangle_count = 0;
    bool bounding_box_valid = false;
    Vec3 bounding_box_min{};
    Vec3 bounding_box_max{};
    bool tetgen_completed = false;
    int tetgen_firstnumber = 0;
    std::size_t tetgen_output_vertex_count = 0;
    std::size_t tetgen_output_tetra_count = 0;
    std::size_t tetgen_output_boundary_face_count = 0;
    DeformSimIndexStats tetgen_tetra_indices;
    DeformSimIndexStats tetgen_triface_indices;
    std::size_t estimated_unique_line_count = 0;
    std::size_t line_capacity_nnode_times_32 = 0;
    bool estimated_line_capacity_exceeded = false;
    std::size_t estimated_matrix_node_count = 0;
    std::size_t estimated_matrix_order = 0;
    std::size_t estimated_dense_k_l_bytes = 0;
    std::size_t estimated_element_scratch_bytes = 0;
    std::vector<Vec3> output_vertices;
    std::vector<Tet> output_tetrahedra;
    std::vector<Face> output_boundary_faces;
};

DeformSimPressureResult evaluate_deformsim_pressure(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const DeformSimPressureOptions& options
);

std::string deformsim_pressure_to_json(const DeformSimPressureResult& result);

void write_deformsim_pressure_json(
    const std::filesystem::path& path,
    const DeformSimPressureResult& result
);

}  // namespace mvrmesh
