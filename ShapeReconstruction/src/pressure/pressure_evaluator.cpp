#include "mvrmesh/pressure/pressure_evaluator.h"

#include <algorithm>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/core/geometry.h"
#include "mvrmesh/core/topology.h"
#include "tetgen.h"

namespace mvrmesh {

namespace {

constexpr std::size_t kLineCapacityPerNode = 32;
constexpr std::size_t kDenseMatrixCount = 2;
constexpr std::size_t kElementScratchDoubles = 12 * 12 + 6 * 12;

std::size_t saturating_multiply(std::size_t lhs, std::size_t rhs) {
    if (lhs != 0 && rhs > std::numeric_limits<std::size_t>::max() / lhs) {
        return std::numeric_limits<std::size_t>::max();
    }
    return lhs * rhs;
}

DeformSimIndexStats empty_index_stats() {
    return DeformSimIndexStats{};
}

void update_index_stats(DeformSimIndexStats& stats, int index, int lower, int upper_exclusive) {
    if (stats.max_index < stats.min_index) {
        stats.min_index = index;
        stats.max_index = index;
    } else {
        stats.min_index = std::min(stats.min_index, index);
        stats.max_index = std::max(stats.max_index, index);
    }
    if (index < lower || index >= upper_exclusive) {
        ++stats.out_of_range_count;
    }
}

DeformSimIndexStats face_index_stats(const std::vector<Face>& faces, std::size_t vertex_count) {
    if (faces.empty()) {
        return empty_index_stats();
    }

    DeformSimIndexStats stats;
    const int upper = static_cast<int>(vertex_count);
    for (const Face& face : faces) {
        update_index_stats(stats, face[0], 0, upper);
        update_index_stats(stats, face[1], 0, upper);
        update_index_stats(stats, face[2], 0, upper);
    }
    return stats;
}

DeformSimIndexStats tet_index_stats(const std::vector<Tet>& tets, std::size_t vertex_count) {
    if (tets.empty()) {
        return empty_index_stats();
    }

    DeformSimIndexStats stats;
    const int upper = static_cast<int>(vertex_count);
    for (const Tet& tet : tets) {
        update_index_stats(stats, tet[0], 0, upper);
        update_index_stats(stats, tet[1], 0, upper);
        update_index_stats(stats, tet[2], 0, upper);
        update_index_stats(stats, tet[3], 0, upper);
    }
    return stats;
}

std::size_t count_degenerate_surface_triangles(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double epsilon
) {
    std::size_t count = 0;
    for (const Face& face : faces) {
        const Vec3& a = vertices.at(static_cast<std::size_t>(face[0]));
        const Vec3& b = vertices.at(static_cast<std::size_t>(face[1]));
        const Vec3& c = vertices.at(static_cast<std::size_t>(face[2]));
        const double area = 0.5 * norm(cross(vsub(b, a), vsub(c, a)));
        if (area <= epsilon) {
            ++count;
        }
    }
    return count;
}

void fill_bounding_box(const std::vector<Vec3>& vertices, DeformSimPressureResult& result) {
    const MeshBoundingBox box = compute_bbox(vertices);
    result.bounding_box_valid = box.valid;
    if (box.valid) {
        result.bounding_box_min = box.min;
        result.bounding_box_max = box.max;
    }
}

std::size_t count_unique_lines_from_tets(const std::vector<Tet>& tets) {
    std::set<std::pair<int, int>> lines;
    for (const Tet& tet : tets) {
        const int ids[4] = {tet[0], tet[1], tet[2], tet[3]};
        for (int a = 0; a < 4; ++a) {
            for (int b = a + 1; b < 4; ++b) {
                lines.insert(std::make_pair(std::min(ids[a], ids[b]), std::max(ids[a], ids[b])));
            }
        }
    }
    return lines.size();
}

DeformSimPressureResult make_base_result(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const DeformSimPressureOptions& options
) {
    DeformSimPressureResult result;
    result.switches = options.switches;
    result.input_ply = options.input_ply;
    result.stage = "precheck_surface";
    result.diagnostic = "not started";
    result.surface_vertex_count = surface_vertices.size();
    result.surface_face_count = surface_faces.size();
    result.object_node_count = surface_vertices.size();
    result.object_triangle_count = surface_faces.size();
    result.surface_face_indices = face_index_stats(surface_faces, surface_vertices.size());
    result.object_face_indices = result.surface_face_indices;
    fill_bounding_box(surface_vertices, result);
    if (result.surface_face_indices.out_of_range_count == 0) {
        result.degenerate_surface_triangle_count =
            count_degenerate_surface_triangles(surface_vertices, surface_faces, options.degeneracy_epsilon);
    }
    return result;
}

void validate_tetgen_input_size(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    const auto max_int = static_cast<std::size_t>(std::numeric_limits<int>::max());
    if (vertices.size() > max_int) {
        throw std::runtime_error("DeformSim pressure input has too many vertices for TetGen int indexing.");
    }
    if (faces.size() > max_int) {
        throw std::runtime_error("DeformSim pressure input has too many faces for TetGen int indexing.");
    }
}

void fill_input_points(tetgenio& input, const std::vector<Vec3>& vertices) {
    input.firstnumber = 1;
    input.numberofpoints = static_cast<int>(vertices.size());
    input.pointlist = new REAL[static_cast<std::size_t>(input.numberofpoints) * 3];
    for (std::size_t i = 0; i < vertices.size(); ++i) {
        input.pointlist[i * 3 + 0] = static_cast<REAL>(vertices[i].x);
        input.pointlist[i * 3 + 1] = static_cast<REAL>(vertices[i].y);
        input.pointlist[i * 3 + 2] = static_cast<REAL>(vertices[i].z);
    }
}

void fill_input_facets(
    tetgenio& input,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    validate_face_indices(vertices, faces, "DeformSim pressure evaluation");

    input.numberoffacets = static_cast<int>(faces.size());
    input.facetlist = new tetgenio::facet[static_cast<std::size_t>(input.numberoffacets)];
    // Zero-initialize every facet before anything below can throw: an
    // allocation in the fill loop may exit mid-way, and tetgenio's destructor
    // would otherwise delete the garbage pointers of the not-yet-filled facets.
    for (std::size_t i = 0; i < faces.size(); ++i) {
        tetgenio::init(&input.facetlist[i]);
    }
    input.trifacemarkerlist = new int[static_cast<std::size_t>(input.numberoffacets)];

    for (std::size_t i = 0; i < faces.size(); ++i) {
        const Face& face = faces[i];
        tetgenio::facet& facet = input.facetlist[i];
        facet.numberofpolygons = 1;
        facet.polygonlist = new tetgenio::polygon[1];
        facet.numberofholes = 0;
        facet.holelist = nullptr;

        tetgenio::polygon& polygon = facet.polygonlist[0];
        tetgenio::init(&polygon);
        polygon.numberofvertices = 3;
        polygon.vertexlist = new int[3];
        polygon.vertexlist[0] = face[0] + 1;
        polygon.vertexlist[1] = face[1] + 1;
        polygon.vertexlist[2] = face[2] + 1;
        input.trifacemarkerlist[i] = 0;
    }
}

void require_output_array(const void* data, std::size_t count, const std::string& name) {
    if (count > 0 && data == nullptr) {
        throw std::runtime_error("TetGen output is missing required array: " + name);
    }
}

int to_checked_zero_based_index(
    int value,
    int first_number,
    std::size_t vertex_count,
    const std::string& element_name
) {
    const int idx = value - first_number;
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertex_count) {
        std::ostringstream oss;
        oss << element_name << " index out of range for DeformSim pressure evaluation: " << idx
            << ", n_vertices=" << vertex_count;
        throw std::runtime_error(oss.str());
    }
    return idx;
}

void validate_result_index(std::size_t vertex_count, int idx, const std::string& element_name) {
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertex_count) {
        std::ostringstream oss;
        oss << element_name << " index out of range for DeformSim pressure JSON: " << idx
            << ", n_vertices=" << vertex_count;
        throw std::runtime_error(oss.str());
    }
}

void validate_pressure_result_indices(const DeformSimPressureResult& result) {
    for (const Tet& tet : result.output_tetrahedra) {
        validate_result_index(result.output_vertices.size(), tet[0], "Tetrahedron");
        validate_result_index(result.output_vertices.size(), tet[1], "Tetrahedron");
        validate_result_index(result.output_vertices.size(), tet[2], "Tetrahedron");
        validate_result_index(result.output_vertices.size(), tet[3], "Tetrahedron");
    }
    for (const Face& face : result.output_boundary_faces) {
        validate_result_index(result.output_vertices.size(), face[0], "Boundary face");
        validate_result_index(result.output_vertices.size(), face[1], "Boundary face");
        validate_result_index(result.output_vertices.size(), face[2], "Boundary face");
    }
}

void copy_tetgen_output(tetgenio& output, DeformSimPressureResult& result) {
    result.tetgen_firstnumber = output.firstnumber;
    result.tetgen_output_vertex_count = static_cast<std::size_t>(std::max(output.numberofpoints, 0));
    result.tetgen_output_tetra_count = static_cast<std::size_t>(std::max(output.numberoftetrahedra, 0));
    result.tetgen_output_boundary_face_count = static_cast<std::size_t>(std::max(output.numberoftrifaces, 0));

    require_output_array(output.pointlist, result.tetgen_output_vertex_count, "pointlist");
    require_output_array(output.tetrahedronlist, result.tetgen_output_tetra_count, "tetrahedronlist");
    require_output_array(output.trifacelist, result.tetgen_output_boundary_face_count, "trifacelist");

    result.output_vertices.reserve(result.tetgen_output_vertex_count);
    for (std::size_t i = 0; i < result.tetgen_output_vertex_count; ++i) {
        result.output_vertices.push_back(Vec3{
            static_cast<double>(output.pointlist[i * 3 + 0]),
            static_cast<double>(output.pointlist[i * 3 + 1]),
            static_cast<double>(output.pointlist[i * 3 + 2]),
        });
    }

    const int corners = output.numberofcorners >= 4 ? output.numberofcorners : 4;
    result.output_tetrahedra.reserve(result.tetgen_output_tetra_count);
    for (std::size_t i = 0; i < result.tetgen_output_tetra_count; ++i) {
        result.output_tetrahedra.push_back(Tet{
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 0],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Tetrahedron"
            ),
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 1],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Tetrahedron"
            ),
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 2],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Tetrahedron"
            ),
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 3],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Tetrahedron"
            ),
        });
    }

    result.output_boundary_faces.reserve(result.tetgen_output_boundary_face_count);
    for (std::size_t i = 0; i < result.tetgen_output_boundary_face_count; ++i) {
        result.output_boundary_faces.push_back(Face{
            to_checked_zero_based_index(
                output.trifacelist[i * 3 + 0],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Boundary face"
            ),
            to_checked_zero_based_index(
                output.trifacelist[i * 3 + 1],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Boundary face"
            ),
            to_checked_zero_based_index(
                output.trifacelist[i * 3 + 2],
                output.firstnumber,
                result.tetgen_output_vertex_count,
                "Boundary face"
            ),
        });
    }

    result.tetgen_tetra_indices = tet_index_stats(result.output_tetrahedra, result.output_vertices.size());
    result.tetgen_triface_indices = face_index_stats(result.output_boundary_faces, result.output_vertices.size());
    result.estimated_unique_line_count = count_unique_lines_from_tets(result.output_tetrahedra);
    result.line_capacity_nnode_times_32 =
        saturating_multiply(result.tetgen_output_vertex_count, kLineCapacityPerNode);
    result.estimated_line_capacity_exceeded =
        result.estimated_unique_line_count > result.line_capacity_nnode_times_32;
    result.estimated_matrix_node_count = result.tetgen_output_vertex_count;
    result.estimated_matrix_order = saturating_multiply(result.estimated_matrix_node_count, 3);
    const std::size_t order_squared =
        saturating_multiply(result.estimated_matrix_order, result.estimated_matrix_order);
    result.estimated_dense_k_l_bytes =
        saturating_multiply(saturating_multiply(order_squared, sizeof(double)), kDenseMatrixCount);
    result.estimated_element_scratch_bytes = saturating_multiply(
        saturating_multiply(result.tetgen_output_tetra_count, kElementScratchDoubles),
        sizeof(double)
    );
}

void write_index_stats(std::ostringstream& out, const char* name, const DeformSimIndexStats& stats) {
    out << "  \"" << name << "\": {\n";
    out << "    \"min_index\": " << stats.min_index << ",\n";
    out << "    \"max_index\": " << stats.max_index << ",\n";
    out << "    \"out_of_range_count\": " << stats.out_of_range_count << "\n";
    out << "  }";
}

void write_bounding_box_fields(std::ostringstream& out, const DeformSimPressureResult& result) {
    if (result.bounding_box_valid) {
        out << "  \"bounding_box_min\": ["
            << result.bounding_box_min.x << ", "
            << result.bounding_box_min.y << ", "
            << result.bounding_box_min.z << "],\n";
        out << "  \"bounding_box_max\": ["
            << result.bounding_box_max.x << ", "
            << result.bounding_box_max.y << ", "
            << result.bounding_box_max.z << "],\n";
    } else {
        out << "  \"bounding_box_min\": null,\n";
        out << "  \"bounding_box_max\": null,\n";
    }
    out << "  \"bounding_box_valid\": " << (result.bounding_box_valid ? "true" : "false") << ",\n";
}

}  // namespace

DeformSimPressureResult evaluate_deformsim_pressure(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const DeformSimPressureOptions& options
) {
    DeformSimPressureResult result = make_base_result(surface_vertices, surface_faces, options);

    try {
        result.stage = "fill_tetgen_input";
        validate_tetgen_input_size(surface_vertices, surface_faces);
        tetgenio input;
        tetgenio output;
        fill_input_points(input, surface_vertices);
        fill_input_facets(input, surface_vertices, surface_faces);

        result.stage = "tetgen_call";
        std::vector<char> switches(result.switches.begin(), result.switches.end());
        switches.push_back('\0');
        tetrahedralize(switches.data(), &input, &output);

        copy_tetgen_output(output, result);
        result.success = true;
        result.tetgen_completed = true;
        result.stage = "tetgen_output_validated";
        result.diagnostic = "TetGen completed; diagnostic did not run DeformSim post-processing.";
    } catch (int code) {
        result.success = false;
        result.tetgen_completed = false;
        std::ostringstream oss;
        oss << "TetGen terminated with code " << code;
        result.diagnostic = oss.str();
    } catch (const std::exception& ex) {
        result.success = false;
        result.tetgen_completed = false;
        result.diagnostic = ex.what();
    }
    return result;
}

std::string deformsim_pressure_to_json(const DeformSimPressureResult& result) {
    validate_pressure_result_indices(result);
    std::ostringstream out;
    out << std::setprecision(17);
    out << "{\n";
    out << "  \"success\": " << (result.success ? "true" : "false") << ",\n";
    out << "  \"input_ply\": \"" << json_escape(result.input_ply) << "\",\n";
    out << "  \"stage\": \"" << json_escape(result.stage) << "\",\n";
    out << "  \"diagnostic\": \"" << json_escape(result.diagnostic) << "\",\n";
    out << "  \"surface_vertex_count\": " << result.surface_vertex_count << ",\n";
    out << "  \"surface_face_count\": " << result.surface_face_count << ",\n";
    out << "  \"object_node_count\": " << result.object_node_count << ",\n";
    out << "  \"object_triangle_count\": " << result.object_triangle_count << ",\n";
    out << "  \"surface_face_index_min\": " << result.surface_face_indices.min_index << ",\n";
    out << "  \"surface_face_index_max\": " << result.surface_face_indices.max_index << ",\n";
    out << "  \"surface_face_index_out_of_range_count\": "
        << result.surface_face_indices.out_of_range_count << ",\n";
    out << "  \"object_face_index_min\": " << result.object_face_indices.min_index << ",\n";
    out << "  \"object_face_index_max\": " << result.object_face_indices.max_index << ",\n";
    out << "  \"object_face_index_out_of_range_count\": "
        << result.object_face_indices.out_of_range_count << ",\n";
    out << "  \"degenerate_surface_triangle_count\": "
        << result.degenerate_surface_triangle_count << ",\n";
    write_bounding_box_fields(out, result);
    out << "  \"tetgen_completed\": " << (result.tetgen_completed ? "true" : "false") << ",\n";
    out << "  \"tetgen_firstnumber\": " << result.tetgen_firstnumber << ",\n";
    out << "  \"tetgen_output_vertex_count\": " << result.tetgen_output_vertex_count << ",\n";
    out << "  \"tetgen_output_tetra_count\": " << result.tetgen_output_tetra_count << ",\n";
    out << "  \"tetgen_output_boundary_face_count\": " << result.tetgen_output_boundary_face_count << ",\n";
    out << "  \"tetgen_tetra_index_min\": " << result.tetgen_tetra_indices.min_index << ",\n";
    out << "  \"tetgen_tetra_index_max\": " << result.tetgen_tetra_indices.max_index << ",\n";
    out << "  \"tetgen_tetra_index_out_of_range_count\": "
        << result.tetgen_tetra_indices.out_of_range_count << ",\n";
    out << "  \"tetgen_triface_index_min\": " << result.tetgen_triface_indices.min_index << ",\n";
    out << "  \"tetgen_triface_index_max\": " << result.tetgen_triface_indices.max_index << ",\n";
    out << "  \"tetgen_triface_index_out_of_range_count\": "
        << result.tetgen_triface_indices.out_of_range_count << ",\n";
    write_index_stats(out, "surface_face_indices", result.surface_face_indices);
    out << ",\n";
    write_index_stats(out, "object_face_indices", result.object_face_indices);
    out << ",\n";
    write_index_stats(out, "tetgen_tetra_indices", result.tetgen_tetra_indices);
    out << ",\n";
    write_index_stats(out, "tetgen_triface_indices", result.tetgen_triface_indices);
    out << ",\n";
    out << "  \"estimated_unique_line_count\": " << result.estimated_unique_line_count << ",\n";
    out << "  \"line_capacity_nnode_times_32\": " << result.line_capacity_nnode_times_32 << ",\n";
    out << "  \"estimated_line_capacity_exceeded\": "
        << (result.estimated_line_capacity_exceeded ? "true" : "false") << ",\n";
    out << "  \"estimated_matrix_node_count\": " << result.estimated_matrix_node_count << ",\n";
    out << "  \"estimated_matrix_order\": " << result.estimated_matrix_order << ",\n";
    out << "  \"estimated_dense_k_l_bytes\": " << result.estimated_dense_k_l_bytes << ",\n";
    out << "  \"estimated_element_scratch_bytes\": " << result.estimated_element_scratch_bytes << "\n";
    out << "}\n";
    return out.str();
}

void write_deformsim_pressure_json(
    const std::filesystem::path& path,
    const DeformSimPressureResult& result
) {
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("Failed to open DeformSim pressure output file: " + path.string());
    }
    output << deformsim_pressure_to_json(result);
}

}  // namespace mvrmesh
