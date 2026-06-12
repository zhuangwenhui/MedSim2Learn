#pragma once

#include "mvrmesh/core/types.h"

namespace mvrmesh {

// Component-wise difference a - b.
Vec3 vsub(const Vec3& a, const Vec3& b);
// Component-wise sum a + b.
Vec3 vadd(const Vec3& a, const Vec3& b);
// a scaled by s.
Vec3 vmul(const Vec3& a, double s);
// Dot product of a and b.
double dot(const Vec3& a, const Vec3& b);
// Cross product a x b.
Vec3 cross(const Vec3& a, const Vec3& b);
// Euclidean length of a.
double norm(const Vec3& a);
// a scaled to unit length; returns the zero vector when |a| == 0.
Vec3 normalize(const Vec3& a);
// Unit normal of triangle (v1, v2, v3), right-hand rule on the winding order;
// zero vector for degenerate triangles.
Vec3 face_normal(const Vec3& v1, const Vec3& v2, const Vec3& v3);

// Canonical key for the undirected edge {i, j}: the smaller index comes first.
Edge make_edge_key(int i, int j);
// Area of triangle (a, b, c).
double triangle_area(const Vec3& a, const Vec3& b, const Vec3& c);
// Point on triangle (a, b, c) closest to p. Degenerate (near-zero-area)
// triangles fall back to the closest point on the three edges.
Vec3 closest_point_on_triangle(const Vec3& p, const Vec3& a, const Vec3& b, const Vec3& c);

}  // namespace mvrmesh

