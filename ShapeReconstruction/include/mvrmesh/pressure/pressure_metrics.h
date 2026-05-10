// include/mvrmesh/pressure/pressure_metrics.h
#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include "mvrmesh/core/types.h"

namespace mvrmesh {

struct PressureConfig;  // forward declare

struct PressureMetrics {
    std::size_t v_surface = 0;
    std::size_t v_tet = 0;
    double expansion_ratio = 0.0;
    std::size_t matrix_order_3v_tet = 0;
    std::size_t memory_peak_bytes_kl = 0;
    double dgetri_flops = 0.0;
    std::size_t n_samples = 22500;
    double dgemv_total_flops = 0.0;
    std::size_t estimated_disk_per_run_bytes = 0;
    bool tetgen_success = false;
    std::string tetgen_switches = "pYQ";
    std::string failure_reason;
};

struct MatrixRow {
    std::string config;
    std::string args;
    PressureMetrics metrics;
    bool is_baseline = false;
};

PressureMetrics compute_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::size_t n_samples,
    const std::string& switches);

void write_single_json(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_ply,
    const PressureMetrics& m);

void write_matrix_md(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_mvr_hint,
    const std::vector<MatrixRow>& rows,
    std::size_t n_samples,
    const std::string& switches);

std::string format_bytes_human(std::size_t bytes);
std::string format_flops_sci(double flops);

int run_pressure_single(const PressureConfig& config);
int run_pressure_matrix(const PressureConfig& config);

}  // namespace mvrmesh
