#include "mvrmesh/core/geometry.h"

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

}  // namespace mvrmesh

