#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/core/metrics.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct GmshEvaluationOptions {
    int algorithm3d = 10;
};

struct GmshEvaluationResult {
    bool success = false;
    int algorithm3d = 10;
    std::string diagnostic;
    std::size_t input_vertex_count = 0;
    std::size_t input_face_count = 0;
    std::size_t output_vertex_count = 0;
    std::size_t output_tetra_count = 0;
    std::size_t output_boundary_face_count = 0;
    std::size_t steiner_vertex_count = 0;
    TetraMeshMetrics tetra_metrics;
    std::vector<Vec3> output_vertices;
    std::vector<Tet> output_tetrahedra;
};

GmshEvaluationResult evaluate_gmsh(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const GmshEvaluationOptions& options
);

std::string gmsh_evaluation_to_json(const GmshEvaluationResult& result);

void write_gmsh_evaluation_json(
    const std::filesystem::path& path,
    const GmshEvaluationResult& result
);

}  // namespace mvrmesh
