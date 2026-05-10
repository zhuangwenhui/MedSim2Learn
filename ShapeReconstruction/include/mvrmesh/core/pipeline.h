#pragma once

#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

BuildResult build_surface(
    const ParsedMvr& parsed,
    const PipelineConfig& config
);

std::vector<std::filesystem::path> outputs_for_mode(
    const std::filesystem::path& base_output
);

}  // namespace mvrmesh
