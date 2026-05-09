#pragma once

#include <array>
#include <string>
#include <utility>
#include <vector>

namespace mvrmesh {

struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

using Face = std::array<int, 3>;
using Tet = std::array<int, 4>;
using Edge = std::pair<int, int>;

struct ParsedMvr {
    std::vector<Vec3> vertices;
    std::vector<Face> triangles;
    std::vector<Tet> tetrahedra;
};

enum class SurfaceMode {
    DirectSurface,
    AdaptiveRemesh,
    UniformSubdivide,
    UniformTaubin,
    SdfReconstruct
};

struct BuildOptions {
    bool adaptive_remesh = false;
    int adaptive_iterations = 1;
    double adaptive_split_ratio = 0.5;
    bool uniform_subdivide = false;
    int uniform_iterations = 1;
    bool taubin_smooth = false;
    int taubin_iterations = 8;
    double taubin_lambda = 0.5;
    double taubin_mu = -0.53;
    bool taubin_preserve_boundary = true;
    bool sdf_reconstruct = false;
    int sdf_resolution = 72;
    double sdf_padding_ratio = 0.05;
    double sdf_sharp_edge_degrees = 179.0;
    double sdf_target_edge_length = 0.025;
    int sdf_remesh_iterations = 3;
};

struct BuildResult {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    SurfaceMode mode = SurfaceMode::DirectSurface;
};

}  // namespace mvrmesh
