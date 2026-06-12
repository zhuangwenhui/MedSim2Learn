#include "stdafx.h"

#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include "object.h"
#include "surface.h"


namespace {

double tetra_volume(const Object& object, const Tetrahedron& tetra) {
    Vector3f a = object.vertex[tetra.set[0]].new_coord;
    Vector3f b = object.vertex[tetra.set[1]].new_coord;
    Vector3f c = object.vertex[tetra.set[2]].new_coord;
    Vector3f d = object.vertex[tetra.set[3]].new_coord;

    Vector3f ab = b - a;
    Vector3f ac = c - a;
    Vector3f ad = d - a;
    return std::fabs(static_cast<double>(ad * ab.CrossProduct(ac))) / 6.0;
}

double total_tetra_volume(const Object& object) {
    double total = 0.0;
    for (int i = 0; i < object.nTetra; ++i) {
        total += tetra_volume(object, object.tetra[i]);
    }
    return total;
}

std::string json_escape(const std::string& text) {
    std::string escaped;
    escaped.reserve(text.size());
    for (char ch : text) {
        if (ch == '\\' || ch == '"') {
            escaped.push_back('\\');
        }
        escaped.push_back(ch);
    }
    return escaped;
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

void write_json(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_path,
    const Surface& surface,
    const Object& object,
    double elapsed_ms,
    double volume
) {
    std::filesystem::create_directories(output_path.parent_path());
    std::ofstream out(output_path);
    if (!out) {
        throw std::runtime_error("Failed to open smoke JSON output: " + output_path.string());
    }

    out << "{\n";
    out << "  \"success\": true,\n";
    out << "  \"input_ply\": \"" << json_escape(input_path.string()) << "\",\n";
    out << "  \"surface_vertex_count\": " << surface.nNode << ",\n";
    out << "  \"surface_face_count\": " << surface.nTriangle << ",\n";
    out << "  \"deformsim_vertex_count\": " << object.nNode << ",\n";
    out << "  \"deformsim_tetra_count\": " << object.nTetra << ",\n";
    out << "  \"deformsim_boundary_face_count\": " << object.nTriangle << ",\n";
    out << "  \"deformsim_total_volume\": " << volume << ",\n";
    out << "  \"elapsed_ms\": " << elapsed_ms << "\n";
    out << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 3) {
            std::cerr << "Usage: deformsim_ply_tetra_smoke <input.ply> <output.json>\n";
            return 2;
        }

        const std::filesystem::path input_path = std::filesystem::absolute(argv[1]);
        const std::filesystem::path output_path = std::filesystem::absolute(argv[2]);
        if (!std::filesystem::exists(input_path)) {
            throw std::runtime_error("Input PLY not found: " + input_path.string());
        }

        Surface surface;
        if (!surface.ReadPLY(input_path.string())) {
            throw std::runtime_error("Surface::ReadPLY failed for: " + input_path.string());
        }
        if (surface.nNode <= 0 || surface.nTriangle <= 0) {
            throw std::runtime_error("Surface::ReadPLY produced an empty surface.");
        }

        Object object;
        copy_surface_to_object(surface, object);

        const auto start = std::chrono::steady_clock::now();
        char switches[] = "pY";
        object.ComputeQualityTetrahedralMesh(switches);
        const auto end = std::chrono::steady_clock::now();

        if (object.nTetra <= 0) {
            throw std::runtime_error("DeformSim tetrahedralization produced no tetrahedra.");
        }

        const double elapsed_ms =
            std::chrono::duration<double, std::milli>(end - start).count();
        const double volume = total_tetra_volume(object);
        write_json(output_path, input_path, surface, object, elapsed_ms, volume);

        std::cout << "[ok] deformsim ply-to-tetra smoke"
                  << " surface_vertices=" << surface.nNode
                  << " surface_faces=" << surface.nTriangle
                  << " tetrahedra=" << object.nTetra
                  << " elapsed_ms=" << elapsed_ms
                  << " output=" << output_path.string() << "\n";
    } catch (const std::exception& ex) {
        std::cerr << "[error] " << ex.what() << "\n";
        return 1;
    }

    return 0;
}
