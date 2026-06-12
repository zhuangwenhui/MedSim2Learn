#pragma once

#include <filesystem>
#include <string>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Tuning for SurfaceMode::AdaptiveRemesh. Each iteration scores faces by
// vertex curvature and splits the edges of the highest-scoring fraction
// (split_ratio, in (0, 1]) of faces. iterations must be >= 1.
struct AdaptiveRemeshConfig {
    int iterations = 1;
    double split_ratio = 0.5;
};

// Tuning for SurfaceMode::UniformSubdivide; also the subdivision step of
// SurfaceMode::UniformTaubin. iterations must be >= 1.
struct UniformSubdivideConfig {
    int iterations = 1;
};

// Taubin lambda|mu smoothing parameters (SurfaceMode::UniformTaubin).
// lambda is the positive shrink step, mu the negative inflate step that
// counters shrinkage; preserve_boundary keeps boundary vertices fixed.
// iterations >= 0 (0 disables smoothing).
struct TaubinConfig {
    int iterations = 8;
    double lambda = 0.5;
    double mu = -0.53;
    bool preserve_boundary = true;
};

// Tuning for SurfaceMode::SdfReconstruct: sample the surface into a signed
// distance grid of 'resolution' cells per axis (valid range
// [2, kMaxSdfGridResolution]), padded by padding_ratio of the bounding-box
// extent, then re-extract and remesh the isosurface. Edge lengths are in the
// pipeline's normalized mesh space, not millimetres; the near-180 sharp-edge
// default effectively disables sharp-edge protection.
struct SdfReconstructConfig {
    int resolution = 72;
    double padding_ratio = 0.05;
    double sharp_edge_dihedral_degrees = 179.0;
    double target_edge_length = 0.025;
    int remesh_iterations = 3;
};

// Tuning for the optional CGAL repair + isotropic-remesh post-step
// (PipelineConfig::cgal_mesh_post). Edges whose dihedral angle exceeds
// sharp_edge_dihedral_degrees are protected during remeshing.
// target_edge_length 0 = auto from the input's mean edge length; lengths are
// in normalized mesh space, not millimetres.
struct CgalMeshConfig {
    double sharp_edge_dihedral_degrees = 60.0;
    double target_edge_length = 0.0;
    int remesh_iterations = 3;
};

// Effective settings for one mvr_to_mesh_cli run, merged from struct
// defaults, an optional YAML file, and CLI flags (see load_config). The
// pipeline operates in the MVR's normalized coordinate space;
// restore_physical_coords scales the result back to physical millimetres
// using voxel_spacing_mm (mm per voxel).
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
    bool pose_flip = false;

    // Throws std::runtime_error if any setting is out of range or the mode
    // combination is inconsistent (e.g. cgal_mesh_post together with a
    // non-DirectSurface mode).
    void validate() const;
};

// Maps a snake_case mode name (e.g. "direct_surface") to SurfaceMode.
// Throws std::runtime_error on an unknown name.
SurfaceMode parse_surface_mode(const std::string& name);

// Inverse of parse_surface_mode. Throws std::runtime_error if the enum value
// is out of range.
std::string surface_mode_name(SurfaceMode mode);

}  // namespace mvrmesh
