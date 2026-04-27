#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct CgalPmpOptions {
    double target_edge_length = 0.0;
    int remesh_iterations = 1;
};

struct CgalPmpResult {
    bool success = false;
    std::string diagnostic;
    std::size_t input_vertex_count = 0;
    std::size_t input_face_count = 0;
    std::size_t output_vertex_count = 0;
    std::size_t output_face_count = 0;
    std::vector<Vec3> output_vertices;
    std::vector<Face> output_faces;
};

CgalPmpResult run_cgal_pmp_backend(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const CgalPmpOptions& options
);

}  // namespace mvrmesh
