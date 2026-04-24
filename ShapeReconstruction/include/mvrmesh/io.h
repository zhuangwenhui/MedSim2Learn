#pragma once

#include <filesystem>
#include <vector>

#include "mvrmesh/types.h"

namespace mvrmesh {

ParsedMvr parse_mvr(const std::filesystem::path& path);

void write_ply(
    const std::filesystem::path& path,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

void write_stl(
    const std::filesystem::path& path,
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
);

}  // namespace mvrmesh

