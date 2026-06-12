#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Apply vertex perturbation and degenerate triangle removal, in place, on
// normalized-space coordinates: jitters every vertex by a tiny fraction of the
// shortest edge, then drops near-zero-area and duplicate triangles. Returns the
// number of degenerate triangles removed (duplicate removals are not counted).
int mesh_quality_fix(std::vector<Vec3>& vertices, std::vector<Face>& faces);

// Restore vertices from normalized coordinate space to physical mm units by
// mapping the current vertex bounding box onto the MVR header bounding box
// (voxel units) and scaling by the voxel spacing.
// Skips silently if bounding_box.valid is false.
void restore_physical_coordinates(
    std::vector<Vec3>& vertices,
    const BoundingBox& bounding_box,
    double voxel_spacing_mm);

// Transform vertices into a canonical "lying-flat" pose in-place:
// translate the area-weighted centroid to the origin, align the thinnest
// principal axis with +z and the longest with +x, and orient the sign so the
// largest stable convex-hull support facet faces -z (the resting side).
// When `flip` is true, the object instead rests on the opposite broad face
// (the pose is rotated 180 deg about an in-plane axis), keeping a proper rigid
// transform (det +1).
void canonicalize_pose(std::vector<Vec3>& vertices, const std::vector<Face>& faces, bool flip = false);

}  // namespace mvrmesh
