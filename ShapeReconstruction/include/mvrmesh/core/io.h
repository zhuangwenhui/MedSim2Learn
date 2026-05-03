#pragma once

#include <filesystem>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

ParsedMvr parse_mvr(const std::filesystem::path& path);

void write_ply(
    const std::filesystem::path& path,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

void read_ply(
    const std::filesystem::path& path,
    std::vector<Vec3>& out_vertices,
    std::vector<Face>& out_faces
);

}  // namespace mvrmesh

