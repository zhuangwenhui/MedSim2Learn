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

struct BoundingBox {
    double x_min = 0.0, x_max = 0.0;
    double y_min = 0.0, y_max = 0.0;
    double z_min = 0.0, z_max = 0.0;
    bool valid = false;
};

struct ParsedMvr {
    std::vector<Vec3> vertices;
    std::vector<Face> triangles;
    std::vector<Tet> tetrahedra;
    BoundingBox bounding_box;
};

enum class SurfaceMode {
    DirectSurface,
    AdaptiveRemesh,
    UniformSubdivide,
    UniformTaubin,
    SdfReconstruct
};

struct BuildResult {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    SurfaceMode mode = SurfaceMode::DirectSurface;
};

}  // namespace mvrmesh
