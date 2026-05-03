#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/backends/cgal/cgal_mesh.h"
#include "mvrmesh/core/io.h"
#include "mvrmesh/core/pipeline.h"
#include "mvrmesh/core/types.h"

namespace {

struct CliOptions {
    std::filesystem::path input;
    std::filesystem::path output;
    bool has_output = false;
    mvrmesh::BuildOptions build;

    // robust pipeline (Task 7)
    bool cgal_mesh = false;
    bool has_sharp_edge_degrees = false;
    bool has_robust_target_edge_length = false;
    bool has_remesh_iterations = false;
    double sharp_edge_degrees = 60.0;
    double robust_target_edge_length = 0.0;
    int remesh_iterations = 3;
};

[[noreturn]] void throw_usage_error(const std::string& message) {
    throw std::runtime_error(
        message +
        "\nUsage: mvr_to_mesh_cli <input.mvr> [-o|--output <base_path>] "
        "[--adaptive-remesh] "
        "[--adaptive-iterations N] [--adaptive-split-ratio R] "
        "[--cgal-mesh [--sharp-edge-degrees D] "
        "[--target-edge-length L] [--remesh-iterations N]]\n"
        "Default input root for relative paths: <project_root>/originalData\n"
        "Default output (without --output): <project_root>/outPut/PLY/<input_stem>.ply"
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
        } else if (arg == "--cgal-mesh") {
            options.cgal_mesh = true;
        } else if (arg == "--sharp-edge-degrees") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --sharp-edge-degrees.");
            }
            options.sharp_edge_degrees = parse_double_value(
                argv[++i], "--sharp-edge-degrees");
            options.has_sharp_edge_degrees = true;
        } else if (arg == "--target-edge-length") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --target-edge-length.");
            }
            options.robust_target_edge_length = parse_double_value(
                argv[++i], "--target-edge-length");
            options.has_robust_target_edge_length = true;
        } else if (arg == "--remesh-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --remesh-iterations.");
            }
            options.remesh_iterations = parse_int_value(
                argv[++i], "--remesh-iterations");
            options.has_remesh_iterations = true;
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

    // Robust pipeline validation (Task 7)
    if (options.cgal_mesh) {
        if (options.build.adaptive_remesh) {
            throw std::runtime_error("--cgal-mesh conflicts with --adaptive-remesh");
        }
        if (!(options.sharp_edge_degrees > 0.0 && options.sharp_edge_degrees < 180.0)) {
            throw std::runtime_error("--sharp-edge-degrees must be in (0, 180)");
        }
        if (options.robust_target_edge_length < 0.0) {
            throw std::runtime_error("--target-edge-length must be >= 0");
        }
        if (options.remesh_iterations < 1) {
            throw std::runtime_error("--remesh-iterations must be >= 1");
        }
    } else {
        if (options.has_sharp_edge_degrees) {
            throw std::runtime_error("--sharp-edge-degrees requires --cgal-mesh");
        }
        if (options.has_robust_target_edge_length) {
            throw std::runtime_error("--target-edge-length requires --cgal-mesh");
        }
        if (options.has_remesh_iterations) {
            throw std::runtime_error("--remesh-iterations requires --cgal-mesh");
        }
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
    const std::filesystem::path& project_root
) {
    const std::filesystem::path root =
        project_root.empty() ? infer_project_root_from_input(in_path) : project_root;
    const std::string stem = in_path.stem().string();
    return { root / "outPut" / "PLY" / (stem + ".ply") };
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
                ? mvrmesh::outputs_for_mode(std::filesystem::absolute(args.output))
                : default_outputs_for_input(in_path, project_root);

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

        if (args.cgal_mesh) {
            mvrmesh::CgalMeshOptions ropts;
            ropts.sharp_edge_dihedral_degrees = args.sharp_edge_degrees;
            ropts.target_edge_length          = args.robust_target_edge_length;
            ropts.remesh_iterations           = args.remesh_iterations;
            mvrmesh::CgalMeshResult robust =
                mvrmesh::run_cgal_mesh(result.vertices, result.faces, ropts);
            result.vertices = std::move(robust.vertices);
            result.faces    = std::move(robust.faces);
        }
        std::cout << "[info] surface backend="
                  << (args.cgal_mesh ? "cgal_mesh" : "native")
                  << ", output vertices=" << result.vertices.size()
                  << ", faces=" << result.faces.size() << "\n";

        for (const auto& out_path : out_paths) {
            ensure_parent_directory(out_path);

            const std::string ext = out_path.extension().string();
            if (ext != ".ply" && ext != ".PLY") {
                throw std::runtime_error("Unsupported output extension: " + out_path.extension().string());
            }
            mvrmesh::write_ply(out_path, result.vertices, result.faces);
            std::cout << "[ok] wrote " << out_path.string() << "\n";
        }

    } catch (const std::exception& ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }

    return 0;
}
