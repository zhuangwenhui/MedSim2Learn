// include/mvrmesh/cli/cli_common.h
#pragma once

#include <filesystem>
#include <vector>

#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

std::filesystem::path find_project_root(const char* argv0);

std::filesystem::path resolve_input(
    const PipelineConfig& config, const char* argv0);

std::vector<std::filesystem::path> resolve_outputs(
    const PipelineConfig& config,
    const std::filesystem::path& resolved_input,
    const char* argv0);

void ensure_parent_dir(const std::filesystem::path& path);

void write_outputs(
    const BuildResult& result,
    const std::vector<std::filesystem::path>& out_paths);

void log_source_info(const ParsedMvr& parsed);
void log_build_result(const BuildResult& result);

}  // namespace mvrmesh
