#pragma once

#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Builds the output surface for the configured SurfaceMode: starts from the
// parsed @3 triangles, or from the boundary faces of the @4 tetrahedra when
// no triangles exist, then applies the mode's remesh/subdivide/smooth stage.
// Throws std::runtime_error when the input has neither triangles nor
// tetrahedra.
BuildResult build_surface(
    const ParsedMvr& parsed,
    const PipelineConfig& config
);

// Returns the file paths the pipeline will write for the given base output
// path: currently a single path with its extension replaced by ".ply".
std::vector<std::filesystem::path> outputs_for_mode(
    const std::filesystem::path& base_output
);

}  // namespace mvrmesh
