#include "mvrmesh/core/io.h"

#include <algorithm>
#include <cctype>
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

bool is_section_marker(const std::string& line) {
    if (line.size() < 2 || line[0] != '@') {
        return false;
    }
    return std::all_of(line.begin() + 1, line.end(), [](char ch) { return std::isdigit(static_cast<unsigned char>(ch)) != 0; });
}

int parse_required_int(const std::vector<std::string>& parts, const std::string& label) {
    if (parts.size() < 2) {
        throw std::runtime_error("Missing numeric value for " + label);
    }
    std::size_t consumed = 0;
    const int value = std::stoi(parts[1], &consumed);
    if (consumed != parts[1].size()) {
        throw std::runtime_error("Invalid numeric value for " + label + ": " + parts[1]);
    }
    return value;
}

std::vector<Vec3> parse_vertices(const std::vector<std::string>& lines) {
    std::vector<Vec3> out;
    out.reserve(lines.size());
    for (const std::string& line : lines) {
        const std::vector<std::string> parts = split_ws(line);
        if (parts.size() >= 3) {
            out.push_back(Vec3{
                std::stod(parts[0]),
                std::stod(parts[1]),
                std::stod(parts[2]),
            });
        }
    }
    return out;
}

std::vector<Face> parse_triangles(const std::vector<std::string>& lines) {
    std::vector<Face> out;
    out.reserve(lines.size());
    for (const std::string& line : lines) {
        const std::vector<std::string> parts = split_ws(line);
        if (parts.size() >= 3) {
            out.push_back(Face{
                std::stoi(parts[0]),
                std::stoi(parts[1]),
                std::stoi(parts[2]),
            });
        }
    }
    return out;
}

std::vector<Tet> parse_tetra(const std::vector<std::string>& lines) {
    std::vector<Tet> out;
    out.reserve(lines.size());
    for (const std::string& line : lines) {
        const std::vector<std::string> parts = split_ws(line);
        if (parts.size() >= 4) {
            out.push_back(Tet{
                std::stoi(parts[0]),
                std::stoi(parts[1]),
                std::stoi(parts[2]),
                std::stoi(parts[3]),
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

    std::map<int, std::vector<std::string>> sections;
    bool has_active_section = false;
    int section_id = -1;
    std::optional<int> declared_vertices;
    std::optional<int> declared_triangles;
    std::optional<int> declared_tetra;

    std::string raw;
    while (std::getline(input, raw)) {
        const std::string line = trim_copy(raw);
        if (line.empty() || line[0] == '#') {
            continue;
        }

        if (!has_active_section) {
            if (line.rfind("nVertex", 0) == 0) {
                declared_vertices = parse_required_int(split_ws(line), "nVertex");
            } else if (line.rfind("nTriangle", 0) == 0) {
                declared_triangles = parse_required_int(split_ws(line), "nTriangle");
            } else if (line.rfind("nTetrahedron", 0) == 0) {
                declared_tetra = parse_required_int(split_ws(line), "nTetrahedron");
            }
        }

        if (is_section_marker(line)) {
            section_id = std::stoi(line.substr(1));
            has_active_section = true;
            sections[section_id];
            continue;
        }

        if (has_active_section) {
            sections[section_id].push_back(line);
        }
    }

    const std::vector<Vec3> vertices = parse_vertices(sections[1]);
    const std::vector<Face> triangles_raw = parse_triangles(sections[3]);
    const std::vector<Tet> tets_raw = parse_tetra(sections[4]);

    if (vertices.empty()) {
        throw std::runtime_error("No vertices were found in section @1.");
    }

    ParsedMvr parsed;
    parsed.vertices = vertices;
    parsed.triangles = normalize_faces_indices(triangles_raw, static_cast<int>(vertices.size()));
    parsed.tetrahedra = normalize_tet_indices(tets_raw, static_cast<int>(vertices.size()));

    if (declared_vertices.has_value() && *declared_vertices != static_cast<int>(vertices.size())) {
        std::cout << "[warn] header nVertex=" << *declared_vertices
                  << ", parsed=" << vertices.size() << "\n";
    }
    if (declared_triangles.has_value() && *declared_triangles != static_cast<int>(triangles_raw.size())) {
        std::cout << "[warn] header nTriangle=" << *declared_triangles
                  << ", parsed=" << triangles_raw.size() << "\n";
    }
    if (declared_tetra.has_value() && *declared_tetra != static_cast<int>(tets_raw.size())) {
        std::cout << "[warn] header nTetrahedron=" << *declared_tetra
                  << ", parsed=" << tets_raw.size() << "\n";
    }

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
    std::vector<Vec3>& out_vertices,
    std::vector<Face>& out_faces
) {
    out_vertices.clear();
    out_faces.clear();

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

    out_vertices.reserve(v_count);
    for (std::size_t i = 0; i < v_count; ++i) {
        if (!std::getline(in, line)) {
            throw std::runtime_error("read_ply: unexpected EOF reading vertex " + std::to_string(i));
        }
        std::istringstream vs(line);
        double x, y, z;
        if (!(vs >> x >> y >> z)) {
            throw std::runtime_error("read_ply: bad vertex line " + std::to_string(i));
        }
        out_vertices.push_back({x, y, z});
    }

    out_faces.reserve(f_count);
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
        out_faces.push_back(f);
    }
}

}  // namespace mvrmesh
