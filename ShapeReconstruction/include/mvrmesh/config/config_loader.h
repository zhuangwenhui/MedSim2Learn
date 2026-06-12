#pragma once

#include <filesystem>

#include "mvrmesh/config/pipeline_config.h"

namespace mvrmesh {

// Parses a YAML file into a PipelineConfig. Missing keys keep their struct
// defaults; unknown keys emit a [warn] on stderr. Does not call validate().
// Throws on an unreadable file or a value of the wrong type (yaml-cpp
// exceptions derive from std::runtime_error).
PipelineConfig load_config_from_yaml(const std::filesystem::path& yaml_path);

// Builds the effective config from three layers: struct defaults, then an
// optional YAML file (--config), then CLI flags (later layers win). Validates
// the merged result. Throws std::runtime_error carrying the usage text on bad
// or missing arguments, including -h/--help.
PipelineConfig load_config(int argc, char** argv);

}  // namespace mvrmesh
