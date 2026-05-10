// src/config/pipeline_config.cpp

#include "mvrmesh/config/pipeline_config.h"

#include <cmath>
#include <stdexcept>
#include <string>

#include "mvrmesh/core/reconstruction.h"

namespace mvrmesh {

namespace {

void require_finite(double v, const char* field) {
    if (!std::isfinite(v)) {
        throw std::runtime_error(
            std::string(field) + " must be finite");
    }
}

}  // namespace

void PipelineConfig::validate() const {
    // -- global --
    if (input.empty()) {
        throw std::runtime_error("input path must not be empty");
    }

    // -- cgal_mesh_post conflicts with non-DirectSurface modes --
    if (cgal_mesh_post) {
        switch (mode) {
            case SurfaceMode::AdaptiveRemesh:
            case SurfaceMode::UniformSubdivide:
            case SurfaceMode::UniformTaubin:
            case SurfaceMode::SdfReconstruct:
                throw std::runtime_error(
                    "cgal_mesh_post conflicts with mode "
                    + surface_mode_name(mode));
            case SurfaceMode::DirectSurface:
                break;
        }
    }

    // -- per-mode validation --
    switch (mode) {
        case SurfaceMode::AdaptiveRemesh:
            if (adaptive_remesh.iterations < 1) {
                throw std::runtime_error(
                    "adaptive_remesh.iterations must be >= 1");
            }
            if (adaptive_remesh.split_ratio <= 0.0
                || adaptive_remesh.split_ratio > 1.0) {
                throw std::runtime_error(
                    "adaptive_remesh.split_ratio must be in (0, 1]");
            }
            break;

        case SurfaceMode::UniformSubdivide:
            if (uniform_subdivide.iterations < 1) {
                throw std::runtime_error(
                    "uniform_subdivide.iterations must be >= 1");
            }
            break;

        case SurfaceMode::UniformTaubin:
            if (uniform_subdivide.iterations < 1) {
                throw std::runtime_error(
                    "uniform_subdivide.iterations must be >= 1");
            }
            if (taubin.iterations < 0) {
                throw std::runtime_error(
                    "taubin.iterations must be >= 0");
            }
            require_finite(taubin.lambda, "taubin.lambda");
            require_finite(taubin.mu, "taubin.mu");
            break;

        case SurfaceMode::SdfReconstruct:
            if (sdf_reconstruct.resolution < 2
                || sdf_reconstruct.resolution > kMaxSdfGridResolution) {
                throw std::runtime_error(
                    "sdf_reconstruct.resolution must be in [2, "
                    + std::to_string(kMaxSdfGridResolution) + "]");
            }
            require_finite(sdf_reconstruct.padding_ratio,
                           "sdf_reconstruct.padding_ratio");
            if (sdf_reconstruct.padding_ratio < 0.0) {
                throw std::runtime_error(
                    "sdf_reconstruct.padding_ratio must be >= 0");
            }
            require_finite(sdf_reconstruct.target_edge_length,
                           "sdf_reconstruct.target_edge_length");
            if (sdf_reconstruct.target_edge_length < 0.0) {
                throw std::runtime_error(
                    "sdf_reconstruct.target_edge_length must be >= 0");
            }
            if (sdf_reconstruct.remesh_iterations < 1) {
                throw std::runtime_error(
                    "sdf_reconstruct.remesh_iterations must be >= 1");
            }
            if (sdf_reconstruct.sharp_edge_dihedral_degrees <= 0.0
                || sdf_reconstruct.sharp_edge_dihedral_degrees >= 180.0) {
                throw std::runtime_error(
                    "sdf_reconstruct.sharp_edge_dihedral_degrees "
                    "must be in (0, 180)");
            }
            break;

        case SurfaceMode::DirectSurface:
            // No mode-specific validation.
            break;
    }

    // -- cgal_mesh_post sub-struct validation --
    if (cgal_mesh_post) {
        if (cgal_mesh.sharp_edge_dihedral_degrees <= 0.0
            || cgal_mesh.sharp_edge_dihedral_degrees >= 180.0) {
            throw std::runtime_error(
                "cgal_mesh.sharp_edge_dihedral_degrees must be in (0, 180)");
        }
        if (cgal_mesh.target_edge_length < 0.0) {
            throw std::runtime_error(
                "cgal_mesh.target_edge_length must be >= 0");
        }
        if (cgal_mesh.remesh_iterations < 1) {
            throw std::runtime_error(
                "cgal_mesh.remesh_iterations must be >= 1");
        }
    }
}

SurfaceMode parse_surface_mode(const std::string& name) {
    if (name == "direct_surface")    return SurfaceMode::DirectSurface;
    if (name == "adaptive_remesh")   return SurfaceMode::AdaptiveRemesh;
    if (name == "uniform_subdivide") return SurfaceMode::UniformSubdivide;
    if (name == "uniform_taubin")    return SurfaceMode::UniformTaubin;
    if (name == "sdf_reconstruct")   return SurfaceMode::SdfReconstruct;
    throw std::runtime_error("Unknown surface mode: " + name);
}

std::string surface_mode_name(SurfaceMode mode) {
    switch (mode) {
        case SurfaceMode::DirectSurface:    return "direct_surface";
        case SurfaceMode::AdaptiveRemesh:   return "adaptive_remesh";
        case SurfaceMode::UniformSubdivide: return "uniform_subdivide";
        case SurfaceMode::UniformTaubin:    return "uniform_taubin";
        case SurfaceMode::SdfReconstruct:   return "sdf_reconstruct";
    }
    throw std::runtime_error("Unknown SurfaceMode enum value");
}

}  // namespace mvrmesh
