#include "stdafx.h"

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "object.h"
#include "surface.h"

bool g_useSolverLU = false;

namespace {

struct IndexStats {
    int min_index = std::numeric_limits<int>::max();
    int max_index = std::numeric_limits<int>::min();
    int out_of_range_count = 0;
};

struct DiagnosticBoundingBox {
    bool valid = false;
    Vector3f min;
    Vector3f max;
};

struct PlyPrecheckResult {
    bool ok = false;
    int vertex_count = 0;
    int face_count = 0;
    IndexStats face_stats;
    std::string diagnostic;
};

std::string json_escape(const std::string& text) {
    std::string escaped;
    escaped.reserve(text.size());
    for (unsigned char ch : text) {
        switch (ch) {
        case '\\':
            escaped += "\\\\";
            break;
        case '"':
            escaped += "\\\"";
            break;
        case '\b':
            escaped += "\\b";
            break;
        case '\f':
            escaped += "\\f";
            break;
        case '\n':
            escaped += "\\n";
            break;
        case '\r':
            escaped += "\\r";
            break;
        case '\t':
            escaped += "\\t";
            break;
        default:
            if (ch < 0x20) {
                std::ostringstream hex;
                hex << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                    << static_cast<int>(ch);
                escaped += hex.str();
            } else {
                escaped.push_back(static_cast<char>(ch));
            }
            break;
        }
    }
    return escaped;
}

double triangle_area(const Vertex& a, const Vertex& b, const Vertex& c) {
    Vector3f ab(
        b.new_coord.x - a.new_coord.x,
        b.new_coord.y - a.new_coord.y,
        b.new_coord.z - a.new_coord.z
    );
    Vector3f ac(
        c.new_coord.x - a.new_coord.x,
        c.new_coord.y - a.new_coord.y,
        c.new_coord.z - a.new_coord.z
    );
    return 0.5 * static_cast<double>(ab.CrossProduct(ac).GetLength());
}

DiagnosticBoundingBox compute_bounding_box(const Surface& surface) {
    DiagnosticBoundingBox box;
    if (surface.nNode <= 0 || surface.vertex.empty()) {
        return box;
    }

    box.valid = true;
    box.min = surface.vertex[0].new_coord;
    box.max = surface.vertex[0].new_coord;
    for (int i = 1; i < surface.nNode; ++i) {
        const Vector3f& p = surface.vertex[static_cast<std::size_t>(i)].new_coord;
        box.min.x = std::min(box.min.x, p.x);
        box.min.y = std::min(box.min.y, p.y);
        box.min.z = std::min(box.min.z, p.z);
        box.max.x = std::max(box.max.x, p.x);
        box.max.y = std::max(box.max.y, p.y);
        box.max.z = std::max(box.max.z, p.z);
    }
    return box;
}

IndexStats make_empty_index_stats() {
    IndexStats stats;
    stats.min_index = 0;
    stats.max_index = -1;
    return stats;
}

void add_index_to_stats(IndexStats& stats, int index, int vertex_count) {
    stats.min_index = std::min(stats.min_index, index);
    stats.max_index = std::max(stats.max_index, index);
    if (index < 0 || index >= vertex_count) {
        ++stats.out_of_range_count;
    }
}

PlyPrecheckResult precheck_ascii_ply(const std::filesystem::path& input_path) {
    PlyPrecheckResult result;
    result.face_stats = make_empty_index_stats();

    std::ifstream in(input_path);
    if (!in) {
        result.diagnostic = "Failed to open PLY for precheck";
        return result;
    }

    std::string line;
    if (!std::getline(in, line) || line != "ply") {
        result.diagnostic = "PLY precheck expected ply magic";
        return result;
    }

    bool ascii_format = false;
    bool saw_end_header = false;
    while (std::getline(in, line)) {
        std::istringstream header(line);
        std::string first;
        header >> first;
        if (first == "format") {
            std::string format;
            header >> format;
            ascii_format = (format == "ascii");
        } else if (first == "element") {
            std::string element_name;
            int count = 0;
            if (!(header >> element_name >> count)) {
                result.diagnostic = "PLY precheck failed to parse element header";
                return result;
            }
            if (count < 0) {
                result.diagnostic = "PLY precheck found negative element count";
                return result;
            }
            if (element_name == "vertex") {
                result.vertex_count = count;
            } else if (element_name == "face") {
                result.face_count = count;
            }
        } else if (first == "end_header") {
            saw_end_header = true;
            break;
        }
    }

    if (!ascii_format) {
        result.diagnostic = "PLY precheck only supports ascii format";
        return result;
    }
    if (!saw_end_header) {
        result.diagnostic = "PLY precheck missing end_header";
        return result;
    }
    for (int i = 0; i < result.vertex_count; ++i) {
        if (!std::getline(in, line)) {
            result.diagnostic = "PLY precheck ended while reading vertices";
            return result;
        }
        std::istringstream vertex(line);
        double x = 0.0;
        double y = 0.0;
        double z = 0.0;
        if (!(vertex >> x >> y >> z)) {
            result.diagnostic = "PLY precheck failed to parse vertex coordinates";
            return result;
        }
    }

    if (result.face_count > 0) {
        result.face_stats.min_index = std::numeric_limits<int>::max();
        result.face_stats.max_index = std::numeric_limits<int>::min();
    }

    for (int i = 0; i < result.face_count; ++i) {
        if (!std::getline(in, line)) {
            result.diagnostic = "PLY precheck ended while reading faces";
            return result;
        }

        std::istringstream face(line);
        int vertex_per_face = 0;
        if (!(face >> vertex_per_face)) {
            result.diagnostic = "PLY precheck failed to parse face vertex count";
            return result;
        }
        if (vertex_per_face != 3) {
            result.diagnostic = "PLY precheck found non-triangle face";
            return result;
        }

        for (int j = 0; j < 3; ++j) {
            int index = 0;
            if (!(face >> index)) {
                result.diagnostic = "PLY precheck failed to parse face index";
                return result;
            }
            add_index_to_stats(result.face_stats, index, result.vertex_count);
        }
    }

    if (result.face_count <= 0) {
        result.face_stats = make_empty_index_stats();
    }
    if (result.face_stats.out_of_range_count > 0) {
        result.diagnostic = "PLY precheck found out-of-range face indices";
        return result;
    }

    result.ok = true;
    result.diagnostic = "PLY precheck passed";
    return result;
}

IndexStats surface_face_index_stats(const Surface& surface) {
    if (surface.nTriangle <= 0) {
        return make_empty_index_stats();
    }

    IndexStats stats;
    for (int i = 0; i < surface.nTriangle; ++i) {
        const Triangle& tri = surface.triangle[static_cast<std::size_t>(i)];
        for (int j = 0; j < 3; ++j) {
            const int index = tri.set[j];
            stats.min_index = std::min(stats.min_index, index);
            stats.max_index = std::max(stats.max_index, index);
            if (index < 0 || index >= surface.nNode) {
                ++stats.out_of_range_count;
            }
        }
    }
    return stats;
}

int count_degenerate_surface_triangles(const Surface& surface, double epsilon) {
    int count = 0;
    for (int i = 0; i < surface.nTriangle; ++i) {
        const Triangle& tri = surface.triangle[static_cast<std::size_t>(i)];
        if (tri.set[0] < 0 || tri.set[0] >= surface.nNode ||
            tri.set[1] < 0 || tri.set[1] >= surface.nNode ||
            tri.set[2] < 0 || tri.set[2] >= surface.nNode) {
            continue;
        }

        const double area = triangle_area(
            surface.vertex[static_cast<std::size_t>(tri.set[0])],
            surface.vertex[static_cast<std::size_t>(tri.set[1])],
            surface.vertex[static_cast<std::size_t>(tri.set[2])]
        );
        if (area <= epsilon) {
            ++count;
        }
    }
    return count;
}

void copy_surface_to_object(const Surface& surface, Object& object) {
    object.InitVertex(surface.nNode);
    for (int i = 0; i < surface.nNode; ++i) {
        object.vertex[i] = surface.vertex[static_cast<std::size_t>(i)];
    }

    object.InitTriangle(surface.nTriangle);
    for (int i = 0; i < surface.nTriangle; ++i) {
        object.triangle[i] = surface.triangle[static_cast<std::size_t>(i)];
    }
}

IndexStats object_triangle_index_stats(const Object& object) {
    if (object.nTriangle <= 0) {
        return make_empty_index_stats();
    }

    IndexStats stats;
    for (int i = 0; i < object.nTriangle; ++i) {
        const Triangle& tri = object.triangle[i];
        for (int j = 0; j < 3; ++j) {
            const int index = tri.set[j];
            stats.min_index = std::min(stats.min_index, index);
            stats.max_index = std::max(stats.max_index, index);
            if (index < 0 || index >= object.nNode) {
                ++stats.out_of_range_count;
            }
        }
    }
    return stats;
}

IndexStats tetgen_tetra_index_stats(const tetgenio& output) {
    if (output.numberoftetrahedra <= 0 || output.tetrahedronlist == nullptr) {
        return make_empty_index_stats();
    }

    IndexStats stats;
    const int corners = output.numberofcorners >= 4 ? output.numberofcorners : 4;
    for (int i = 0; i < output.numberoftetrahedra; ++i) {
        for (int j = 0; j < 4; ++j) {
            const int index = output.tetrahedronlist[i * corners + j];
            stats.min_index = std::min(stats.min_index, index);
            stats.max_index = std::max(stats.max_index, index);
            if (index < output.firstnumber || index >= output.firstnumber + output.numberofpoints) {
                ++stats.out_of_range_count;
            }
        }
    }
    return stats;
}

IndexStats tetgen_triface_index_stats(const tetgenio& output) {
    if (output.numberoftrifaces <= 0 || output.trifacelist == nullptr) {
        return make_empty_index_stats();
    }

    IndexStats stats;
    for (int i = 0; i < output.numberoftrifaces; ++i) {
        for (int j = 0; j < 3; ++j) {
            const int index = output.trifacelist[i * 3 + j];
            stats.min_index = std::min(stats.min_index, index);
            stats.max_index = std::max(stats.max_index, index);
            if (index < output.firstnumber || index >= output.firstnumber + output.numberofpoints) {
                ++stats.out_of_range_count;
            }
        }
    }
    return stats;
}

std::int64_t count_unique_lines_from_tets(const tetgenio& output) {
    if (output.numberoftetrahedra <= 0 || output.tetrahedronlist == nullptr) {
        return 0;
    }

    const int corners = output.numberofcorners >= 4 ? output.numberofcorners : 4;
    std::set<std::pair<int, int>> lines;
    for (int i = 0; i < output.numberoftetrahedra; ++i) {
        const int ids[4] = {
            output.tetrahedronlist[i * corners + 0] - output.firstnumber,
            output.tetrahedronlist[i * corners + 1] - output.firstnumber,
            output.tetrahedronlist[i * corners + 2] - output.firstnumber,
            output.tetrahedronlist[i * corners + 3] - output.firstnumber,
        };
        for (int a = 0; a < 4; ++a) {
            for (int b = a + 1; b < 4; ++b) {
                lines.insert(std::make_pair(std::min(ids[a], ids[b]), std::max(ids[a], ids[b])));
            }
        }
    }
    return static_cast<std::int64_t>(lines.size());
}

void fill_tetgen_input(const Object& object, tetgenio& input) {
    input.firstnumber = 1;
    input.numberofpoints = object.nNode;
    input.pointlist = new REAL[input.numberofpoints * 3];
    input.numberoffacets = object.nTriangle;
    input.facetlist = new tetgenio::facet[input.numberoffacets];
    input.trifacemarkerlist = new int[input.numberoffacets];

    for (int i = 0; i < input.numberofpoints; ++i) {
        input.pointlist[i * 3 + 0] = object.vertex[i].new_coord.x;
        input.pointlist[i * 3 + 1] = object.vertex[i].new_coord.y;
        input.pointlist[i * 3 + 2] = object.vertex[i].new_coord.z;
    }

    for (int i = 0; i < object.nTriangle; ++i) {
        tetgenio::facet& facet = input.facetlist[i];
        facet.numberofpolygons = 1;
        facet.polygonlist = new tetgenio::polygon[1];
        facet.numberofholes = 0;
        facet.holelist = nullptr;

        tetgenio::polygon& polygon = facet.polygonlist[0];
        polygon.numberofvertices = 3;
        polygon.vertexlist = new int[3];
        polygon.vertexlist[0] = object.triangle[i].set[0] + 1;
        polygon.vertexlist[1] = object.triangle[i].set[1] + 1;
        polygon.vertexlist[2] = object.triangle[i].set[2] + 1;
        input.trifacemarkerlist[i] = 0;
    }
}

void write_index_stats(std::ofstream& out, const char* name, const IndexStats& stats) {
    out << "  \"" << name << "\": {\n";
    out << "    \"min_index\": " << stats.min_index << ",\n";
    out << "    \"max_index\": " << stats.max_index << ",\n";
    out << "    \"out_of_range_count\": " << stats.out_of_range_count << "\n";
    out << "  }";
}

void write_bounding_box_fields(std::ofstream& out, const DiagnosticBoundingBox& bbox) {
    if (bbox.valid) {
        out << "  \"bounding_box_min\": [" << bbox.min.x << ", " << bbox.min.y << ", " << bbox.min.z << "],\n";
        out << "  \"bounding_box_max\": [" << bbox.max.x << ", " << bbox.max.y << ", " << bbox.max.z << "],\n";
    } else {
        out << "  \"bounding_box_min\": null,\n";
        out << "  \"bounding_box_max\": null,\n";
    }
    out << "  \"bounding_box_valid\": " << (bbox.valid ? "true" : "false") << ",\n";
}

void write_precheck_failure_json(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_path,
    const PlyPrecheckResult& precheck,
    const std::string& stage
) {
    std::filesystem::create_directories(output_path.parent_path());
    std::ofstream out(output_path);
    if (!out) {
        throw std::runtime_error("Failed to open diagnostic JSON: " + output_path.string());
    }

    const IndexStats empty_stats = make_empty_index_stats();

    out << "{\n";
    out << "  \"success\": false,\n";
    out << "  \"input_ply\": \"" << json_escape(input_path.string()) << "\",\n";
    out << "  \"stage\": \"" << json_escape(stage) << "\",\n";
    out << "  \"diagnostic\": \"" << json_escape(precheck.diagnostic) << "\",\n";
    out << "  \"surface_vertex_count\": " << precheck.vertex_count << ",\n";
    out << "  \"surface_face_count\": " << precheck.face_count << ",\n";
    out << "  \"object_node_count\": 0,\n";
    out << "  \"object_triangle_count\": 0,\n";
    out << "  \"surface_face_index_min\": " << precheck.face_stats.min_index << ",\n";
    out << "  \"surface_face_index_max\": " << precheck.face_stats.max_index << ",\n";
    out << "  \"surface_face_index_out_of_range_count\": "
        << precheck.face_stats.out_of_range_count << ",\n";
    out << "  \"object_face_index_min\": 0,\n";
    out << "  \"object_face_index_max\": -1,\n";
    out << "  \"object_face_index_out_of_range_count\": 0,\n";
    out << "  \"degenerate_surface_triangle_count\": 0,\n";
    write_bounding_box_fields(out, DiagnosticBoundingBox{});
    out << "  \"tetgen_completed\": false,\n";
    out << "  \"tetgen_firstnumber\": 0,\n";
    out << "  \"tetgen_output_vertex_count\": 0,\n";
    out << "  \"tetgen_output_tetra_count\": 0,\n";
    out << "  \"tetgen_output_boundary_face_count\": 0,\n";
    out << "  \"tetgen_tetra_index_min\": 0,\n";
    out << "  \"tetgen_tetra_index_max\": -1,\n";
    out << "  \"tetgen_tetra_index_out_of_range_count\": 0,\n";
    out << "  \"tetgen_triface_index_min\": 0,\n";
    out << "  \"tetgen_triface_index_max\": -1,\n";
    out << "  \"tetgen_triface_index_out_of_range_count\": 0,\n";
    write_index_stats(out, "surface_face_indices", precheck.face_stats);
    out << ",\n";
    write_index_stats(out, "object_face_indices", empty_stats);
    out << ",\n";
    write_index_stats(out, "tetgen_tetra_indices", empty_stats);
    out << ",\n";
    write_index_stats(out, "tetgen_triface_indices", empty_stats);
    out << ",\n";
    out << "  \"estimated_unique_line_count\": 0,\n";
    out << "  \"line_capacity_nnode_times_32\": 0,\n";
    out << "  \"estimated_line_capacity_exceeded\": false\n";
    out << "}\n";
}

void write_json_result(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_path,
    const Surface& surface,
    const Object& object,
    const DiagnosticBoundingBox& bbox,
    const IndexStats& surface_stats,
    const IndexStats& object_stats,
    int degenerate_surface_triangles,
    const tetgenio& tetgen_output,
    bool tetgen_completed,
    const std::string& stage,
    const std::string& diagnostic
) {
    std::filesystem::create_directories(output_path.parent_path());
    std::ofstream out(output_path);
    if (!out) {
        throw std::runtime_error("Failed to open diagnostic JSON: " + output_path.string());
    }

    const IndexStats tetra_stats = tetgen_tetra_index_stats(tetgen_output);
    const IndexStats triface_stats = tetgen_triface_index_stats(tetgen_output);
    const std::int64_t unique_line_count =
        tetgen_completed ? count_unique_lines_from_tets(tetgen_output) : 0;
    const std::int64_t line_capacity = tetgen_output.numberofpoints > 0
        ? static_cast<std::int64_t>(tetgen_output.numberofpoints) * 32
        : 0;

    out << "{\n";
    out << "  \"success\": " << (tetgen_completed ? "true" : "false") << ",\n";
    out << "  \"input_ply\": \"" << json_escape(input_path.string()) << "\",\n";
    out << "  \"stage\": \"" << json_escape(stage) << "\",\n";
    out << "  \"diagnostic\": \"" << json_escape(diagnostic) << "\",\n";
    out << "  \"surface_vertex_count\": " << surface.nNode << ",\n";
    out << "  \"surface_face_count\": " << surface.nTriangle << ",\n";
    out << "  \"object_node_count\": " << object.nNode << ",\n";
    out << "  \"object_triangle_count\": " << object.nTriangle << ",\n";
    out << "  \"surface_face_index_min\": " << surface_stats.min_index << ",\n";
    out << "  \"surface_face_index_max\": " << surface_stats.max_index << ",\n";
    out << "  \"surface_face_index_out_of_range_count\": " << surface_stats.out_of_range_count << ",\n";
    out << "  \"object_face_index_min\": " << object_stats.min_index << ",\n";
    out << "  \"object_face_index_max\": " << object_stats.max_index << ",\n";
    out << "  \"object_face_index_out_of_range_count\": " << object_stats.out_of_range_count << ",\n";
    out << "  \"degenerate_surface_triangle_count\": " << degenerate_surface_triangles << ",\n";
    write_bounding_box_fields(out, bbox);
    out << "  \"tetgen_completed\": " << (tetgen_completed ? "true" : "false") << ",\n";
    out << "  \"tetgen_firstnumber\": " << tetgen_output.firstnumber << ",\n";
    out << "  \"tetgen_output_vertex_count\": " << tetgen_output.numberofpoints << ",\n";
    out << "  \"tetgen_output_tetra_count\": " << tetgen_output.numberoftetrahedra << ",\n";
    out << "  \"tetgen_output_boundary_face_count\": " << tetgen_output.numberoftrifaces << ",\n";
    out << "  \"tetgen_tetra_index_min\": " << tetra_stats.min_index << ",\n";
    out << "  \"tetgen_tetra_index_max\": " << tetra_stats.max_index << ",\n";
    out << "  \"tetgen_tetra_index_out_of_range_count\": " << tetra_stats.out_of_range_count << ",\n";
    out << "  \"tetgen_triface_index_min\": " << triface_stats.min_index << ",\n";
    out << "  \"tetgen_triface_index_max\": " << triface_stats.max_index << ",\n";
    out << "  \"tetgen_triface_index_out_of_range_count\": " << triface_stats.out_of_range_count << ",\n";
    write_index_stats(out, "surface_face_indices", surface_stats);
    out << ",\n";
    write_index_stats(out, "object_face_indices", object_stats);
    out << ",\n";
    write_index_stats(out, "tetgen_tetra_indices", tetra_stats);
    out << ",\n";
    write_index_stats(out, "tetgen_triface_indices", triface_stats);
    out << ",\n";
    out << "  \"estimated_unique_line_count\": " << unique_line_count << ",\n";
    out << "  \"line_capacity_nnode_times_32\": " << line_capacity << ",\n";
    out << "  \"estimated_line_capacity_exceeded\": "
        << (unique_line_count > line_capacity ? "true" : "false") << "\n";
    out << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: deformsim_ply_tetra_diagnostic <input.ply> <output.json>\n";
        return 2;
    }

    const std::filesystem::path input_path = std::filesystem::absolute(argv[1]);
    const std::filesystem::path output_path = std::filesystem::absolute(argv[2]);

    Surface surface;
    Object object;
    tetgenio input;
    tetgenio output;
    bool tetgen_completed = false;
    std::string stage = "startup";
    std::string diagnostic = "not started";

    try {
        if (!std::filesystem::exists(input_path)) {
            throw std::runtime_error("Input PLY not found: " + input_path.string());
        }

        stage = "precheck_ply";
        const PlyPrecheckResult precheck = precheck_ascii_ply(input_path);
        if (!precheck.ok) {
            write_precheck_failure_json(output_path, input_path, precheck, stage);
            return 1;
        }

        stage = "read_ply";
        if (!surface.ReadPLY(input_path.string())) {
            diagnostic = "Surface::ReadPLY failed";
            write_json_result(
                output_path, input_path, surface, object, DiagnosticBoundingBox{},
                make_empty_index_stats(), make_empty_index_stats(), 0, output,
                false, stage, diagnostic
            );
            return 1;
        }

        const DiagnosticBoundingBox bbox = compute_bounding_box(surface);
        const IndexStats surface_stats = surface_face_index_stats(surface);
        const int degenerate_count = count_degenerate_surface_triangles(surface, 1e-12);

        stage = "copy_surface_to_object";
        copy_surface_to_object(surface, object);
        const IndexStats object_stats = object_triangle_index_stats(object);

        if (surface_stats.out_of_range_count > 0 || object_stats.out_of_range_count > 0) {
            diagnostic = "Input contains out-of-range face indices";
            write_json_result(
                output_path, input_path, surface, object, bbox, surface_stats, object_stats,
                degenerate_count, output, false, stage, diagnostic
            );
            return 1;
        }

        stage = "fill_tetgen_input";
        fill_tetgen_input(object, input);

        stage = "tetgen_call";
        diagnostic = "Checkpoint before TetGen call";
        write_json_result(
            output_path, input_path, surface, object, bbox, surface_stats, object_stats,
            degenerate_count, output, false, stage, diagnostic
        );

        char switches[] = "pYQ";
        try {
            tetrahedralize(switches, &input, &output);
        } catch (int code) {
            diagnostic = "TetGen terminated with code " + std::to_string(code);
            write_json_result(
                output_path, input_path, surface, object, bbox, surface_stats, object_stats,
                degenerate_count, output, false, stage, diagnostic
            );
            std::cerr << "[error] stage=" << stage << " diagnostic=" << diagnostic << "\n";
            return code != 0 ? code : 1;
        }
        tetgen_completed = true;

        stage = "tetgen_output_validated";
        diagnostic = "TetGen completed; diagnostic did not run DeformSim post-processing.";
        write_json_result(
            output_path, input_path, surface, object, bbox, surface_stats, object_stats,
            degenerate_count, output, tetgen_completed, stage, diagnostic
        );

        std::cout << "[ok] deformsim ply-to-tetra diagnostic"
                  << " surface_vertices=" << surface.nNode
                  << " surface_faces=" << surface.nTriangle
                  << " tetgen_vertices=" << output.numberofpoints
                  << " tetgen_tetra=" << output.numberoftetrahedra
                  << " tetgen_boundary_faces=" << output.numberoftrifaces
                  << " output=" << output_path.string() << "\n";
        return 0;
    } catch (const std::exception& ex) {
        diagnostic = ex.what();
        try {
            write_json_result(
                output_path, input_path, surface, object, compute_bounding_box(surface),
                surface_face_index_stats(surface), object_triangle_index_stats(object),
                count_degenerate_surface_triangles(surface, 1e-12),
                output, tetgen_completed, stage, diagnostic
            );
        } catch (...) {
        }
        std::cerr << "[error] stage=" << stage << " diagnostic=" << diagnostic << "\n";
        return 1;
    }
}
