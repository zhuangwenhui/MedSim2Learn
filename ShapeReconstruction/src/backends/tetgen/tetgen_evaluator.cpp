#include "mvrmesh/backends/tetgen/tetgen_evaluator.h"

#include <algorithm>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <vector>

#include "tetgen.h"

namespace mvrmesh {

namespace {

std::string json_escape(const std::string& value) {
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

TetGenEvaluationResult make_base_result(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const TetGenEvaluationOptions& options
) {
    TetGenEvaluationResult result;
    result.switches = options.switches;
    result.input_vertex_count = surface_vertices.size();
    result.input_face_count = surface_faces.size();
    return result;
}

void validate_face_index(const std::vector<Vec3>& vertices, int idx) {
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertices.size()) {
        std::ostringstream oss;
        oss << "Face index out of range for TetGen evaluation: " << idx
            << ", n_vertices=" << vertices.size();
        throw std::runtime_error(oss.str());
    }
}

void validate_tetgen_input_size(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    const auto max_int = static_cast<std::size_t>(std::numeric_limits<int>::max());
    if (vertices.size() > max_int) {
        throw std::runtime_error("TetGen evaluation input has too many vertices for TetGen int indexing.");
    }
    if (faces.size() > max_int) {
        throw std::runtime_error("TetGen evaluation input has too many faces for TetGen int indexing.");
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
    input.numberoffacets = static_cast<int>(faces.size());
    input.facetlist = new tetgenio::facet[static_cast<std::size_t>(input.numberoffacets)];

    for (std::size_t i = 0; i < faces.size(); ++i) {
        const Face& face = faces[i];
        validate_face_index(vertices, face[0]);
        validate_face_index(vertices, face[1]);
        validate_face_index(vertices, face[2]);

        tetgenio::facet& facet = input.facetlist[i];
        tetgenio::init(&facet);
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
    }
}

int to_zero_based_index(int value, int first_number) {
    return value - first_number;
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
    const int idx = to_zero_based_index(value, first_number);
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertex_count) {
        std::ostringstream oss;
        oss << element_name << " index out of range for TetGen evaluation: " << idx
            << ", n_vertices=" << vertex_count;
        throw std::runtime_error(oss.str());
    }
    return idx;
}

void validate_result_index(std::size_t vertex_count, int idx, const std::string& element_name) {
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertex_count) {
        std::ostringstream oss;
        oss << element_name << " index out of range for TetGen evaluation: " << idx
            << ", n_vertices=" << vertex_count;
        throw std::runtime_error(oss.str());
    }
}

void validate_tetgen_result_indices(const TetGenEvaluationResult& result) {
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

void copy_tetgen_output(tetgenio& output, TetGenEvaluationResult& result) {
    result.output_vertex_count = static_cast<std::size_t>(std::max(output.numberofpoints, 0));
    result.output_tetra_count = static_cast<std::size_t>(std::max(output.numberoftetrahedra, 0));
    result.output_boundary_face_count = static_cast<std::size_t>(std::max(output.numberoftrifaces, 0));

    require_output_array(output.pointlist, result.output_vertex_count, "pointlist");
    require_output_array(output.tetrahedronlist, result.output_tetra_count, "tetrahedronlist");
    require_output_array(output.trifacelist, result.output_boundary_face_count, "trifacelist");

    result.output_vertices.reserve(result.output_vertex_count);
    for (std::size_t i = 0; i < result.output_vertex_count; ++i) {
        result.output_vertices.push_back(Vec3{
            static_cast<double>(output.pointlist[i * 3 + 0]),
            static_cast<double>(output.pointlist[i * 3 + 1]),
            static_cast<double>(output.pointlist[i * 3 + 2]),
        });
    }

    const int corners = output.numberofcorners >= 4 ? output.numberofcorners : 4;
    result.output_tetrahedra.reserve(result.output_tetra_count);
    for (std::size_t i = 0; i < result.output_tetra_count; ++i) {
        result.output_tetrahedra.push_back(Tet{
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 0],
                output.firstnumber,
                result.output_vertex_count,
                "Tetrahedron"
            ),
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 1],
                output.firstnumber,
                result.output_vertex_count,
                "Tetrahedron"
            ),
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 2],
                output.firstnumber,
                result.output_vertex_count,
                "Tetrahedron"
            ),
            to_checked_zero_based_index(
                output.tetrahedronlist[i * static_cast<std::size_t>(corners) + 3],
                output.firstnumber,
                result.output_vertex_count,
                "Tetrahedron"
            ),
        });
    }

    result.output_boundary_faces.reserve(result.output_boundary_face_count);
    for (std::size_t i = 0; i < result.output_boundary_face_count; ++i) {
        result.output_boundary_faces.push_back(Face{
            to_checked_zero_based_index(
                output.trifacelist[i * 3 + 0],
                output.firstnumber,
                result.output_vertex_count,
                "Boundary face"
            ),
            to_checked_zero_based_index(
                output.trifacelist[i * 3 + 1],
                output.firstnumber,
                result.output_vertex_count,
                "Boundary face"
            ),
            to_checked_zero_based_index(
                output.trifacelist[i * 3 + 2],
                output.firstnumber,
                result.output_vertex_count,
                "Boundary face"
            ),
        });
    }
    result.tetra_metrics = compute_tetra_mesh_metrics(result.output_vertices, result.output_tetrahedra);
}

}  // namespace

TetGenEvaluationResult evaluate_tetgen(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const TetGenEvaluationOptions& options
) {
    TetGenEvaluationResult result = make_base_result(surface_vertices, surface_faces, options);

    try {
        validate_tetgen_input_size(surface_vertices, surface_faces);
        tetgenio input;
        tetgenio output;
        fill_input_points(input, surface_vertices);
        fill_input_facets(input, surface_vertices, surface_faces);

        std::vector<char> switches(result.switches.begin(), result.switches.end());
        switches.push_back('\0');
        tetrahedralize(switches.data(), &input, &output);

        copy_tetgen_output(output, result);
        result.success = true;
        result.diagnostic = "TetGen evaluation completed.";
    } catch (int code) {
        result.success = false;
        std::ostringstream oss;
        oss << "TetGen terminated with code " << code << ".";
        result.diagnostic = oss.str();
    } catch (const std::exception& ex) {
        result.success = false;
        result.diagnostic = ex.what();
    }
    return result;
}

std::string tetgen_evaluation_to_json(const TetGenEvaluationResult& result) {
    validate_tetgen_result_indices(result);
    const TetraMeshMetrics tetra_metrics =
        compute_tetra_mesh_metrics(result.output_vertices, result.output_tetrahedra);
    std::ostringstream out;
    out << std::setprecision(17);
    out << "{\n";
    out << "  \"success\": " << (result.success ? "true" : "false") << ",\n";
    out << "  \"switches\": \"" << json_escape(result.switches) << "\",\n";
    out << "  \"diagnostic\": \"" << json_escape(result.diagnostic) << "\",\n";
    out << "  \"input_vertex_count\": " << result.input_vertex_count << ",\n";
    out << "  \"input_face_count\": " << result.input_face_count << ",\n";
    out << "  \"output_vertex_count\": " << result.output_vertex_count << ",\n";
    out << "  \"output_tetra_count\": " << result.output_tetra_count << ",\n";
    out << "  \"output_boundary_face_count\": " << result.output_boundary_face_count << ",\n";
    out << "  \"tetra_count\": " << tetra_metrics.tetra_count << ",\n";
    out << "  \"degenerate_tetra_count\": " << tetra_metrics.degenerate_tetra_count << ",\n";
    out << "  \"total_volume\": " << tetra_metrics.total_volume << ",\n";
    out << "  \"min_tetra_volume\": " << tetra_metrics.min_tetra_volume << ",\n";
    out << "  \"max_tetra_volume\": " << tetra_metrics.max_tetra_volume << ",\n";
    out << "  \"mean_tetra_volume\": " << tetra_metrics.mean_tetra_volume << ",\n";
    out << "  \"min_tetra_quality\": " << tetra_metrics.min_tetra_quality << ",\n";
    out << "  \"max_tetra_quality\": " << tetra_metrics.max_tetra_quality << ",\n";
    out << "  \"mean_tetra_quality\": " << tetra_metrics.mean_tetra_quality << "\n";
    out << "}\n";
    return out.str();
}

void write_tetgen_evaluation_json(
    const std::filesystem::path& path,
    const TetGenEvaluationResult& result
) {
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("Failed to open TetGen metrics output file: " + path.string());
    }
    output << tetgen_evaluation_to_json(result);
}

}  // namespace mvrmesh
