#include <cmath>
#include <exception>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/algorithms.h"
#include "mvrmesh/topology.h"
#include "mvrmesh/types.h"

namespace {

void require(bool cond, const std::string& message) {
    if (!cond) {
        throw std::runtime_error(message);
    }
}

void test_normalize_faces_indices() {
    using mvrmesh::Face;

    const std::vector<Face> one_based{Face{1, 2, 3}, Face{3, 4, 5}};
    const std::vector<Face> normalized = mvrmesh::normalize_faces_indices(one_based, 5);
    require(normalized[0] == Face{0, 1, 2}, "1-based faces should normalize to 0-based");
    require(normalized[1] == Face{2, 3, 4}, "1-based faces should normalize to 0-based");

    const std::vector<Face> zero_based{Face{0, 1, 2}, Face{2, 3, 4}};
    const std::vector<Face> kept = mvrmesh::normalize_faces_indices(zero_based, 5);
    require(kept == zero_based, "0-based faces should remain unchanged");
}

void test_boundary_faces_single_tet() {
    using mvrmesh::Tet;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Tet> tets{Tet{0, 1, 2, 3}};
    const std::vector<mvrmesh::Face> faces = mvrmesh::boundary_faces_from_tets(vertices, tets);
    require(faces.size() == 4, "Single tetrahedron should produce 4 boundary faces");
}

void test_subdivide_tetrahedra_count() {
    using mvrmesh::Tet;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
        Vec3{0.0, 0.0, 1.0},
    };
    const std::vector<Tet> tets{Tet{0, 1, 2, 3}};
    const auto subdivided = mvrmesh::subdivide_tetrahedra(vertices, tets);
    require(subdivided.second.size() == 8, "Each tetrahedron must subdivide into 8 tetrahedra");
    require(subdivided.first.size() == 10, "Single tetrahedron subdivision should create 6 edge midpoints");
}

void test_adaptive_single_triangle_split() {
    using mvrmesh::Face;
    using mvrmesh::Vec3;

    const std::vector<Vec3> vertices{
        Vec3{0.0, 0.0, 0.0},
        Vec3{1.0, 0.0, 0.0},
        Vec3{0.0, 1.0, 0.0},
    };
    const std::vector<Face> faces{Face{0, 1, 2}};

    const auto remeshed = mvrmesh::adaptive_remesh(vertices, faces, 1, 1.0);
    require(remeshed.first.size() == 6, "One fully split triangle should add 3 midpoint vertices");
    require(remeshed.second.size() == 4, "One fully split triangle should create 4 faces");
}

void test_python_round_behavior_for_face_selection() {
    using mvrmesh::Face;

    const std::vector<Face> faces{
        Face{0, 1, 2},
        Face{3, 4, 5},
        Face{6, 7, 8},
        Face{9, 10, 11},
        Face{12, 13, 14},
    };
    const std::vector<double> curvature(15, 1.0);
    const std::set<mvrmesh::Edge> edges = mvrmesh::select_split_edges_by_curvature(faces, curvature, 0.5);

    // Python round(5 * 0.5) = round(2.5) = 2 (ties-to-even), so we expect 2 faces selected.
    require(edges.size() == 6, "Split edge count should reflect Python-style tie-to-even rounding");
}

}  // namespace

int main() {
    try {
        test_normalize_faces_indices();
        test_boundary_faces_single_tet();
        test_subdivide_tetrahedra_count();
        test_adaptive_single_triangle_split();
        test_python_round_behavior_for_face_selection();
    } catch (const std::exception& ex) {
        std::cerr << "[fail] " << ex.what() << "\n";
        return 1;
    }

    std::cout << "[ok] smoke tests passed\n";
    return 0;
}

