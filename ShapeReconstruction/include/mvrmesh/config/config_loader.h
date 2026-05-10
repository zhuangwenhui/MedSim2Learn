// include/mvrmesh/config/config_loader.h
#pragma once

#include <filesystem>

#include "mvrmesh/config/pipeline_config.h"

namespace mvrmesh {

PipelineConfig load_config_from_yaml(const std::filesystem::path& yaml_path);
PipelineConfig load_config(int argc, char** argv);

}  // namespace mvrmesh
