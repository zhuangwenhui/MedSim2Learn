#pragma once

#include <array>
#include <string>
#include <utility>
#include <vector>

namespace mvrmesh {

// Conventions that hold throughout this library (stated once here, not
// repeated per function):
// - Face/tet/edge entries are 0-based vertex indices; the parser auto-detects
//   1-based .mvr files and converts them (see normalize_faces_indices()).
// - Vertex coordinates stay in the source .mvr's own coordinate space until
//   restore_physical_coordinates() maps them to millimetres; the shipped PLY
//   meshes that DeformSim consumes are millimetre-scaled.
// - Mesh and index validation failures throw std::runtime_error with context
//   (file, section, offending value). A few entry points deviate and say so
//   at their declaration (std::invalid_argument, std::out_of_range).

// 3-component double vector, used both for points and for directions/normals.
struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

// Triangle as three vertex indices.
using Face = std::array<int, 3>;
// Tetrahedron as four vertex indices.
using Tet = std::array<int, 4>;
// Undirected edge key: smaller vertex index first (see make_edge_key()).
using Edge = std::pair<int, int>;

// Axis-aligned bounds stored as six per-axis scalars mirroring the MVR header
// layout. `valid` stays false until the parser fills the fields.
struct BoundingBox {
    double x_min = 0.0, x_max = 0.0;
    double y_min = 0.0, y_max = 0.0;
    double z_min = 0.0, z_max = 0.0;
    bool valid = false;
};

// Axis-aligned bounding box over mesh vertices (Vec3 corners). Distinct from
// BoundingBox above, which mirrors the scalar-field layout of the MVR header.
struct MeshBoundingBox {
    bool valid = false;
    Vec3 min;
    Vec3 max;
};

// In-memory contents of a parsed .mvr file: vertices, surface triangles
// (@3 section), tetrahedra (@4 section), and the bounding box from the header.
struct ParsedMvr {
    std::vector<Vec3> vertices;
    std::vector<Face> triangles;
    std::vector<Tet> tetrahedra;
    BoundingBox bounding_box;
};

// Strategy applied to the base surface (input triangles, or boundary faces
// extracted from the tet mesh) when building the output mesh.
enum class SurfaceMode {
    DirectSurface,  // keep the base surface unchanged
    AdaptiveRemesh,  // adaptive isotropic remeshing
    UniformSubdivide,  // uniform triangle subdivision
    UniformTaubin,  // uniform subdivision followed by Taubin smoothing
    SdfReconstruct  // SDF-based surface reconstruction, then remesh
};

// Output of build_surface(): the final surface mesh and the mode that
// produced it.
struct BuildResult {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    SurfaceMode mode = SurfaceMode::DirectSurface;
};

}  // namespace mvrmesh
