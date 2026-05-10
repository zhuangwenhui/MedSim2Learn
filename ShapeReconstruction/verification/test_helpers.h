#pragma once

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <functional>

#include "mvrmesh/core/types.h"

namespace mvrmesh::test {

inline void require(bool cond, const std::string& msg) {
    if (!cond) throw std::runtime_error(msg);
}

inline bool near(double a, double b, double tol = 1e-9) {
    return std::abs(a - b) < tol;
}

inline void require_vec3_near(const Vec3& actual, const Vec3& expected,
                               const std::string& label, double tol = 1e-9) {
    require(near(actual.x, expected.x, tol), label + " x mismatch");
    require(near(actual.y, expected.y, tol), label + " y mismatch");
    require(near(actual.z, expected.z, tol), label + " z mismatch");
}

inline int run_tests(std::initializer_list<std::pair<std::function<void()>, const char*>> tests) {
    int passed = 0, failed = 0;
    for (const auto& [fn, name] : tests) {
        try {
            fn();
            ++passed;
        } catch (const std::exception& ex) {
            std::cerr << "FAIL: " << name << " -- " << ex.what() << "\n";
            ++failed;
        }
    }
    std::cout << passed << " passed, " << failed << " failed\n";
    return failed > 0 ? 1 : 0;
}

}  // namespace mvrmesh::test
