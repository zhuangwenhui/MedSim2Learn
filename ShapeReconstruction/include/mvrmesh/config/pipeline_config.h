// include/mvrmesh/config/pipeline_config.h
#pragma once

#include <filesystem>
#include <string>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct AdaptiveRemeshConfig {
    int iterations = 1;
    double split_ratio = 0.5;
};

struct UniformSubdivideConfig {
    int iterations = 1;
};

struct TaubinConfig {
    int iterations = 8;
    double lambda = 0.5;
    double mu = -0.53;
    bool preserve_boundary = true;
};

struct SdfReconstructConfig {
    int resolution = 72;
    double padding_ratio = 0.05;
    double sharp_edge_dihedral_degrees = 179.0;
    double target_edge_length = 0.025;
    int remesh_iterations = 3;
};

struct CgalMeshConfig {
    double sharp_edge_dihedral_degrees = 60.0;
    double target_edge_length = 0.0;
    int remesh_iterations = 3;
};

struct PipelineConfig {
    std::filesystem::path input;
    std::filesystem::path output;

    SurfaceMode mode = SurfaceMode::DirectSurface;
    bool cgal_mesh_post = false;

    AdaptiveRemeshConfig adaptive_remesh;
    UniformSubdivideConfig uniform_subdivide;
    TaubinConfig taubin;
    SdfReconstructConfig sdf_reconstruct;
    CgalMeshConfig cgal_mesh;

    double voxel_spacing_mm = 1.0;
    bool restore_physical_coords = true;
    bool mesh_quality_fix = true;
    bool canonicalize_pose = false;

    void validate() const;
};

SurfaceMode parse_surface_mode(const std::string& name);
std::string surface_mode_name(SurfaceMode mode);

}  // namespace mvrmesh
