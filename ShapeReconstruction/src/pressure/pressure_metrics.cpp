// src/pressure/pressure_metrics.cpp

#include "mvrmesh/pressure/pressure_metrics.h"

#include <cstdio>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/config/pressure_config.h"
#include "mvrmesh/core/io.h"
#include "mvrmesh/core/types.h"
#include "mvrmesh/pressure/pressure_evaluator.h"

namespace mvrmesh {

PressureMetrics compute_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::size_t n_samples,
    const std::string& switches)
{
    PressureMetrics m;
    m.v_surface = vertices.size();
    m.n_samples = n_samples;
    m.tetgen_switches = switches;

    DeformSimPressureOptions opts;
    opts.switches = switches;
    opts.input_ply = "check_fem_pressure_internal";
    DeformSimPressureResult r = evaluate_deformsim_pressure(vertices, faces, opts);

    if (!r.success) {
        m.tetgen_success = false;
        m.failure_reason = r.diagnostic.empty() ? "tetgen failed" : r.diagnostic;
        return m;
    }

    m.v_tet = r.tetgen_output_vertex_count;
    m.expansion_ratio = m.v_surface > 0
        ? static_cast<double>(m.v_tet) / static_cast<double>(m.v_surface) : 0.0;
    m.matrix_order_3v_tet = static_cast<std::size_t>(m.v_tet) * 3u;
    m.memory_peak_bytes_kl = r.estimated_dense_k_l_bytes;
    const double order_d = static_cast<double>(m.matrix_order_3v_tet);
    m.dgetri_flops = order_d * order_d * order_d * 2.0;
    m.dgemv_total_flops = order_d * order_d * 2.0 * static_cast<double>(n_samples);
    m.estimated_disk_per_run_bytes = n_samples * (m.v_surface * 64u + 256u);
    m.tetgen_success = true;
    return m;
}

void write_single_json(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_ply,
    const PressureMetrics& m)
{
    std::filesystem::create_directories(output_path.parent_path());
    std::ofstream out(output_path);
    if (!out) throw std::runtime_error("cannot open output: " + output_path.string());

    out << "{\n";
    out << "  \"input_ply\": \"" << input_ply.string() << "\",\n";
    out << "  \"v_surface\": " << m.v_surface << ",\n";
    out << "  \"v_tet\": " << m.v_tet << ",\n";
    out << "  \"expansion_ratio\": " << m.expansion_ratio << ",\n";
    out << "  \"matrix_order_3v_tet\": " << m.matrix_order_3v_tet << ",\n";
    out << "  \"memory_peak_bytes_kl\": " << m.memory_peak_bytes_kl << ",\n";
    out << "  \"dgetri_flops\": " << m.dgetri_flops << ",\n";
    out << "  \"n_samples\": " << m.n_samples << ",\n";
    out << "  \"dgemv_total_flops\": " << m.dgemv_total_flops << ",\n";
    out << "  \"estimated_disk_per_run_bytes\": " << m.estimated_disk_per_run_bytes << ",\n";
    out << "  \"tetgen_success\": " << (m.tetgen_success ? "true" : "false") << ",\n";
    out << "  \"tetgen_switches\": \"" << m.tetgen_switches << "\"";
    if (!m.failure_reason.empty()) {
        out << ",\n  \"failure_reason\": \"" << m.failure_reason << "\"";
    }
    out << "\n}\n";
}

std::string format_bytes_human(std::size_t bytes) {
    constexpr double KIB = 1024.0;
    constexpr double MIB = KIB * 1024.0;
    constexpr double GIB = MIB * 1024.0;
    char buf[64];
    if (bytes >= static_cast<std::size_t>(GIB)) {
        std::snprintf(buf, sizeof(buf), "%.2f GiB", static_cast<double>(bytes) / GIB);
    } else if (bytes >= static_cast<std::size_t>(MIB)) {
        std::snprintf(buf, sizeof(buf), "%.2f MiB", static_cast<double>(bytes) / MIB);
    } else if (bytes >= static_cast<std::size_t>(KIB)) {
        std::snprintf(buf, sizeof(buf), "%.2f KiB", static_cast<double>(bytes) / KIB);
    } else {
        std::snprintf(buf, sizeof(buf), "%zu B", bytes);
    }
    return std::string(buf);
}

std::string format_flops_sci(double flops) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.2e", flops);
    return std::string(buf);
}

void write_matrix_md(
    const std::filesystem::path& output_path,
    const std::filesystem::path& input_mvr_hint,
    const std::vector<MatrixRow>& rows,
    std::size_t n_samples,
    const std::string& switches)
{
    std::filesystem::create_directories(output_path.parent_path());
    std::ofstream out(output_path);
    if (!out) throw std::runtime_error("cannot open: " + output_path.string());

    auto t = std::time(nullptr);
    char timestr[64];
    std::tm tm_local{};
#if defined(_MSC_VER)
    localtime_s(&tm_local, &t);
#else
    tm_local = *std::localtime(&t);
#endif
    std::strftime(timestr, sizeof(timestr), "%Y-%m-%d %H:%M:%S", &tm_local);

    out << "# FEM Pressure Matrix Report\n\n";
    out << "**Input MVR**: " << input_mvr_hint.string() << "\n";
    out << "**Generated**: " << timestr << "\n";
    out << "**N_samples** (DeformSim default per run): " << n_samples << "\n";
    out << "**TetGen switches**: " << switches << "\n\n";

    out << "## Pressure dimensions explained\n\n";
    out << "- **V_surf** -- .ply vertex count\n";
    out << "- **V_tet** -- TetGen tetrahedralized internal vertex count\n";
    out << "- **Memory (K+L)** -- (3V_tet)^2 * 16 bytes, peak for entire DeformSim run\n";
    out << "- **DGETRI flops** -- (3V_tet)^3 * 2, one-time matrix inversion\n";
    out << "- **DGEMV total flops** -- (3V_tet)^2 * 2 * N_samples, per-sample solve total\n";
    out << "- **Output disk** -- N_samples * (V_surf * 64 bytes), output PLY total\n\n";

    out << "## Results\n\n";
    out << "| Config | Args | V_surf | V_tet | Memory (K+L) | DGETRI flops | DGEMV total | Output disk |\n";
    out << "|--------|------|--------|-------|--------------|--------------|-------------|-------------|\n";

    for (const auto& row : rows) {
        if (row.is_baseline) out << "| **(baseline)** ";
        else out << "| ";
        out << row.config << " | ";
        out << "`" << row.args << "` | ";
        if (!row.metrics.tetgen_success) {
            out << "(failed: " << row.metrics.failure_reason << ") | -- | -- | -- | -- | -- |\n";
            continue;
        }
        out << row.metrics.v_surface << " | "
            << row.metrics.v_tet << " | "
            << format_bytes_human(row.metrics.memory_peak_bytes_kl) << " | "
            << format_flops_sci(row.metrics.dgetri_flops) << " | "
            << format_flops_sci(row.metrics.dgemv_total_flops) << " | "
            << format_bytes_human(row.metrics.estimated_disk_per_run_bytes) << " |\n";
    }
    out << "\n";

    out << "## Interpretation\n\n";
    out << "- Critical V where DGETRI overtakes DGEMV: V_surf ~= 2500 (assuming TetGen expansion ~= 3)\n";
    out << "- Below this V: DGEMV total dominates (per-sample work x N_samples)\n";
    out << "- Above this V: DGETRI dominates (one-time inversion)\n";
}

int run_pressure_single(const PressureConfig& config) {
    if (!std::filesystem::exists(config.input)) {
        std::cerr << "[error] input not found: " << config.input << "\n";
        return 1;
    }
    std::vector<Vec3> vertices;
    std::vector<Face> faces;
    read_ply(config.input, vertices, faces);

    PressureMetrics m = compute_metrics(vertices, faces, config.n_samples, config.switches);
    write_single_json(config.output, config.input, m);

    if (!m.tetgen_success) {
        std::cerr << "[warn] tetgen failed: " << m.failure_reason << "\n";
        return 1;
    }
    std::cout << "[ok] check_fem_pressure: V_surf=" << m.v_surface
              << " V_tet=" << m.v_tet
              << " mem=" << m.memory_peak_bytes_kl << " bytes -> "
              << config.output.string() << "\n";
    return 0;
}

int run_pressure_matrix(const PressureConfig& config) {
    std::vector<MatrixRow> rows;

    auto resolve_label = [&](const std::filesystem::path& p) -> std::string {
        for (const auto& kv : config.labels) {
            std::error_code ec;
            if (std::filesystem::equivalent(kv.first, p, ec)) return kv.second;
        }
        return p.filename().string();
    };

    for (const auto& p : config.inputs) {
        MatrixRow row;
        row.config = resolve_label(p);
        row.args = "(see candidate list)";
        if (!std::filesystem::exists(p)) {
            row.metrics.tetgen_success = false;
            row.metrics.failure_reason = "input not found";
            rows.push_back(row);
            continue;
        }
        std::vector<Vec3> v;
        std::vector<Face> f;
        try {
            read_ply(p, v, f);
        } catch (const std::exception& ex) {
            row.metrics.tetgen_success = false;
            row.metrics.failure_reason = std::string("read_ply failed: ") + ex.what();
            rows.push_back(row);
            continue;
        }
        row.metrics = compute_metrics(v, f, config.n_samples, config.switches);
        rows.push_back(row);
    }

    if (!config.baseline.empty()) {
        MatrixRow row;
        row.config = config.baseline.filename().string();
        row.args = "(DeformSim current input)";
        row.is_baseline = true;
        if (!std::filesystem::exists(config.baseline)) {
            row.metrics.tetgen_success = false;
            row.metrics.failure_reason = "baseline not found";
        } else {
            std::vector<Vec3> v;
            std::vector<Face> f;
            try {
                read_ply(config.baseline, v, f);
                row.metrics = compute_metrics(v, f, config.n_samples, config.switches);
            } catch (const std::exception& ex) {
                row.metrics.tetgen_success = false;
                row.metrics.failure_reason = std::string("read_ply failed: ") + ex.what();
            }
        }
        rows.push_back(row);
    }

    std::filesystem::path mvr_hint = config.inputs.empty()
        ? std::filesystem::path{}
        : config.inputs.front();
    write_matrix_md(config.output, mvr_hint, rows, config.n_samples, config.switches);

    std::cout << "[ok] check_fem_pressure matrix: " << rows.size()
              << " rows -> " << config.output.string() << "\n";
    return 0;
}

}  // namespace mvrmesh
