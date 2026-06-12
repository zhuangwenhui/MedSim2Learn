#include "mvrmesh/core/io.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/core/topology.h"

namespace mvrmesh {

namespace {

std::string trim_copy(const std::string& input) {
    std::size_t start = 0;
    while (start < input.size() && std::isspace(static_cast<unsigned char>(input[start])) != 0) {
        ++start;
    }
    std::size_t end = input.size();
    while (end > start && std::isspace(static_cast<unsigned char>(input[end - 1])) != 0) {
        --end;
    }
    return input.substr(start, end - start);
}

std::vector<std::string> split_ws(const std::string& line) {
    std::istringstream iss(line);
    std::vector<std::string> parts;
    std::string part;
    while (iss >> part) {
        parts.push_back(part);
    }
    return parts;
}

// Section markers look like "@1": an '@' followed by digits only.
bool is_section_marker(const std::string& line) {
    if (line.size() < 2 || line[0] != '@') {
        return false;
    }
    return std::all_of(line.begin() + 1, line.end(), [](char ch) { return std::isdigit(static_cast<unsigned char>(ch)) != 0; });
}

// A content line of an .mvr section together with its 1-based line number in
// the source file, so parse errors can point back at the offending line.
struct NumberedLine {
    std::size_t line_number = 0;
    std::string text;
};

[[noreturn]] void throw_field_error(
    const std::string& token,
    const std::filesystem::path& path,
    std::size_t line_number,
    const std::string& context,
    const std::string& reason
) {
    std::ostringstream oss;
    oss << "Failed to parse " << context << " in " << path.string()
        << " at line " << line_number << ": " << reason << " '" << token << "'";
    throw std::runtime_error(oss.str());
}

int parse_int_field(
    const std::string& token,
    const std::filesystem::path& path,
    std::size_t line_number,
    const std::string& context
) {
    std::size_t consumed = 0;
    int value = 0;
    try {
        value = std::stoi(token, &consumed);
    } catch (const std::exception&) {
        throw_field_error(token, path, line_number, context, "invalid integer token");
    }
    if (consumed != token.size()) {
        throw_field_error(token, path, line_number, context, "trailing characters in integer token");
    }
    return value;
}

double parse_double_field(
    const std::string& token,
    const std::filesystem::path& path,
    std::size_t line_number,
    const std::string& context
) {
    std::size_t consumed = 0;
    double value = 0.0;
    try {
        value = std::stod(token, &consumed);
    } catch (const std::exception&) {
        throw_field_error(token, path, line_number, context, "invalid floating-point token");
    }
    if (consumed != token.size()) {
        throw_field_error(token, path, line_number, context, "trailing characters in floating-point token");
    }
    if (!std::isfinite(value)) {
        throw_field_error(token, path, line_number, context, "non-finite floating-point token");
    }
    return value;
}

int parse_required_int(
    const std::vector<std::string>& parts,
    const std::string& label,
    const std::filesystem::path& path,
    std::size_t line_number
) {
    if (parts.size() < 2) {
        throw std::runtime_error("Missing numeric value for " + label);
    }
    return parse_int_field(parts[1], path, line_number, label);
}

std::vector<Vec3> parse_vertices(
    const std::vector<NumberedLine>& lines,
    const std::filesystem::path& path
) {
    std::vector<Vec3> out;
    out.reserve(lines.size());
    for (const NumberedLine& line : lines) {
        const std::vector<std::string> parts = split_ws(line.text);
        if (parts.size() >= 3) {
            out.push_back(Vec3{
                parse_double_field(parts[0], path, line.line_number, "vertex section @1"),
                parse_double_field(parts[1], path, line.line_number, "vertex section @1"),
                parse_double_field(parts[2], path, line.line_number, "vertex section @1"),
            });
        }
    }
    return out;
}

std::vector<Face> parse_triangles(
    const std::vector<NumberedLine>& lines,
    const std::filesystem::path& path
) {
    std::vector<Face> out;
    out.reserve(lines.size());
    for (const NumberedLine& line : lines) {
        const std::vector<std::string> parts = split_ws(line.text);
        if (parts.size() >= 3) {
            out.push_back(Face{
                parse_int_field(parts[0], path, line.line_number, "triangle section @3"),
                parse_int_field(parts[1], path, line.line_number, "triangle section @3"),
                parse_int_field(parts[2], path, line.line_number, "triangle section @3"),
            });
        }
    }
    return out;
}

std::vector<Tet> parse_tetra(
    const std::vector<NumberedLine>& lines,
    const std::filesystem::path& path
) {
    std::vector<Tet> out;
    out.reserve(lines.size());
    for (const NumberedLine& line : lines) {
        const std::vector<std::string> parts = split_ws(line.text);
        if (parts.size() >= 4) {
            out.push_back(Tet{
                parse_int_field(parts[0], path, line.line_number, "tetrahedron section @4"),
                parse_int_field(parts[1], path, line.line_number, "tetrahedron section @4"),
                parse_int_field(parts[2], path, line.line_number, "tetrahedron section @4"),
                parse_int_field(parts[3], path, line.line_number, "tetrahedron section @4"),
            });
        }
    }
    return out;
}

}  // namespace

ParsedMvr parse_mvr(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::in);
    if (!input) {
        throw std::runtime_error("Failed to open input file: " + path.string());
    }

    std::map<int, std::vector<NumberedLine>> sections;
    bool has_active_section = false;
    int section_id = -1;
    std::optional<int> declared_vertices;
    std::optional<int> declared_triangles;
    std::optional<int> declared_tetra;
    BoundingBox bounding_box;

    std::string raw;
    std::size_t line_number = 0;
    while (std::getline(input, raw)) {
        ++line_number;
        const std::string line = trim_copy(raw);
        if (line.empty() || line[0] == '#') {
            continue;
        }

        // Header fields are only recognized before the first section marker.
        if (!has_active_section) {
            if (line.rfind("nVertex", 0) == 0) {
                declared_vertices = parse_required_int(split_ws(line), "nVertex", path, line_number);
            } else if (line.rfind("nTriangle", 0) == 0) {
                declared_triangles = parse_required_int(split_ws(line), "nTriangle", path, line_number);
            } else if (line.rfind("nTetrahedron", 0) == 0) {
                declared_tetra = parse_required_int(split_ws(line), "nTetrahedron", path, line_number);
            } else if (line.rfind("Bounding Box", 0) == 0) {
                const std::vector<std::string> bb_parts = split_ws(line);
                if (bb_parts.size() >= 8) {
                    try {
                        bounding_box.x_min = std::stod(bb_parts[2]);
                        bounding_box.x_max = std::stod(bb_parts[3]);
                        bounding_box.y_min = std::stod(bb_parts[4]);
                        bounding_box.y_max = std::stod(bb_parts[5]);
                        bounding_box.z_min = std::stod(bb_parts[6]);
                        bounding_box.z_max = std::stod(bb_parts[7]);
                        bounding_box.valid = true;
                    } catch (const std::exception&) {
                        // Malformed values: leave valid=false
                    }
                }
            }
        }

        if (is_section_marker(line)) {
            section_id = parse_int_field(line.substr(1), path, line_number, "section marker");
            has_active_section = true;
            // Touch the map entry so a section with no content lines still exists.
            sections[section_id];
            continue;
        }

        if (has_active_section) {
            sections[section_id].push_back(NumberedLine{line_number, line});
        }
    }

    const std::vector<Vec3> vertices = parse_vertices(sections[1], path);
    const std::vector<Face> triangles_raw = parse_triangles(sections[3], path);
    const std::vector<Tet> tets_raw = parse_tetra(sections[4], path);

    if (vertices.empty()) {
        throw std::runtime_error("No vertices were found in section @1.");
    }

    ParsedMvr parsed;
    parsed.vertices = vertices;
    parsed.triangles = normalize_faces_indices(triangles_raw, static_cast<int>(vertices.size()));
    parsed.tetrahedra = normalize_tet_indices(tets_raw, static_cast<int>(vertices.size()));

    // Header counts are advisory: a mismatch warns but does not fail the parse.
    if (declared_vertices.has_value() && *declared_vertices != static_cast<int>(vertices.size())) {
        std::cerr << "[warn] header nVertex=" << *declared_vertices
                  << ", parsed=" << vertices.size() << "\n";
    }
    if (declared_triangles.has_value() && *declared_triangles != static_cast<int>(triangles_raw.size())) {
        std::cerr << "[warn] header nTriangle=" << *declared_triangles
                  << ", parsed=" << triangles_raw.size() << "\n";
    }
    if (declared_tetra.has_value() && *declared_tetra != static_cast<int>(tets_raw.size())) {
        std::cerr << "[warn] header nTetrahedron=" << *declared_tetra
                  << ", parsed=" << tets_raw.size() << "\n";
    }

    parsed.bounding_box = bounding_box;
    return parsed;
}

void write_ply(
    const std::filesystem::path& path,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("Failed to open output file: " + path.string());
    }

    output << "ply\n";
    output << "format ascii 1.0\n";
    output << "element vertex " << vertices.size() << "\n";
    output << "property float x\n";
    output << "property float y\n";
    output << "property float z\n";
    output << "element face " << faces.size() << "\n";
    output << "property list uchar int vertex_indices\n";
    output << "end_header\n";
    // 9 significant digits: enough to round-trip the float-typed properties
    // declared in the header.
    output << std::setprecision(9) << std::defaultfloat;
    for (const Vec3& v : vertices) {
        output << v.x << " " << v.y << " " << v.z << "\n";
    }
    for (const Face& f : faces) {
        output << "3 " << f[0] << " " << f[1] << " " << f[2] << "\n";
    }
}

void read_ply(
    const std::filesystem::path& path,
    std::vector<Vec3>& vertices_out,
    std::vector<Face>& faces_out
) {
    vertices_out.clear();
    faces_out.clear();

    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("read_ply: cannot open " + path.string());
    }

    std::string line;
    if (!std::getline(in, line) || line != "ply") {
        throw std::runtime_error("read_ply: expected 'ply' magic in " + path.string());
    }

    bool ascii = false;
    std::size_t v_count = 0;
    std::size_t f_count = 0;

    while (std::getline(in, line)) {
        std::istringstream ss(line);
        std::string tok;
        ss >> tok;
        if (tok == "format") {
            std::string fmt;
            ss >> fmt;
            if (fmt != "ascii") {
                throw std::runtime_error("read_ply: only ascii format supported");
            }
            ascii = true;
        } else if (tok == "element") {
            std::string elem;
            std::size_t cnt = 0;
            ss >> elem >> cnt;
            if (elem == "vertex") v_count = cnt;
            else if (elem == "face") f_count = cnt;
        } else if (tok == "end_header") {
            break;
        }
    }
    if (!ascii) throw std::runtime_error("read_ply: missing format directive");

    vertices_out.reserve(v_count);
    for (std::size_t i = 0; i < v_count; ++i) {
        if (!std::getline(in, line)) {
            throw std::runtime_error("read_ply: unexpected EOF reading vertex " + std::to_string(i));
        }
        std::istringstream vs(line);
        double x, y, z;
        if (!(vs >> x >> y >> z)) {
            throw std::runtime_error("read_ply: bad vertex line " + std::to_string(i));
        }
        vertices_out.push_back({x, y, z});
    }

    faces_out.reserve(f_count);
    for (std::size_t i = 0; i < f_count; ++i) {
        if (!std::getline(in, line)) {
            throw std::runtime_error("read_ply: unexpected EOF reading face " + std::to_string(i));
        }
        std::istringstream fs(line);
        int n_verts = 0;
        if (!(fs >> n_verts) || n_verts != 3) {
            throw std::runtime_error("read_ply: only triangle faces supported (face " + std::to_string(i) + ")");
        }
        Face f{0, 0, 0};
        if (!(fs >> f[0] >> f[1] >> f[2])) {
            throw std::runtime_error("read_ply: bad face indices on face " + std::to_string(i));
        }
        faces_out.push_back(f);
    }
}

}  // namespace mvrmesh
