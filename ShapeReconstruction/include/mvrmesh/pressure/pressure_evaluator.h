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

// Options for the TetGen pre-flight run by evaluate_deformsim_pressure().
struct DeformSimPressureOptions {
    // TetGen switch string passed to tetrahedralize() unchanged.
    std::string switches = "pYQ";
    // Source mesh path, recorded verbatim in the report; never opened here.
    std::string input_ply;
    // Triangle area (mm^2) at or below which a surface face counts as degenerate.
    double degeneracy_epsilon = 1e-12;
};

// Range summary over one index array (face corners or tet corners). The
// default max_index < min_index state means no index was recorded.
struct DeformSimIndexStats {
    int min_index = 0;
    int max_index = -1;
    std::size_t out_of_range_count = 0;
};

// Full report of one pre-flight: input surface statistics, the TetGen
// outcome, footprint estimates for DeformSim's dense solver, and the
// tetrahedralized mesh itself. On failure success stays false and
// stage/diagnostic record how far the run got and why it stopped.
// Coordinates are millimetres.
struct DeformSimPressureResult {
    bool success = false;
    std::string switches;
    std::string input_ply;
    // Last pipeline stage reached; written into the JSON report.
    std::string stage = "startup";
    std::string diagnostic;
    std::size_t surface_vertex_count = 0;
    std::size_t surface_face_count = 0;
    // The same surface mesh counted under DeformSim's object naming.
    std::size_t object_node_count = 0;
    std::size_t object_triangle_count = 0;
    DeformSimIndexStats surface_face_indices;
    DeformSimIndexStats object_face_indices;
    std::size_t degenerate_surface_triangle_count = 0;
    // Axis-aligned bounding box of the input surface, in millimetres.
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
    // DeformSim footprint estimates: its edge table allows 32 lines per node,
    // and its dense K and L matrices are (3 * node_count)^2 doubles each.
    std::size_t estimated_unique_line_count = 0;
    std::size_t line_capacity_nnode_times_32 = 0;
    bool estimated_line_capacity_exceeded = false;
    std::size_t estimated_matrix_node_count = 0;
    std::size_t estimated_matrix_order = 0;
    std::size_t estimated_dense_k_l_bytes = 0;
    std::size_t estimated_element_scratch_bytes = 0;
    // Tetrahedralized mesh from TetGen.
    std::vector<Vec3> output_vertices;
    std::vector<Tet> output_tetrahedra;
    std::vector<Face> output_boundary_faces;
};

// Tetrahedralizes the closed surface (vertices in millimetres) with TetGen and
// fills the diagnostic report. Failures, including TetGen's plain-int throws,
// are captured as success=false with stage and diagnostic set instead of
// propagating.
DeformSimPressureResult evaluate_deformsim_pressure(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const DeformSimPressureOptions& options
);

// Serializes the result to a JSON object string (doubles at 17 significant
// digits). Throws std::runtime_error if the stored tetrahedron or boundary
// face indices fall outside the output vertex range.
std::string deformsim_pressure_to_json(const DeformSimPressureResult& result);

// Writes the JSON serialization of the result to path. Throws
// std::runtime_error when the file cannot be opened, and propagates the index
// validation failure from deformsim_pressure_to_json().
void write_deformsim_pressure_json(
    const std::filesystem::path& path,
    const DeformSimPressureResult& result
);

}  // namespace mvrmesh
