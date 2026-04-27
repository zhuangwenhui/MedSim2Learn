#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/core/metrics.h"
#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct TetGenEvaluationOptions {
    std::string switches = "pYQ";
};

struct TetGenEvaluationResult {
    bool success = false;
    std::string switches;
    std::string diagnostic;
    std::size_t input_vertex_count = 0;
    std::size_t input_face_count = 0;
    std::size_t output_vertex_count = 0;
    std::size_t output_tetra_count = 0;
    std::size_t output_boundary_face_count = 0;
    TetraMeshMetrics tetra_metrics;
    std::vector<Vec3> output_vertices;
    std::vector<Tet> output_tetrahedra;
    std::vector<Face> output_boundary_faces;
};

TetGenEvaluationResult evaluate_tetgen(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const TetGenEvaluationOptions& options
);

std::string tetgen_evaluation_to_json(const TetGenEvaluationResult& result);

void write_tetgen_evaluation_json(
    const std::filesystem::path& path,
    const TetGenEvaluationResult& result
);

}  // namespace mvrmesh
