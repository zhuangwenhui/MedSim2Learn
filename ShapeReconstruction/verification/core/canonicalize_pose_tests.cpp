#include <array>
#include <cmath>
#include <vector>

#include "test_helpers.h"

#include "mvrmesh/core/mesh_postprocess.h"
#include "mvrmesh/core/types.h"

namespace {

using mvrmesh::Vec3;
using mvrmesh::Face;

void make_box(std::vector<Vec3>& v, std::vector<Face>& f,
              double hx, double hy, double hz) {
    v = {
        {-hx,-hy,-hz},{ hx,-hy,-hz},{ hx, hy,-hz},{-hx, hy,-hz},
        {-hx,-hy, hz},{ hx,-hy, hz},{ hx, hy, hz},{-hx, hy, hz},
    };
    f = {
        {0,1,2},{0,2,3}, {4,6,5},{4,7,6},
        {0,4,5},{0,5,1}, {1,5,6},{1,6,2},
        {2,6,7},{2,7,3}, {3,7,4},{3,4,0},
    };
}

double extent(const std::vector<Vec3>& v, int axis) {
    double lo = 1e300, hi = -1e300;
    for (const auto& p : v) {
        double c = (axis==0)?p.x:(axis==1)?p.y:p.z;
        lo = std::min(lo, c); hi = std::max(hi, c);
    }
    return hi - lo;
}

void test_centering_puts_centroid_at_origin() {
    std::vector<Vec3> v; std::vector<Face> f;
    make_box(v, f, 4.0, 0.5, 2.0);
    for (auto& p : v) { p.x += 100.0; p.y += 50.0; p.z += 10.0; }
    mvrmesh::canonicalize_pose(v, f);
    double cx=0, cy=0, cz=0;
    for (const auto& p : v) { cx+=p.x; cy+=p.y; cz+=p.z; }
    cx/=v.size(); cy/=v.size(); cz/=v.size();
    mvrmesh::test::require(mvrmesh::test::near(cx,0.0,1e-6) &&
                           mvrmesh::test::near(cy,0.0,1e-6) &&
                           mvrmesh::test::near(cz,0.0,1e-6),
                           "centroid should be at origin after pose");
}

void test_thin_axis_becomes_z() {
    std::vector<Vec3> v; std::vector<Face> f;
    make_box(v, f, 4.0, 0.5, 2.0);
    mvrmesh::canonicalize_pose(v, f);
    double ex = extent(v,0), ey = extent(v,1), ez = extent(v,2);
    mvrmesh::test::require(ez <= ex && ez <= ey,
                           "z extent should be the smallest after pose");
    mvrmesh::test::require(ex >= ey,
                           "x extent should be the largest after pose");
}

void test_resting_face_points_down() {
    // Trapezoidal slab: wide flat base at original y=-0.5, narrow top at y=+0.5.
    std::vector<Vec3> v = {
        {-4,-0.5,-3},{ 4,-0.5,-3},{ 4,-0.5, 3},{-4,-0.5, 3},   // wide base
        {-2, 0.5,-1},{ 2, 0.5,-1},{ 2, 0.5, 1},{-2, 0.5, 1},   // narrow top
    };
    std::vector<Face> f = {
        {0,2,1},{0,3,2}, {4,5,6},{4,6,7},
        {0,1,5},{0,5,4}, {1,2,6},{1,6,5},
        {2,3,7},{2,7,6}, {3,0,4},{3,4,7},
    };
    mvrmesh::canonicalize_pose(v, f);
    double zmin = 1e300; for (auto& p : v) zmin = std::min(zmin, p.z);
    int base_at_min = 0;
    for (int i = 0; i < 4; ++i) if (mvrmesh::test::near(v[i].z, zmin, 1e-3)) ++base_at_min;
    mvrmesh::test::require(base_at_min >= 3,
        "wide base should rest at min z (-z) after pose");
}

// Carried-forward from A2 code review (lock the right-handed/rigid invariant):
void test_pose_is_proper_rigid_transform() {
    std::vector<Vec3> v; std::vector<Face> f;
    // reuse make_box from this file
    make_box(v, f, 4.0, 0.5, 2.0);
    auto sgnvol = [](const Vec3& a, const Vec3& b, const Vec3& c, const Vec3& d) {
        Vec3 ab{b.x-a.x,b.y-a.y,b.z-a.z}, ac{c.x-a.x,c.y-a.y,c.z-a.z}, ad{d.x-a.x,d.y-a.y,d.z-a.z};
        double cx = ab.y*ac.z - ab.z*ac.y;
        double cy = ab.z*ac.x - ab.x*ac.z;
        double cz = ab.x*ac.y - ab.y*ac.x;
        return (cx*ad.x + cy*ad.y + cz*ad.z) / 6.0;  // signed tetra volume
    };
    double before = sgnvol(v[0], v[1], v[3], v[4]);
    mvrmesh::canonicalize_pose(v, f);
    double after = sgnvol(v[0], v[1], v[3], v[4]);
    // A proper rigid transform (rotation det +1 + translation) preserves signed volume exactly.
    mvrmesh::test::require(mvrmesh::test::near(before, after, 1e-6),
        "signed volume must be preserved (proper rigid transform, right-handed)");
}

void test_pose_flips_inverted_base() {
    // Inverted trapezoid: WIDE base at y=+0.5, NARROW top at y=-0.5.
    // For this axis-symmetric shape raw PCA yields thin-axis (0,+1,0), which would
    // place the wide base at +z WITHOUT the hull sign correction. The hull correction
    // must flip it so the wide (resting) base lands at -z. This test fails if the
    // hull sign-correction block is absent -> it discriminates the A3 feature.
    std::vector<Vec3> v = {
        {-4, 0.5,-3},{ 4, 0.5,-3},{ 4, 0.5, 3},{-4, 0.5, 3},   // wide base at +y
        {-2,-0.5,-1},{ 2,-0.5,-1},{ 2,-0.5, 1},{-2,-0.5, 1},   // narrow top at -y
    };
    std::vector<Face> f = {
        {0,2,1},{0,3,2}, {4,5,6},{4,6,7},
        {0,1,5},{0,5,4}, {1,2,6},{1,6,5},
        {2,3,7},{2,7,6}, {3,0,4},{3,4,7},
    };
    mvrmesh::canonicalize_pose(v, f);
    double zmin = 1e300; for (auto& p : v) zmin = std::min(zmin, p.z);
    int base_at_min = 0;
    for (int i = 0; i < 4; ++i) if (mvrmesh::test::near(v[i].z, zmin, 1e-3)) ++base_at_min;
    mvrmesh::test::require(base_at_min >= 3,
        "inverted wide base must be flipped to min z (-z) by hull sign correction");
}

void test_pose_flip_inverts_resting_face() {
    // Wide base at y=-0.5, narrow top at y=+0.5 (same as test_resting_face_points_down).
    std::vector<Vec3> v = {
        {-4,-0.5,-3},{ 4,-0.5,-3},{ 4,-0.5, 3},{-4,-0.5, 3},
        {-2, 0.5,-1},{ 2, 0.5,-1},{ 2, 0.5, 1},{-2, 0.5, 1},
    };
    std::vector<Face> f = {
        {0,2,1},{0,3,2}, {4,5,6},{4,6,7},
        {0,1,5},{0,5,4}, {1,2,6},{1,6,5},
        {2,3,7},{2,7,6}, {3,0,4},{3,4,7},
    };
    mvrmesh::canonicalize_pose(v, f, /*flip=*/true);
    // Without flip the wide base rests at MIN z; with flip it must be at MAX z.
    double zmax = -1e300; for (auto& p : v) zmax = std::max(zmax, p.z);
    int base_at_max = 0;
    for (int i = 0; i < 4; ++i) if (mvrmesh::test::near(v[i].z, zmax, 1e-3)) ++base_at_max;
    mvrmesh::test::require(base_at_max >= 3,
        "flip should put the wide resting base at MAX z (+z)");
}

}  // namespace

int main() {
    return mvrmesh::test::run_tests({
        {test_centering_puts_centroid_at_origin, "test_centering_puts_centroid_at_origin"},
        {test_thin_axis_becomes_z,               "test_thin_axis_becomes_z"},
        {test_resting_face_points_down,          "test_resting_face_points_down"},
        {test_pose_is_proper_rigid_transform,    "test_pose_is_proper_rigid_transform"},
        {test_pose_flips_inverted_base,          "test_pose_flips_inverted_base"},
        {test_pose_flip_inverts_resting_face,    "test_pose_flip_inverts_resting_face"},
    });
}
