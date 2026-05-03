#pragma once

#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

BuildResult build_surface(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& triangles,
    const std::vector<Tet>& tets,
    const BuildOptions& options
);

std::vector<std::filesystem::path> outputs_for_mode(
    const std::filesystem::path& base_output
);

std::string surface_mode_to_string(SurfaceMode mode);

}  // namespace mvrmesh

