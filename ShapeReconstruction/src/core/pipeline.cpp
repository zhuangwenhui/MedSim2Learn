#include "mvrmesh/core/pipeline.h"

#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/core/algorithms.h"
#include "mvrmesh/core/topology.h"

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
    if (!(options.adaptive_split_ratio > 0.0 && options.adaptive_split_ratio <= 1.0)) {
        throw std::runtime_error("--adaptive-split-ratio must be in (0, 1]");
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
    const std::filesystem::path& base_output
) {
    std::filesystem::path p = base_output;
    p.replace_extension(".ply");
    return { std::move(p) };
}

std::string surface_mode_to_string(SurfaceMode mode) {
    if (mode == SurfaceMode::AdaptiveRemesh) {
        return "adaptive_remesh";
    }
    return "direct_surface";
}

}  // namespace mvrmesh
