#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/backends/cgal/cgal_pmp_backend.h"
#include "mvrmesh/backends/gmsh/gmsh_evaluator.h"
#include "mvrmesh/core/io.h"
#include "mvrmesh/core/metrics.h"
#include "mvrmesh/core/pipeline.h"
#include "mvrmesh/backends/tetgen/tetgen_evaluator.h"
#include "mvrmesh/core/types.h"

namespace {

enum class SurfaceBackend {
    Native,
    Cgal
};

struct CliOptions {
    std::filesystem::path input;
    std::filesystem::path output;
    std::filesystem::path metrics_output;
    std::filesystem::path gmsh_metrics_output;
    std::filesystem::path tetgen_metrics_output;
    bool has_output = false;
    bool has_metrics_output = false;
    bool evaluate_gmsh = false;
    bool has_gmsh_metrics_output = false;
    bool has_gmsh_algorithm3d = false;
    bool evaluate_tetgen = false;
    bool has_tetgen_metrics_output = false;
    bool has_tetgen_switches = false;
    bool has_cgal_target_edge_length = false;
    bool has_cgal_iterations = false;
    std::string tetgen_switches = "pYQ";
    mvrmesh::OutputFormat format = mvrmesh::OutputFormat::Both;
    SurfaceBackend surface_backend = SurfaceBackend::Native;
    mvrmesh::BuildOptions build;
    mvrmesh::CgalPmpOptions cgal;
    mvrmesh::GmshEvaluationOptions gmsh;
};

[[noreturn]] void throw_usage_error(const std::string& message) {
    throw std::runtime_error(
        message +
        "\nUsage: mvr_to_mesh_cli <input.mvr> [-o|--output <base_path>] "
        "[--format ply|stl|both] [--metrics-output <json_path>] "
        "[--surface-backend native|cgal] [--cgal-target-edge-length <value>] "
        "[--cgal-iterations <n>] "
        "[--evaluate-gmsh] [--gmsh-algorithm3d <int>] "
        "[--gmsh-metrics-output <json_path>] "
        "[--evaluate-tetgen] [--tetgen-switches <switches>] "
        "[--tetgen-metrics-output <json_path>] [--adaptive-remesh] "
        "[--adaptive-iterations N] [--adaptive-split-ratio R]\n"
        "Default input root for relative paths: <project_root>/originalData\n"
        "Default output (without --output): <project_root>/outPut/{PLY|STL}/<input_stem>"
    );
}

int parse_int_value(const std::string& text, const std::string& flag_name) {
    std::size_t consumed = 0;
    const int value = std::stoi(text, &consumed);
    if (consumed != text.size()) {
        throw std::runtime_error("Invalid value for " + flag_name + ": " + text);
    }
    return value;
}

double parse_double_value(const std::string& text, const std::string& flag_name) {
    std::size_t consumed = 0;
    const double value = std::stod(text, &consumed);
    if (consumed != text.size()) {
        throw std::runtime_error("Invalid value for " + flag_name + ": " + text);
    }
    return value;
}

SurfaceBackend parse_surface_backend(const std::string& text) {
    if (text == "native") {
        return SurfaceBackend::Native;
    }
    if (text == "cgal") {
        return SurfaceBackend::Cgal;
    }
    throw std::runtime_error("Invalid value for --surface-backend: " + text);
}

std::string surface_backend_to_string(SurfaceBackend backend) {
    switch (backend) {
        case SurfaceBackend::Native:
            return "native";
        case SurfaceBackend::Cgal:
            return "cgal";
    }
    return "unknown";
}

CliOptions parse_args(int argc, char** argv) {
    if (argc <= 1) {
        throw_usage_error("Missing required <input.mvr>.");
    }

    CliOptions options;

    bool has_input = false;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];

        if (arg == "-h" || arg == "--help") {
            throw_usage_error("Help requested.");
        } else if (arg == "-o" || arg == "--output") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --output.");
            }
            options.output = std::filesystem::path(argv[++i]);
            options.has_output = true;
        } else if (arg == "--metrics-output") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --metrics-output.");
            }
            options.metrics_output = std::filesystem::path(argv[++i]);
            options.has_metrics_output = true;
        } else if (arg == "--evaluate-gmsh") {
            options.evaluate_gmsh = true;
        } else if (arg == "--gmsh-algorithm3d") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --gmsh-algorithm3d.");
            }
            options.gmsh.algorithm3d = parse_int_value(argv[++i], "--gmsh-algorithm3d");
            options.has_gmsh_algorithm3d = true;
        } else if (arg == "--gmsh-metrics-output") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --gmsh-metrics-output.");
            }
            options.gmsh_metrics_output = std::filesystem::path(argv[++i]);
            options.has_gmsh_metrics_output = true;
        } else if (arg == "--evaluate-tetgen") {
            options.evaluate_tetgen = true;
        } else if (arg == "--tetgen-switches") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --tetgen-switches.");
            }
            options.tetgen_switches = argv[++i];
            options.has_tetgen_switches = true;
        } else if (arg == "--tetgen-metrics-output") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --tetgen-metrics-output.");
            }
            options.tetgen_metrics_output = std::filesystem::path(argv[++i]);
            options.has_tetgen_metrics_output = true;
        } else if (arg == "--format") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --format.");
            }
            options.format = mvrmesh::parse_output_format(argv[++i]);
        } else if (arg == "--surface-backend") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --surface-backend.");
            }
            options.surface_backend = parse_surface_backend(argv[++i]);
        } else if (arg == "--cgal-target-edge-length") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --cgal-target-edge-length.");
            }
            options.cgal.target_edge_length = parse_double_value(argv[++i], "--cgal-target-edge-length");
            options.has_cgal_target_edge_length = true;
        } else if (arg == "--cgal-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --cgal-iterations.");
            }
            options.cgal.remesh_iterations = parse_int_value(argv[++i], "--cgal-iterations");
            options.has_cgal_iterations = true;
        } else if (arg == "--adaptive-remesh") {
            options.build.adaptive_remesh = true;
        } else if (arg == "--adaptive-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --adaptive-iterations.");
            }
            options.build.adaptive_iterations = parse_int_value(argv[++i], "--adaptive-iterations");
        } else if (arg == "--adaptive-split-ratio") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --adaptive-split-ratio.");
            }
            options.build.adaptive_split_ratio = parse_double_value(argv[++i], "--adaptive-split-ratio");
        } else if (!arg.empty() && arg[0] == '-') {
            throw_usage_error("Unknown option: " + arg);
        } else {
            if (has_input) {
                throw_usage_error("Only one positional input path is supported.");
            }
            options.input = std::filesystem::path(arg);
            has_input = true;
        }
    }

    if (!has_input) {
        throw_usage_error("Missing required <input.mvr>.");
    }

    if (options.build.adaptive_iterations < 1) {
        throw std::runtime_error("--adaptive-iterations must be >= 1");
    }
    if (!(options.build.adaptive_split_ratio > 0.0 && options.build.adaptive_split_ratio <= 1.0)) {
        throw std::runtime_error("--adaptive-split-ratio must be in (0, 1]");
    }
    if (options.has_tetgen_metrics_output && !options.evaluate_tetgen) {
        throw std::runtime_error("--tetgen-metrics-output requires --evaluate-tetgen");
    }
    if (options.has_tetgen_switches && !options.evaluate_tetgen) {
        throw std::runtime_error("--tetgen-switches requires --evaluate-tetgen");
    }
    if (options.has_gmsh_metrics_output && !options.evaluate_gmsh) {
        throw std::runtime_error("--gmsh-metrics-output requires --evaluate-gmsh");
    }
    if (options.has_gmsh_algorithm3d && !options.evaluate_gmsh) {
        throw std::runtime_error("--gmsh-algorithm3d requires --evaluate-gmsh");
    }
    if (options.has_gmsh_algorithm3d && options.gmsh.algorithm3d <= 0) {
        throw std::runtime_error("--gmsh-algorithm3d must be > 0");
    }
    if (options.surface_backend != SurfaceBackend::Cgal) {
        if (options.has_cgal_target_edge_length) {
            throw std::runtime_error("--cgal-target-edge-length requires --surface-backend cgal");
        }
        if (options.has_cgal_iterations) {
            throw std::runtime_error("--cgal-iterations requires --surface-backend cgal");
        }
    }
    if (options.has_cgal_target_edge_length && !(options.cgal.target_edge_length > 0.0)) {
        throw std::runtime_error("--cgal-target-edge-length must be > 0");
    }
    if (options.has_cgal_iterations && options.cgal.remesh_iterations < 1) {
        throw std::runtime_error("--cgal-iterations must be >= 1");
    }

    return options;
}

std::string to_lower_ascii(std::string text) {
    for (char& ch : text) {
        if (ch >= 'A' && ch <= 'Z') {
            ch = static_cast<char>(ch - 'A' + 'a');
        }
    }
    return text;
}

std::filesystem::path infer_project_root_from_input(const std::filesystem::path& in_path) {
    const std::filesystem::path parent = in_path.parent_path();
    if (parent.empty()) {
        return in_path.parent_path();
    }

    const std::string parent_name = to_lower_ascii(parent.filename().string());
    const std::filesystem::path grandparent = parent.parent_path();
    const std::string grandparent_name = to_lower_ascii(grandparent.filename().string());

    if (parent_name == "mvr" && grandparent_name == "originaldata") {
        return grandparent.parent_path();
    }
    return parent;
}

bool looks_like_project_root(const std::filesystem::path& path) {
    return std::filesystem::exists(path / "originalData") &&
           std::filesystem::exists(path / "CMakeLists.txt");
}

std::filesystem::path find_project_root_upward(std::filesystem::path start) {
    if (start.empty()) {
        return {};
    }

    std::error_code ec;
    std::filesystem::path current = std::filesystem::absolute(start, ec);
    if (ec) {
        current = start;
    }
    if (std::filesystem::is_regular_file(current, ec)) {
        current = current.parent_path();
    }

    while (!current.empty()) {
        if (looks_like_project_root(current)) {
            return current;
        }
        const std::filesystem::path parent = current.parent_path();
        if (parent == current) {
            break;
        }
        current = parent;
    }
    return {};
}

std::filesystem::path find_project_root(const char* argv0) {
    std::filesystem::path root = find_project_root_upward(std::filesystem::current_path());
    if (!root.empty()) {
        return root;
    }

    root = find_project_root_upward(std::filesystem::path(argv0));
    if (!root.empty()) {
        return root;
    }

    return {};
}

std::filesystem::path resolve_input_path(
    const std::filesystem::path& input,
    const std::filesystem::path& project_root
) {
    if (input.is_absolute()) {
        return input;
    }

    std::error_code ec;
    const std::filesystem::path cwd_candidate = std::filesystem::absolute(input, ec);
    if (!ec && std::filesystem::exists(cwd_candidate)) {
        return cwd_candidate;
    }

    if (!project_root.empty()) {
        const std::filesystem::path project_candidate = project_root / input;
        if (std::filesystem::exists(project_candidate)) {
            return project_candidate;
        }

        const std::filesystem::path original_data_candidate = project_root / "originalData" / input;
        if (std::filesystem::exists(original_data_candidate)) {
            return original_data_candidate;
        }
    }

    if (!ec) {
        return cwd_candidate;
    }
    return input;
}

std::vector<std::filesystem::path> default_outputs_for_input(
    const std::filesystem::path& in_path,
    mvrmesh::OutputFormat format,
    const std::filesystem::path& project_root
) {
    const std::filesystem::path root =
        project_root.empty() ? infer_project_root_from_input(in_path) : project_root;
    const std::string stem = in_path.stem().string();
    std::vector<std::filesystem::path> outputs;

    if (format == mvrmesh::OutputFormat::Ply) {
        outputs.push_back(root / "outPut" / "PLY" / (stem + ".ply"));
    } else if (format == mvrmesh::OutputFormat::Stl) {
        outputs.push_back(root / "outPut" / "STL" / (stem + ".stl"));
    } else {
        outputs.push_back(root / "outPut" / "PLY" / (stem + ".ply"));
        outputs.push_back(root / "outPut" / "STL" / (stem + ".stl"));
    }
    return outputs;
}

void ensure_parent_directory(const std::filesystem::path& path) {
    const std::filesystem::path dir = path.parent_path();
    if (dir.empty()) {
        return;
    }

    std::error_code ec;
    std::filesystem::create_directories(dir, ec);
    if (ec) {
        throw std::runtime_error(
            "Failed to create output directory: " + dir.string() + ", reason: " + ec.message()
        );
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const CliOptions args = parse_args(argc, argv);

        const std::filesystem::path project_root = find_project_root(argv[0]);
        const std::filesystem::path in_path = resolve_input_path(args.input, project_root);
        if (!std::filesystem::exists(in_path)) {
            throw std::runtime_error("Input file not found: " + in_path.string());
        }

        const std::vector<std::filesystem::path> out_paths =
            args.has_output
                ? mvrmesh::outputs_for_mode(std::filesystem::absolute(args.output), args.format)
                : default_outputs_for_input(in_path, args.format, project_root);

        const mvrmesh::ParsedMvr parsed = mvrmesh::parse_mvr(in_path);
        std::cout << "[info] source: vertices=" << parsed.vertices.size()
                  << ", triangles=" << parsed.triangles.size()
                  << ", tetrahedra=" << parsed.tetrahedra.size() << "\n";

        mvrmesh::BuildResult result = mvrmesh::build_surface(
            parsed.vertices,
            parsed.triangles,
            parsed.tetrahedra,
            args.build
        );
        std::cout << "[info] mode=" << mvrmesh::surface_mode_to_string(result.mode)
                  << ", output vertices=" << result.vertices.size()
                  << ", faces=" << result.faces.size() << "\n";

        if (args.surface_backend == SurfaceBackend::Cgal) {
#if MVRMESH_CGAL_PMP_ENABLED
            const mvrmesh::CgalPmpResult cgal_result =
                mvrmesh::run_cgal_pmp_backend(result.vertices, result.faces, args.cgal);
            if (!cgal_result.success) {
                throw std::runtime_error("CGAL PMP backend failed: " + cgal_result.diagnostic);
            }
            result.vertices = std::move(cgal_result.output_vertices);
            result.faces = std::move(cgal_result.output_faces);
#else
            throw std::runtime_error("CGAL PMP backend is disabled in this build.");
#endif
        }
        std::cout << "[info] surface backend=" << surface_backend_to_string(args.surface_backend)
                  << ", output vertices=" << result.vertices.size()
                  << ", faces=" << result.faces.size() << "\n";

        if (args.evaluate_tetgen) {
#if MVRMESH_TETGEN_ENABLED
            mvrmesh::TetGenEvaluationOptions tetgen_options;
            tetgen_options.switches = args.tetgen_switches;
            const mvrmesh::TetGenEvaluationResult tetgen_result =
                mvrmesh::evaluate_tetgen(result.vertices, result.faces, tetgen_options);
            if (!tetgen_result.success) {
                throw std::runtime_error("TetGen evaluation failed: " + tetgen_result.diagnostic);
            }
            std::cout << "[info] tetgen switches=" << tetgen_result.switches
                      << ", output vertices=" << tetgen_result.output_vertex_count
                      << ", tetrahedra=" << tetgen_result.output_tetra_count
                      << ", boundary faces=" << tetgen_result.output_boundary_face_count << "\n";

            if (args.has_tetgen_metrics_output) {
                const std::filesystem::path tetgen_metrics_path =
                    std::filesystem::absolute(args.tetgen_metrics_output);
                ensure_parent_directory(tetgen_metrics_path);
                mvrmesh::write_tetgen_evaluation_json(tetgen_metrics_path, tetgen_result);
                std::cout << "[ok] wrote tetgen metrics " << tetgen_metrics_path.string() << "\n";
            }
#else
            throw std::runtime_error("TetGen evaluation backend is disabled in this build.");
#endif
        }

        if (args.evaluate_gmsh) {
#if MVRMESH_GMSH_ENABLED
            const mvrmesh::GmshEvaluationResult gmsh_result =
                mvrmesh::evaluate_gmsh(result.vertices, result.faces, args.gmsh);
            if (!gmsh_result.success) {
                throw std::runtime_error("Gmsh evaluation failed: " + gmsh_result.diagnostic);
            }
            std::cout << "[info] gmsh algorithm3d=" << gmsh_result.algorithm3d
                      << ", output vertices=" << gmsh_result.output_vertex_count
                      << ", tetrahedra=" << gmsh_result.output_tetra_count
                      << ", boundary faces=" << gmsh_result.output_boundary_face_count << "\n";

            if (args.has_gmsh_metrics_output) {
                const std::filesystem::path gmsh_metrics_path =
                    std::filesystem::absolute(args.gmsh_metrics_output);
                ensure_parent_directory(gmsh_metrics_path);
                mvrmesh::write_gmsh_evaluation_json(gmsh_metrics_path, gmsh_result);
                std::cout << "[ok] wrote gmsh metrics " << gmsh_metrics_path.string() << "\n";
            }
#else
            throw std::runtime_error("Gmsh evaluation backend is disabled in this build.");
#endif
        }

        for (const auto& out_path : out_paths) {
            ensure_parent_directory(out_path);

            const std::string ext = out_path.extension().string();
            if (ext == ".ply" || ext == ".PLY") {
                mvrmesh::write_ply(out_path, result.vertices, result.faces);
            } else if (ext == ".stl" || ext == ".STL") {
                mvrmesh::write_stl(out_path, result.vertices, result.faces);
            } else {
                throw std::runtime_error("Unsupported output extension: " + out_path.extension().string());
            }
            std::cout << "[ok] wrote " << out_path.string() << "\n";
        }

        if (args.has_metrics_output) {
            const std::filesystem::path metrics_path = std::filesystem::absolute(args.metrics_output);
            ensure_parent_directory(metrics_path);
            const mvrmesh::SurfaceMetrics metrics =
                mvrmesh::compute_surface_metrics(result.vertices, result.faces);
            mvrmesh::write_metrics_json(metrics_path, metrics);
            std::cout << "[ok] wrote metrics " << metrics_path.string() << "\n";
        }
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }

    return 0;
}
