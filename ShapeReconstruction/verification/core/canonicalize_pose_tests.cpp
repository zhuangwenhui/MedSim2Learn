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

}  // namespace

int main() {
    return mvrmesh::test::run_tests({
        {test_centering_puts_centroid_at_origin, "test_centering_puts_centroid_at_origin"},
        {test_thin_axis_becomes_z,               "test_thin_axis_becomes_z"},
    });
}
