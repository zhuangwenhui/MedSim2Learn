#pragma once

#include <filesystem>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Parses an .mvr file: header counts and bounding box, then the @1 vertex,
// @3 triangle, and @4 tetrahedron sections. Throws std::runtime_error if the
// file cannot be opened, a numeric token is malformed, or section @1 yields
// no vertices.
ParsedMvr parse_mvr(const std::filesystem::path& path);

// Writes vertices and triangle faces as ASCII PLY (format ascii 1.0).
void write_ply(
    const std::filesystem::path& path,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

// Reads an ASCII triangle PLY into vertices_out/faces_out (both cleared
// first). Throws std::runtime_error on a non-ascii format, truncated data,
// or a face that is not a triangle.
void read_ply(
    const std::filesystem::path& path,
    std::vector<Vec3>& vertices_out,
    std::vector<Face>& faces_out
);

}  // namespace mvrmesh

