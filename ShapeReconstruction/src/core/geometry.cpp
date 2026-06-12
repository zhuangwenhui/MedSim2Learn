#include "mvrmesh/core/geometry.h"

#include <algorithm>
#include <cmath>

namespace mvrmesh {

Vec3 vsub(const Vec3& a, const Vec3& b) {
    return Vec3{a.x - b.x, a.y - b.y, a.z - b.z};
}

Vec3 vadd(const Vec3& a, const Vec3& b) {
    return Vec3{a.x + b.x, a.y + b.y, a.z + b.z};
}

Vec3 vmul(const Vec3& a, double s) {
    return Vec3{a.x * s, a.y * s, a.z * s};
}

double dot(const Vec3& a, const Vec3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Vec3 cross(const Vec3& a, const Vec3& b) {
    return Vec3{
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

double norm(const Vec3& a) {
    return std::sqrt(dot(a, a));
}

Vec3 normalize(const Vec3& a) {
    const double n = norm(a);
    if (n == 0.0) {
        return Vec3{0.0, 0.0, 0.0};
    }
    return Vec3{a.x / n, a.y / n, a.z / n};
}

Vec3 face_normal(const Vec3& v1, const Vec3& v2, const Vec3& v3) {
    return normalize(cross(vsub(v2, v1), vsub(v3, v1)));
}

Edge make_edge_key(int i, int j) {
    if (i < j) {
        return Edge{i, j};
    }
    return Edge{j, i};
}

double triangle_area(const Vec3& a, const Vec3& b, const Vec3& c) {
    return 0.5 * norm(cross(vsub(b, a), vsub(c, a)));
}

namespace {

// Degeneracy guard for squared lengths and squared areas.
constexpr double kEpsilon = 1e-12;

double clamp01(double v) {
    return std::clamp(v, 0.0, 1.0);
}

// Clamped projection parameter num/den; a near-zero denominator (degenerate
// segment) maps to the start point (t = 0).
double segment_param(double num, double den) {
    if (std::abs(den) <= kEpsilon) return 0.0;
    return clamp01(num / den);
}

Vec3 closest_on_segment(const Vec3& p, const Vec3& a, const Vec3& b) {
    const Vec3 ab = vsub(b, a);
    const double t = segment_param(dot(vsub(p, a), ab), dot(ab, ab));
    return vadd(a, vmul(ab, t));
}

}  // namespace

// Closest point on triangle using Voronoi region test (the classic case
// analysis from Ericson, Real-Time Collision Detection: classify P against the
// three vertex regions, three edge regions, then the interior).
// Returns the point on triangle ABC nearest to P.
Vec3 closest_point_on_triangle(const Vec3& p, const Vec3& a, const Vec3& b, const Vec3& c) {
    const Vec3 ab = vsub(b, a);
    const Vec3 ac = vsub(c, a);
    const Vec3 ap = vsub(p, a);
    const Vec3 bp = vsub(p, b);
    const Vec3 cp = vsub(p, c);

    const double area_cross_sq = dot(cross(ab, ac), cross(ab, ac));
    // Degenerate triangle: fall back to closest point on edges.
    if (area_cross_sq <= kEpsilon * kEpsilon) {
        const auto d2 = [&](const Vec3& q) { return dot(vsub(q, p), vsub(q, p)); };
        const Vec3 c_ab = closest_on_segment(p, a, b);
        const Vec3 c_ac = closest_on_segment(p, a, c);
        const Vec3 c_bc = closest_on_segment(p, b, c);
        const double d_ab = d2(c_ab), d_ac = d2(c_ac), d_bc = d2(c_bc);
        if (d_ab <= d_ac && d_ab <= d_bc) return c_ab;
        if (d_ac <= d_bc) return c_ac;
        return c_bc;
    }

    const double d1 = dot(ab, ap), d2 = dot(ac, ap);
    // Vertex A region
    if (d1 <= 0.0 && d2 <= 0.0) return a;

    const double d3 = dot(ab, bp), d4 = dot(ac, bp);
    // Vertex B region
    if (d3 >= 0.0 && d4 <= d3) return b;

    const double d5 = dot(ab, cp), d6 = dot(ac, cp);
    // Vertex C region
    if (d6 >= 0.0 && d5 <= d6) return c;

    // Edge AB region
    const double vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0) {
        return vadd(a, vmul(ab, segment_param(d1, d1 - d3)));
    }

    // Edge AC region
    const double vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0) {
        return vadd(a, vmul(ac, segment_param(d2, d2 - d6)));
    }

    // Edge BC region
    const double va = d3 * d6 - d5 * d4;
    if (va <= 0.0 && (d4 - d2) >= 0.0 && (d5 - d3) >= 0.0) {
        return vadd(b, vmul(vsub(c, b), segment_param(d4 - d2, (d4 - d2) + (d5 - d3))));
    }

    // Interior region: barycentric projection
    const double inv = 1.0 / (va + vb + vc);
    return vadd(a, vadd(vmul(ab, vb * inv), vmul(ac, vc * inv)));
}

}  // namespace mvrmesh

