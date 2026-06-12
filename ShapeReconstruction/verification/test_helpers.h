#pragma once

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <functional>

#include "mvrmesh/core/types.h"

namespace mvrmesh::test {

// Basic test assertion: throws std::runtime_error(msg) when cond is false.
inline void require(bool cond, const std::string& msg) {
    if (!cond) throw std::runtime_error(msg);
}

// Absolute-difference comparison: true when |a - b| < tol.
inline bool near(double a, double b, double tol = 1e-9) {
    return std::abs(a - b) < tol;
}

// Compares two Vec3 component-wise with near(); on mismatch throws naming the label and axis.
inline void require_vec3_near(const Vec3& actual, const Vec3& expected,
                               const std::string& label, double tol = 1e-9) {
    require(near(actual.x, expected.x, tol), label + " x mismatch");
    require(near(actual.y, expected.y, tol), label + " y mismatch");
    require(near(actual.z, expected.z, tol), label + " z mismatch");
}

// Runs each (test, name) pair, prints a pass/fail summary, and returns 1 if any test failed.
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
