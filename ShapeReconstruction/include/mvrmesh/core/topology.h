#pragma once

#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

std::vector<Face> normalize_faces_indices(const std::vector<Face>& faces, int n_vertices);
std::vector<Tet> normalize_tet_indices(const std::vector<Tet>& tets, int n_vertices);

Face oriented_face_outward(const std::vector<Vec3>& vertices, const Face& face, int opposite);
std::vector<Face> boundary_faces_from_tets(const std::vector<Vec3>& vertices, const std::vector<Tet>& tets);
Face orient_like_face(const std::vector<Vec3>& vertices, const Face& base_face, const Face& tri);

}  // namespace mvrmesh

