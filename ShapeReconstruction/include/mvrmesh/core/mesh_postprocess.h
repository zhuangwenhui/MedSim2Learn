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

/// Transform vertices into a canonical "lying-flat" pose in-place:
/// translate the area-weighted centroid to the origin, align the thinnest
/// principal axis with +z and the longest with +x, and orient the sign so the
/// largest stable convex-hull support facet faces -z (the resting side).
void canonicalize_pose(std::vector<Vec3>& vertices, const std::vector<Face>& faces);

}  // namespace mvrmesh
