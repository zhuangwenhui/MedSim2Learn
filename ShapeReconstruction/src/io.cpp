#include "mvrmesh/io.h"

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

#include "mvrmesh/geometry.h"
#include "mvrmesh/topology.h"

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

void write_stl(
    const std::filesystem::path& path,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("Failed to open output file: " + path.string());
    }

    std::string name = path.stem().string();
    if (name.empty()) {
        name = "mesh";
    }
    std::replace(name.begin(), name.end(), ' ', '_');

    output << "solid " << name << "\n";
    output << std::setprecision(9) << std::defaultfloat;

    for (const Face& f : faces) {
        const Vec3& v1 = vertices.at(static_cast<std::size_t>(f[0]));
        const Vec3& v2 = vertices.at(static_cast<std::size_t>(f[1]));
        const Vec3& v3 = vertices.at(static_cast<std::size_t>(f[2]));
        const Vec3 n = face_normal(v1, v2, v3);
        output << "  facet normal " << n.x << " " << n.y << " " << n.z << "\n";
        output << "    outer loop\n";
        output << "      vertex " << v1.x << " " << v1.y << " " << v1.z << "\n";
        output << "      vertex " << v2.x << " " << v2.y << " " << v2.z << "\n";
        output << "      vertex " << v3.x << " " << v3.y << " " << v3.z << "\n";
        output << "    endloop\n";
        output << "  endfacet\n";
    }

    output << "endsolid " << name << "\n";
}

}  // namespace mvrmesh
