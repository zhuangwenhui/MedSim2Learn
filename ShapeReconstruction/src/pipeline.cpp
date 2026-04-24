#include "mvrmesh/pipeline.h"

#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/algorithms.h"
#include "mvrmesh/topology.h"

namespace mvrmesh {

BuildResult build_surface(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& triangles,
    const std::vector<Tet>& tets,
    const BuildOptions& options
) {
    if (options.adaptive_iterations < 1) {
        throw std::runtime_error("--adaptive-iterations must be >= 1");
    }
    if (options.volumetric_iterations < 1) {
        throw std::runtime_error("--volumetric-iterations must be >= 1");
    }
    if (!(options.adaptive_split_ratio > 0.0 && options.adaptive_split_ratio <= 1.0)) {
        throw std::runtime_error("--adaptive-split-ratio must be in (0, 1]");
    }
    if (options.adaptive_remesh && options.volumetric_reconstruct) {
        throw std::runtime_error("Only one of --adaptive-remesh or --volumetric-reconstruct can be enabled.");
    }

    if (options.volumetric_reconstruct) {
        if (tets.empty()) {
            throw std::runtime_error("No tetrahedra in @4. --volumetric-reconstruct requires tetra mesh.");
        }
        std::vector<Vec3> out_vertices = vertices;
        std::vector<Tet> out_tets = tets;
        for (int i = 0; i < options.volumetric_iterations; ++i) {
            auto subdivided = subdivide_tetrahedra(out_vertices, out_tets);
            out_vertices = std::move(subdivided.first);
            out_tets = std::move(subdivided.second);
        }
        BuildResult result;
        result.vertices = std::move(out_vertices);
        result.faces = boundary_faces_from_tets(result.vertices, out_tets);
        result.mode = SurfaceMode::VolumetricReconstruct;
        return result;
    }

    std::vector<Face> base_faces;
    if (!triangles.empty()) {
        base_faces = triangles;
    } else if (!tets.empty()) {
        base_faces = boundary_faces_from_tets(vertices, tets);
    } else {
        throw std::runtime_error("No triangles in @3 and no tetrahedra in @4.");
    }

    if (options.adaptive_remesh) {
        auto remeshed = adaptive_remesh(
            vertices,
            base_faces,
            options.adaptive_iterations,
            options.adaptive_split_ratio
        );
        BuildResult result;
        result.vertices = std::move(remeshed.first);
        result.faces = std::move(remeshed.second);
        result.mode = SurfaceMode::AdaptiveRemesh;
        return result;
    }

    BuildResult result;
    result.vertices = vertices;
    result.faces = std::move(base_faces);
    result.mode = SurfaceMode::DirectSurface;
    return result;
}

std::vector<std::filesystem::path> outputs_for_mode(
    const std::filesystem::path& base_output,
    OutputFormat format
) {
    std::vector<std::filesystem::path> outputs;
    if (format == OutputFormat::Ply) {
        std::filesystem::path p = base_output;
        p.replace_extension(".ply");
        outputs.push_back(std::move(p));
    } else if (format == OutputFormat::Stl) {
        std::filesystem::path p = base_output;
        p.replace_extension(".stl");
        outputs.push_back(std::move(p));
    } else {
        std::filesystem::path p = base_output;
        p.replace_extension(".ply");
        outputs.push_back(p);
        p = base_output;
        p.replace_extension(".stl");
        outputs.push_back(std::move(p));
    }
    return outputs;
}

OutputFormat parse_output_format(const std::string& text) {
    std::string lowered = text;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });

    if (lowered == "ply") {
        return OutputFormat::Ply;
    }
    if (lowered == "stl") {
        return OutputFormat::Stl;
    }
    if (lowered == "both") {
        return OutputFormat::Both;
    }
    throw std::runtime_error("Invalid --format value: " + text + " (expected: ply, stl, both)");
}

std::string surface_mode_to_string(SurfaceMode mode) {
    if (mode == SurfaceMode::AdaptiveRemesh) {
        return "adaptive_remesh";
    }
    if (mode == SurfaceMode::VolumetricReconstruct) {
        return "volumetric_reconstruct";
    }
    return "direct_surface";
}

}  // namespace mvrmesh

