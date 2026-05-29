// src/config/config_loader.cpp

#include "mvrmesh/config/config_loader.h"

#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

#include <yaml-cpp/yaml.h>

// -- YAML::convert specialization for std::filesystem::path ------------------

namespace YAML {
template<>
struct convert<std::filesystem::path> {
    static bool decode(const Node& node, std::filesystem::path& rhs) {
        rhs = node.as<std::string>();
        return true;
    }
};
}  // namespace YAML

namespace mvrmesh {

namespace {

// -- helpers -----------------------------------------------------------------

template<typename T>
void read_optional(const YAML::Node& node, const char* key, T& target) {
    if (node[key]) target = node[key].as<T>();
}

[[noreturn]] void throw_usage_error(const std::string& message) {
    throw std::runtime_error(
        message +
        "\nUsage: mvr_to_mesh_cli <input.mvr> [-o|--output <base_path>] "
        "[--mode <name>] [--config <yaml>] "
        "[--adaptive-remesh] "
        "[--adaptive-iterations N] [--adaptive-split-ratio R] "
        "[--uniform-subdivide] [--uniform-iterations N] "
        "[--taubin-smooth [--taubin-iterations N] [--taubin-lambda X] [--taubin-mu X]] "
        "[--sdf-reconstruct [--sdf-resolution N] [--sdf-padding-ratio R] "
        "[--sdf-target-edge-length L] [--sdf-remesh-iterations N] "
        "[--sdf-sharp-edge-degrees D]] "
        "[--cgal-mesh [--sharp-edge-degrees D] "
        "[--target-edge-length L] [--remesh-iterations N]] "
        "[--voxel-spacing-mm X] [--restore-physical-coords true|false] "
        "[--mesh-quality-fix true|false] "
        "[--canonicalize-pose true|false]\n"
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

// -- YAML section loaders ----------------------------------------------------

void load_adaptive_remesh_section(const YAML::Node& node,
                                  AdaptiveRemeshConfig& cfg) {
    read_optional(node, "iterations", cfg.iterations);
    read_optional(node, "split_ratio", cfg.split_ratio);
}

void load_uniform_subdivide_section(const YAML::Node& node,
                                    UniformSubdivideConfig& cfg) {
    read_optional(node, "iterations", cfg.iterations);
}

void load_taubin_section(const YAML::Node& node, TaubinConfig& cfg) {
    read_optional(node, "iterations", cfg.iterations);
    read_optional(node, "lambda", cfg.lambda);
    read_optional(node, "mu", cfg.mu);
    read_optional(node, "preserve_boundary", cfg.preserve_boundary);
}

void load_sdf_reconstruct_section(const YAML::Node& node,
                                  SdfReconstructConfig& cfg) {
    read_optional(node, "resolution", cfg.resolution);
    read_optional(node, "padding_ratio", cfg.padding_ratio);
    read_optional(node, "sharp_edge_dihedral_degrees",
                  cfg.sharp_edge_dihedral_degrees);
    read_optional(node, "target_edge_length", cfg.target_edge_length);
    read_optional(node, "remesh_iterations", cfg.remesh_iterations);
}

void load_cgal_mesh_section(const YAML::Node& node, CgalMeshConfig& cfg) {
    read_optional(node, "sharp_edge_dihedral_degrees",
                  cfg.sharp_edge_dihedral_degrees);
    read_optional(node, "target_edge_length", cfg.target_edge_length);
    read_optional(node, "remesh_iterations", cfg.remesh_iterations);
}

}  // namespace

// -- Public API: YAML loading ------------------------------------------------

PipelineConfig load_config_from_yaml(const std::filesystem::path& yaml_path) {
    YAML::Node root = YAML::LoadFile(yaml_path.string());

    PipelineConfig config;

    read_optional(root, "input", config.input);
    read_optional(root, "output", config.output);

    if (root["mode"]) {
        config.mode = parse_surface_mode(root["mode"].as<std::string>());
    }
    if (root["cgal_mesh_post"]) {
        config.cgal_mesh_post = root["cgal_mesh_post"].as<bool>();
    }

    if (root["adaptive_remesh"]) {
        load_adaptive_remesh_section(root["adaptive_remesh"],
                                     config.adaptive_remesh);
    }
    if (root["uniform_subdivide"]) {
        load_uniform_subdivide_section(root["uniform_subdivide"],
                                       config.uniform_subdivide);
    }
    if (root["taubin"]) {
        load_taubin_section(root["taubin"], config.taubin);
    }
    if (root["sdf_reconstruct"]) {
        load_sdf_reconstruct_section(root["sdf_reconstruct"],
                                     config.sdf_reconstruct);
    }
    if (root["cgal_mesh"]) {
        load_cgal_mesh_section(root["cgal_mesh"], config.cgal_mesh);
    }

    read_optional(root, "voxel_spacing_mm", config.voxel_spacing_mm);
    read_optional(root, "restore_physical_coords", config.restore_physical_coords);
    read_optional(root, "mesh_quality_fix", config.mesh_quality_fix);
    read_optional(root, "canonicalize_pose", config.canonicalize_pose);

    return config;
}

// -- Public API: CLI parsing with three-layer merge --------------------------

PipelineConfig load_config(int argc, char** argv) {
    if (argc <= 1) {
        throw_usage_error("Missing required <input.mvr>.");
    }

    PipelineConfig config;

    // Track whether a YAML config was loaded (layer 2).
    bool has_yaml = false;

    // Track legacy mode-boolean flags.
    bool saw_adaptive = false;
    bool saw_uniform = false;
    bool saw_taubin = false;
    bool saw_sdf = false;
    bool saw_cgal = false;
    bool saw_mode = false;

    // Track tuning-flag groups (for orphan-flag validation).
    bool has_sdf_tuning = false;
    bool has_cgal_tuning = false;
    bool has_uniform_tuning = false;
    bool has_taubin_tuning = false;

    bool has_input = false;

    // ---- First pass: find --config and load YAML (layer 2) ----
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if ((arg == "--config" || arg == "-c") && i + 1 < argc) {
            config = load_config_from_yaml(
                std::filesystem::path(argv[i + 1]));
            has_yaml = true;
            break;
        }
    }

    // ---- Second pass: CLI args override YAML (layer 3) ----
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];

        if (arg == "-h" || arg == "--help") {
            throw_usage_error("Help requested.");
        } else if (arg == "--config" || arg == "-c") {
            // Already handled in first pass; skip the value.
            if (i + 1 < argc) ++i;
        } else if (arg == "-o" || arg == "--output") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --output.");
            }
            config.output = std::filesystem::path(argv[++i]);
        } else if (arg == "--mode") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --mode.");
            }
            config.mode = parse_surface_mode(argv[++i]);
            saw_mode = true;
        } else if (arg == "--adaptive-remesh") {
            saw_adaptive = true;
        } else if (arg == "--uniform-subdivide") {
            saw_uniform = true;
        } else if (arg == "--taubin-smooth") {
            saw_taubin = true;
        } else if (arg == "--sdf-reconstruct") {
            saw_sdf = true;
        } else if (arg == "--cgal-mesh") {
            saw_cgal = true;
        } else if (arg == "--adaptive-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --adaptive-iterations.");
            }
            config.adaptive_remesh.iterations =
                parse_int_value(argv[++i], "--adaptive-iterations");
        } else if (arg == "--adaptive-split-ratio") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --adaptive-split-ratio.");
            }
            config.adaptive_remesh.split_ratio =
                parse_double_value(argv[++i], "--adaptive-split-ratio");
        } else if (arg == "--uniform-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --uniform-iterations.");
            }
            config.uniform_subdivide.iterations =
                parse_int_value(argv[++i], "--uniform-iterations");
            has_uniform_tuning = true;
        } else if (arg == "--taubin-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --taubin-iterations.");
            }
            config.taubin.iterations =
                parse_int_value(argv[++i], "--taubin-iterations");
            has_taubin_tuning = true;
        } else if (arg == "--taubin-lambda") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --taubin-lambda.");
            }
            config.taubin.lambda =
                parse_double_value(argv[++i], "--taubin-lambda");
            has_taubin_tuning = true;
        } else if (arg == "--taubin-mu") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --taubin-mu.");
            }
            config.taubin.mu =
                parse_double_value(argv[++i], "--taubin-mu");
            has_taubin_tuning = true;
        } else if (arg == "--sdf-resolution") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --sdf-resolution.");
            }
            config.sdf_reconstruct.resolution =
                parse_int_value(argv[++i], "--sdf-resolution");
            has_sdf_tuning = true;
        } else if (arg == "--sdf-padding-ratio") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --sdf-padding-ratio.");
            }
            config.sdf_reconstruct.padding_ratio =
                parse_double_value(argv[++i], "--sdf-padding-ratio");
            has_sdf_tuning = true;
        } else if (arg == "--sdf-target-edge-length") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --sdf-target-edge-length.");
            }
            config.sdf_reconstruct.target_edge_length =
                parse_double_value(argv[++i], "--sdf-target-edge-length");
            has_sdf_tuning = true;
        } else if (arg == "--sdf-remesh-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --sdf-remesh-iterations.");
            }
            config.sdf_reconstruct.remesh_iterations =
                parse_int_value(argv[++i], "--sdf-remesh-iterations");
            has_sdf_tuning = true;
        } else if (arg == "--sdf-sharp-edge-degrees") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --sdf-sharp-edge-degrees.");
            }
            config.sdf_reconstruct.sharp_edge_dihedral_degrees =
                parse_double_value(argv[++i], "--sdf-sharp-edge-degrees");
            has_sdf_tuning = true;
        } else if (arg == "--sharp-edge-degrees") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --sharp-edge-degrees.");
            }
            config.cgal_mesh.sharp_edge_dihedral_degrees =
                parse_double_value(argv[++i], "--sharp-edge-degrees");
            has_cgal_tuning = true;
        } else if (arg == "--target-edge-length") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --target-edge-length.");
            }
            config.cgal_mesh.target_edge_length =
                parse_double_value(argv[++i], "--target-edge-length");
            has_cgal_tuning = true;
        } else if (arg == "--remesh-iterations") {
            if (i + 1 >= argc) {
                throw_usage_error(
                    "Missing value for --remesh-iterations.");
            }
            config.cgal_mesh.remesh_iterations =
                parse_int_value(argv[++i], "--remesh-iterations");
            has_cgal_tuning = true;
        } else if (arg == "--voxel-spacing-mm") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --voxel-spacing-mm.");
            }
            config.voxel_spacing_mm =
                parse_double_value(argv[++i], "--voxel-spacing-mm");
        } else if (arg == "--restore-physical-coords") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --restore-physical-coords.");
            }
            const std::string val = argv[++i];
            config.restore_physical_coords = (val == "true" || val == "1");
        } else if (arg == "--mesh-quality-fix") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --mesh-quality-fix.");
            }
            const std::string val = argv[++i];
            config.mesh_quality_fix = (val == "true" || val == "1");
        } else if (arg == "--canonicalize-pose") {
            if (i + 1 >= argc) {
                throw_usage_error("Missing value for --canonicalize-pose.");
            }
            const std::string val = argv[++i];
            config.canonicalize_pose = (val == "true" || val == "1");
        } else if (!arg.empty() && arg[0] == '-') {
            throw_usage_error("Unknown option: " + arg);
        } else {
            if (has_input) {
                throw_usage_error(
                    "Only one positional input path is supported.");
            }
            config.input = std::filesystem::path(arg);
            has_input = true;
        }
    }

    // ---- Legacy conflict detection (only for boolean mode flags) ----
    // Skip when --mode or --config was used: the mode is already explicit.
    if (!saw_mode && !has_yaml) {
        if (saw_uniform && saw_adaptive)
            throw std::runtime_error(
                "--uniform-subdivide conflicts with --adaptive-remesh");
        if (saw_uniform && saw_cgal)
            throw std::runtime_error(
                "--uniform-subdivide conflicts with --cgal-mesh");
        if (saw_sdf && saw_adaptive)
            throw std::runtime_error(
                "--sdf-reconstruct conflicts with --adaptive-remesh");
        if (saw_sdf && saw_uniform)
            throw std::runtime_error(
                "--sdf-reconstruct conflicts with --uniform-subdivide");
        if (saw_sdf && saw_cgal)
            throw std::runtime_error(
                "--sdf-reconstruct conflicts with --cgal-mesh");
        if (saw_cgal && saw_adaptive)
            throw std::runtime_error(
                "--cgal-mesh conflicts with --adaptive-remesh");
        if (saw_taubin && !saw_uniform)
            throw std::runtime_error(
                "--taubin-smooth requires --uniform-subdivide");

        // Orphan tuning flag checks.
        if (has_sdf_tuning && !saw_sdf)
            throw std::runtime_error(
                "SDF tuning flags require --sdf-reconstruct");
        if (has_cgal_tuning && !saw_cgal)
            throw std::runtime_error(
                "CGAL tuning flags require --cgal-mesh");
        if (has_uniform_tuning && !saw_uniform)
            throw std::runtime_error(
                "--uniform-iterations requires --uniform-subdivide");
        if (has_taubin_tuning && !saw_taubin && !saw_uniform)
            throw std::runtime_error(
                "Taubin tuning flags require --taubin-smooth");

        // Resolve legacy flags to SurfaceMode.
        if (saw_sdf)
            config.mode = SurfaceMode::SdfReconstruct;
        else if (saw_uniform && saw_taubin)
            config.mode = SurfaceMode::UniformTaubin;
        else if (saw_uniform)
            config.mode = SurfaceMode::UniformSubdivide;
        else if (saw_adaptive)
            config.mode = SurfaceMode::AdaptiveRemesh;
    }
    if (saw_cgal) config.cgal_mesh_post = true;

    // ---- Final validation (layer 4: structural) ----
    config.validate();

    return config;
}

}  // namespace mvrmesh
