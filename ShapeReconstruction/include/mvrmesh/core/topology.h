#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Converts face indices to 0-based. Faces are returned unchanged when every
// index is already in [0, n_vertices); when they all fit [1, n_vertices] the
// input is treated as 1-based and shifted down; anything else throws
// std::runtime_error.
std::vector<Face> normalize_faces_indices(const std::vector<Face>& faces, int n_vertices);

// Same 0-based/1-based normalization as normalize_faces_indices(), for tetrahedra.
std::vector<Tet> normalize_tet_indices(const std::vector<Tet>& tets, int n_vertices);

// Throws std::runtime_error (prefixed with `context`) if any face references a
// vertex index outside [0, vertices.size()).
void validate_face_indices(const std::vector<Vec3>& vertices,
                           const std::vector<Face>& faces,
                           const char* context);

// Axis-aligned bounding box over all vertices. `valid` is false when the
// vertex list is empty (min/max are then default-initialized).
MeshBoundingBox compute_bbox(const std::vector<Vec3>& vertices);

// Returns `face` wound so its normal points away from `opposite` (the tet
// vertex not on the face).
Face oriented_face_outward(const std::vector<Vec3>& vertices, const Face& face, int opposite);

// Extracts the boundary surface of a tet mesh: the faces referenced by exactly
// one tetrahedron, each wound to point out of its tet.
std::vector<Face> boundary_faces_from_tets(const std::vector<Vec3>& vertices, const std::vector<Tet>& tets);

// Returns `tri` rewound, if needed, so its normal has a positive dot product
// with the normal of `base_face`.
Face orient_like_face(const std::vector<Vec3>& vertices, const Face& base_face, const Face& tri);

}  // namespace mvrmesh

