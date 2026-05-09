#include "mvrmesh/core/pipeline.h"

#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/core/algorithms.h"
#include "mvrmesh/core/reconstruction_pipeline.h"
#include "mvrmesh/core/smoothing.h"
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
    if (options.uniform_iterations < 1) {
        throw std::runtime_error("--uniform-iterations must be >= 1");
    }
    if (options.taubin_smooth && !options.uniform_subdivide) {
        throw std::runtime_error("--taubin-smooth requires --uniform-subdivide");
    }
    if (options.taubin_iterations < 0) {
        throw std::runtime_error("--taubin-iterations must be >= 0");
    }
    if (options.adaptive_remesh && options.uniform_subdivide) {
        throw std::runtime_error("--uniform-subdivide conflicts with --adaptive-remesh");
    }
    if (options.sdf_reconstruct && options.adaptive_remesh) {
        throw std::runtime_error("--sdf-reconstruct conflicts with --adaptive-remesh");
    }
    if (options.sdf_reconstruct && options.uniform_subdivide) {
        throw std::runtime_error("--sdf-reconstruct conflicts with --uniform-subdivide");
    }
    if (options.sdf_reconstruct && options.taubin_smooth) {
        throw std::runtime_error("--sdf-reconstruct conflicts with --taubin-smooth");
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

    if (options.uniform_subdivide) {
        auto subdivided = uniform_subdivide(
            vertices,
            base_faces,
            options.uniform_iterations
        );
        BuildResult result;
        result.faces = std::move(subdivided.second);
        if (options.taubin_smooth) {
            result.vertices = taubin_smooth(
                subdivided.first,
                result.faces,
                options.taubin_iterations,
                options.taubin_lambda,
                options.taubin_mu,
                options.taubin_preserve_boundary
            );
            result.mode = SurfaceMode::UniformTaubin;
        } else {
            result.vertices = std::move(subdivided.first);
            result.mode = SurfaceMode::UniformSubdivide;
        }
        return result;
    }

    if (options.sdf_reconstruct) {
        SdfRemeshOptions remesh_options;
        remesh_options.sdf_resolution = options.sdf_resolution;
        remesh_options.padding_ratio = options.sdf_padding_ratio;
        remesh_options.sharp_edge_dihedral_degrees = options.sdf_sharp_edge_degrees;
        remesh_options.target_edge_length = options.sdf_target_edge_length;
        remesh_options.remesh_iterations = options.sdf_remesh_iterations;

        SdfRemeshResult remeshed = reconstruct_and_remesh_surface(
            vertices,
            base_faces,
            remesh_options
        );

        BuildResult result;
        result.vertices = std::move(remeshed.vertices);
        result.faces = std::move(remeshed.faces);
        result.mode = SurfaceMode::SdfReconstruct;
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
    if (mode == SurfaceMode::UniformSubdivide) {
        return "uniform_subdivide";
    }
    if (mode == SurfaceMode::UniformTaubin) {
        return "uniform_taubin";
    }
    if (mode == SurfaceMode::SdfReconstruct) {
        return "sdf_reconstruct";
    }
    return "direct_surface";
}

}  // namespace mvrmesh
