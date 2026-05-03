#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/core/io.h"
#include "mvrmesh/core/types.h"
#include "mvrmesh/backends/tetgen/tetgen_evaluator.h"

namespace {

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

PressureMetrics compute_metrics(
    const std::vector<mvrmesh::Vec3>& vertices,
    const std::vector<mvrmesh::Face>& faces,
    std::size_t n_samples,
    const std::string& switches)
{
    PressureMetrics m;
    m.v_surface = vertices.size();
    m.n_samples = n_samples;
    m.tetgen_switches = switches;

    mvrmesh::DeformSimPressureOptions opts;
    opts.switches = switches;
    opts.input_ply = "check_fem_pressure_internal";
    mvrmesh::DeformSimPressureResult r = mvrmesh::evaluate_deformsim_pressure(vertices, faces, opts);

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

void usage(const char* argv0) {
    std::cerr << "Usage:\n"
              << "  " << argv0 << " <input.ply> -o <output.json>\n"
              << "  " << argv0 << " --matrix <ply1> [<ply2> ...] -o <output.md>\n"
              << "Options:\n"
              << "  --n-samples N      DeformSim sample count (default 22500)\n"
              << "  --switches s       TetGen switches (default pYQ)\n"
              << "  --baseline P       Add baseline row from P.ply (matrix mode only)\n"
              << "  --label P=name     Friendly label for ply (matrix mode, repeatable)\n";
}

int run_single(
    const std::filesystem::path& input_ply,
    const std::filesystem::path& output_json,
    std::size_t n_samples,
    const std::string& switches)
{
    if (!std::filesystem::exists(input_ply)) {
        std::cerr << "[error] input not found: " << input_ply << "\n";
        return 1;
    }
    std::vector<mvrmesh::Vec3> vertices;
    std::vector<mvrmesh::Face> faces;
    mvrmesh::read_ply(input_ply, vertices, faces);

    PressureMetrics m = compute_metrics(vertices, faces, n_samples, switches);
    write_single_json(output_json, input_ply, m);

    if (!m.tetgen_success) {
        std::cerr << "[warn] tetgen failed: " << m.failure_reason << "\n";
        return 1;
    }
    std::cout << "[ok] check_fem_pressure: V_surf=" << m.v_surface
              << " V_tet=" << m.v_tet
              << " mem=" << m.memory_peak_bytes_kl << " bytes -> "
              << output_json.string() << "\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        std::filesystem::path input_ply;
        std::filesystem::path output_path;
        std::vector<std::filesystem::path> matrix_inputs;
        std::filesystem::path baseline_ply;
        std::vector<std::pair<std::filesystem::path, std::string>> labels;
        std::size_t n_samples = 22500;
        std::string switches = "pYQ";
        bool matrix_mode = false;

        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "-o") {
                if (i + 1 >= argc) { usage(argv[0]); return 2; }
                output_path = argv[++i];
            } else if (arg == "--matrix") {
                matrix_mode = true;
                while (i + 1 < argc && argv[i + 1][0] != '-') {
                    matrix_inputs.push_back(argv[++i]);
                }
            } else if (arg == "--n-samples") {
                if (i + 1 >= argc) { usage(argv[0]); return 2; }
                n_samples = std::stoull(argv[++i]);
            } else if (arg == "--switches") {
                if (i + 1 >= argc) { usage(argv[0]); return 2; }
                switches = argv[++i];
            } else if (arg == "--baseline") {
                if (i + 1 >= argc) { usage(argv[0]); return 2; }
                baseline_ply = argv[++i];
            } else if (arg == "--label") {
                if (i + 1 >= argc) { usage(argv[0]); return 2; }
                std::string spec = argv[++i];
                auto eq = spec.find('=');
                if (eq == std::string::npos) {
                    std::cerr << "[error] --label expects PATH=NAME, got: " << spec << "\n";
                    return 2;
                }
                labels.emplace_back(spec.substr(0, eq), spec.substr(eq + 1));
            } else if (arg == "--help" || arg == "-h") {
                usage(argv[0]);
                return 0;
            } else if (!arg.empty() && arg[0] != '-' && !matrix_mode) {
                input_ply = arg;
            } else {
                std::cerr << "[error] unexpected arg: " << arg << "\n";
                usage(argv[0]);
                return 2;
            }
        }

        if (output_path.empty()) {
            std::cerr << "[error] -o is required\n";
            usage(argv[0]);
            return 2;
        }

        if (matrix_mode) {
            std::cerr << "[error] matrix mode not yet implemented (Task 4.4)\n";
            return 2;
        }

        if (input_ply.empty()) {
            usage(argv[0]);
            return 2;
        }

        return run_single(input_ply, output_path, n_samples, switches);
    } catch (const std::exception& ex) {
        std::cerr << "[error] " << ex.what() << "\n";
        return 1;
    }
}
