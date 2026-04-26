#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "mvrmesh/io.h"
#include "mvrmesh/pipeline.h"
#include "mvrmesh/types.h"

namespace {

struct CliOptions {
    std::filesystem::path input;
    std::filesystem::path output;
    bool has_output = false;
    mvrmesh::OutputFormat format = mvrmesh::OutputFormat::Both;
    mvrmesh::BuildOptions build;
};

[[noreturn]] void throw_usage_error(const std::string& message) {
    throw std::runtime_error(
        message +
        "\nUsage: mvr_to_mesh_cli <input.mvr> [-o|--output <base_path>] "
        "[--format ply|stl|both] [--adaptive-remesh] "
        "[--adaptive-iterations N] [--adaptive-split-ratio R]\n"
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
        } else if (arg == "--format") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --format.");
            }
            options.format = mvrmesh::parse_output_format(argv[++i]);
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

std::vector<std::filesystem::path> default_outputs_for_input(
    const std::filesystem::path& in_path,
    mvrmesh::OutputFormat format
) {
    const std::filesystem::path root = infer_project_root_from_input(in_path);
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

}  // namespace

int main(int argc, char** argv) {
    try {
        const CliOptions args = parse_args(argc, argv);

        const std::filesystem::path in_path = std::filesystem::absolute(args.input);
        if (!std::filesystem::exists(in_path)) {
            throw std::runtime_error("Input file not found: " + in_path.string());
        }

        const std::vector<std::filesystem::path> out_paths =
            args.has_output
                ? mvrmesh::outputs_for_mode(std::filesystem::absolute(args.output), args.format)
                : default_outputs_for_input(in_path, args.format);

        const mvrmesh::ParsedMvr parsed = mvrmesh::parse_mvr(in_path);
        std::cout << "[info] source: vertices=" << parsed.vertices.size()
                  << ", triangles=" << parsed.triangles.size()
                  << ", tetrahedra=" << parsed.tetrahedra.size() << "\n";

        const mvrmesh::BuildResult result = mvrmesh::build_surface(
            parsed.vertices,
            parsed.triangles,
            parsed.tetrahedra,
            args.build
        );
        std::cout << "[info] mode=" << mvrmesh::surface_mode_to_string(result.mode)
                  << ", output vertices=" << result.vertices.size()
                  << ", faces=" << result.faces.size() << "\n";

        for (const auto& out_path : out_paths) {
            const std::filesystem::path out_dir = out_path.parent_path();
            if (!out_dir.empty()) {
                std::error_code ec;
                std::filesystem::create_directories(out_dir, ec);
                if (ec) {
                    throw std::runtime_error(
                        "Failed to create output directory: " + out_dir.string() + ", reason: " + ec.message()
                    );
                }
            }

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
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }

    return 0;
}
