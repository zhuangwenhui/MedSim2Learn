#pragma once

#include <filesystem>
#include <vector>

#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Locates the project root (the directory containing both originalData/ and
// CMakeLists.txt) by walking upward from the current directory, then from the
// executable path argv0. Returns an empty path when neither walk finds one.
std::filesystem::path find_project_root(const char* argv0);

// Resolves config.input to an existing file, trying it as given, relative to
// the current directory, the project root, and <root>/originalData. Throws
// std::runtime_error when no candidate exists.
std::filesystem::path resolve_input(
    const PipelineConfig& config, const char* argv0);

// Output paths for the run: config.output (made absolute and expanded via
// outputs_for_mode) when set, otherwise <root>/outPut/PLY/<input_stem>.ply.
std::vector<std::filesystem::path> resolve_outputs(
    const PipelineConfig& config,
    const std::filesystem::path& resolved_input,
    const char* argv0);

// Recursively creates the parent directory of path if it does not exist.
void ensure_parent_dir(const std::filesystem::path& path);

// Writes the result mesh as PLY to every path in out_paths, creating parent
// directories as needed. Throws std::runtime_error for output extensions
// other than .ply/.PLY.
void write_outputs(
    const BuildResult& result,
    const std::vector<std::filesystem::path>& out_paths);

// Prints an [info] summary of the parsed MVR (vertex/triangle/tet counts).
void log_source_info(const ParsedMvr& parsed);

// Prints an [info] summary of the built surface (mode, vertex/face counts).
void log_build_result(const BuildResult& result);

}  // namespace mvrmesh
