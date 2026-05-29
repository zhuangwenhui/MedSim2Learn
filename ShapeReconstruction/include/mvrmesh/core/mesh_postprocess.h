#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

/// Apply vertex perturbation and degenerate triangle removal.
/// Operates in-place on normalized-space coordinates.
/// Returns the number of degenerate triangles fixed.
int mesh_quality_fix(std::vector<Vec3>& vertices, std::vector<Face>& faces);

/// Restore vertices from normalized coordinate space to physical mm units.
/// Skips silently if bounding_box.valid is false.
void restore_physical_coordinates(
    std::vector<Vec3>& vertices,
    const BoundingBox& bounding_box,
    double voxel_spacing_mm);

}  // namespace mvrmesh
