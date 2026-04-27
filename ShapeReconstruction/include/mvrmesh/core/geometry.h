#pragma once

#include "mvrmesh/core/types.h"

namespace mvrmesh {

Vec3 vsub(const Vec3& a, const Vec3& b);
Vec3 vadd(const Vec3& a, const Vec3& b);
Vec3 vmul(const Vec3& a, double s);
double dot(const Vec3& a, const Vec3& b);
Vec3 cross(const Vec3& a, const Vec3& b);
double norm(const Vec3& a);
Vec3 normalize(const Vec3& a);
Vec3 face_normal(const Vec3& v1, const Vec3& v2, const Vec3& v3);

}  // namespace mvrmesh

