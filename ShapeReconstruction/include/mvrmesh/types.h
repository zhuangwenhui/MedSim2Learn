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

enum class OutputFormat {
    Ply,
    Stl,
    Both
};

enum class SurfaceMode {
    DirectSurface,
    AdaptiveRemesh
};

struct BuildOptions {
    bool adaptive_remesh = false;
    int adaptive_iterations = 1;
    double adaptive_split_ratio = 0.5;
};

struct BuildResult {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    SurfaceMode mode = SurfaceMode::DirectSurface;
};

}  // namespace mvrmesh
