#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Options for the SDF reconstruction + CGAL remesh stage. Lengths are in the
// same units as the vertex coordinates.
struct SdfRemeshOptions {
    // Cells per axis of the SDF sampling grid; valid range [2, kMaxSdfGridResolution].
    int sdf_resolution = 72;
    // Margin added around the input bounding box on every side, as a fraction
    // of its largest span; must be finite and >= 0.
    double padding_ratio = 0.05;
    // Dihedral-angle bound in degrees for CGAL sharp-edge detection; detected
    // edges are pinned during remeshing. Must lie in (0, 180); a higher bound
    // flags fewer edges.
    double sharp_edge_dihedral_degrees = 179.0;
    // Target edge length for isotropic remeshing (0 = auto from mean edge
    // length, see run_cgal_mesh); must be finite and >= 0.
    double target_edge_length = 0.025;
    // Number of isotropic remeshing passes; must be >= 1.
    int remesh_iterations = 3;
};

// Surface produced by reconstruct_and_remesh_surface.
struct SdfRemeshResult {
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
};

// Rebuilds a clean surface from a possibly dirty boundary mesh: compacts the
// input to its referenced vertices, extracts the SDF iso-surface, runs CGAL
// repair plus sharp-edge-protected isotropic remeshing, then compacts again.
// Throws std::invalid_argument when an option is out of range and
// std::runtime_error when the input or remeshed mesh ends up empty.
SdfRemeshResult reconstruct_and_remesh_surface(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfRemeshOptions& options);

}  // namespace mvrmesh
