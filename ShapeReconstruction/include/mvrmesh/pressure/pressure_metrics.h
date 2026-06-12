#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct PressureConfig;  // defined in "mvrmesh/config/pressure_config.h"

// Cost and feasibility metrics for running DeformSim's dense FEM solve on one
// surface mesh, derived from a TetGen pre-flight.
struct PressureMetrics {
    std::size_t v_surface = 0;  // input surface vertex count
    std::size_t v_tet = 0;  // TetGen output vertex count
    double expansion_ratio = 0.0;  // v_tet / v_surface, or 0 when v_surface is 0
    std::size_t matrix_order_3v_tet = 0;  // dense system order: 3 DOF per tet vertex
    std::size_t memory_peak_bytes_kl = 0;  // dense K and L matrices together
    double dgetri_flops = 0.0;  // one-time inversion cost, ~2 * order^3
    std::size_t n_samples = 22500;  // DeformSim's default sample count per run
    double dgemv_total_flops = 0.0;  // per-sample solves, ~2 * order^2 * n_samples
    std::size_t estimated_disk_per_run_bytes = 0;  // output PLY total across n_samples
    bool tetgen_success = false;
    std::string tetgen_switches = "pYQ";
    std::string failure_reason;  // empty when tetgen_success is true
};

// One row of the pressure comparison matrix: a candidate mesh label, the
// arguments that produced it, and its computed metrics.
struct MatrixRow {
    std::string config;
    std::string args;
    PressureMetrics metrics;
    bool is_baseline = false;  // baseline rows render bold in the Markdown table
};

// Runs the TetGen pre-flight on the mesh (vertices in millimetres) and derives
// the DeformSim cost metrics. A TetGen failure is reported via
// tetgen_success=false and failure_reason, not by throwing.
PressureMetrics compute_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::size_t n_samples,
    const std::string& switches);

// Writes the metrics of one mesh as a JSON object to output_path, creating
// parent directories as needed. Throws std::runtime_error when the file
// cannot be opened.
void write_single_json(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_ply,
    const PressureMetrics& m);

// Writes the Markdown comparison report for all rows to output_path, creating
// parent directories as needed. Throws std::runtime_error when the file
// cannot be opened.
void write_matrix_md(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_mvr_hint,
    const std::vector<MatrixRow>& rows,
    std::size_t n_samples,
    const std::string& switches);

// Formats a byte count as "N B" or as a two-decimal "x.xx KiB/MiB/GiB" string.
std::string format_bytes_human(std::size_t bytes);
// Formats a flop count in two-decimal scientific notation, e.g. "1.23e+09".
std::string format_flops_sci(double flops);

// CLI entry point for the single-mesh report: reads config.input, writes the
// JSON report, and returns a process exit code (0 on success, 1 when the
// input is missing or TetGen fails). Read and write errors propagate.
int run_pressure_single(const PressureConfig& config);
// CLI entry point for the comparison matrix: evaluates every input plus the
// optional baseline (per-mesh read or TetGen failures become failed rows),
// writes the Markdown report, and returns 0. Report write errors propagate.
int run_pressure_matrix(const PressureConfig& config);

}  // namespace mvrmesh
