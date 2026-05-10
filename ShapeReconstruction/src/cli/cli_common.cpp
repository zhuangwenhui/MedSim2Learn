// src/cli/cli_common.cpp

#include "mvrmesh/cli/cli_common.h"

#include <iostream>
#include <stdexcept>
#include <string>

#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/io.h"
#include "mvrmesh/core/pipeline.h"
#include "mvrmesh/core/types.h"

namespace {

std::string to_lower_ascii(std::string text) {
    for (char& ch : text) {
        if (ch >= 'A' && ch <= 'Z') {
            ch = static_cast<char>(ch - 'A' + 'a');
        }
    }
    return text;
}

std::filesystem::path infer_project_root_from_input(
    const std::filesystem::path& in_path) {
    const std::filesystem::path parent = in_path.parent_path();
    if (parent.empty()) {
        return in_path.parent_path();
    }

    const std::string parent_name = to_lower_ascii(parent.filename().string());
    const std::filesystem::path grandparent = parent.parent_path();
    const std::string grandparent_name =
        to_lower_ascii(grandparent.filename().string());

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

std::filesystem::path resolve_input_path(
    const std::filesystem::path& input,
    const std::filesystem::path& project_root) {
    if (input.is_absolute()) {
        return input;
    }

    std::error_code ec;
    const std::filesystem::path cwd_candidate =
        std::filesystem::absolute(input, ec);
    if (!ec && std::filesystem::exists(cwd_candidate)) {
        return cwd_candidate;
    }

    if (!project_root.empty()) {
        const std::filesystem::path project_candidate = project_root / input;
        if (std::filesystem::exists(project_candidate)) {
            return project_candidate;
        }

        const std::filesystem::path original_data_candidate =
            project_root / "originalData" / input;
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
    const std::filesystem::path& project_root) {
    const std::filesystem::path root =
        project_root.empty() ? infer_project_root_from_input(in_path)
                             : project_root;
    const std::string stem = in_path.stem().string();
    return {root / "outPut" / "PLY" / (stem + ".ply")};
}

}  // namespace

namespace mvrmesh {

std::filesystem::path find_project_root(const char* argv0) {
    std::filesystem::path root =
        find_project_root_upward(std::filesystem::current_path());
    if (!root.empty()) {
        return root;
    }

    root = find_project_root_upward(std::filesystem::path(argv0));
    if (!root.empty()) {
        return root;
    }

    return {};
}

std::filesystem::path resolve_input(const PipelineConfig& config,
                                    const char* argv0) {
    const std::filesystem::path project_root = find_project_root(argv0);
    const std::filesystem::path in_path =
        resolve_input_path(config.input, project_root);
    if (!std::filesystem::exists(in_path)) {
        throw std::runtime_error("Input file not found: " + in_path.string());
    }
    return in_path;
}

std::vector<std::filesystem::path> resolve_outputs(
    const PipelineConfig& config,
    const std::filesystem::path& resolved_input,
    const char* argv0) {
    if (!config.output.empty()) {
        return outputs_for_mode(std::filesystem::absolute(config.output));
    }
    const std::filesystem::path project_root = find_project_root(argv0);
    return default_outputs_for_input(resolved_input, project_root);
}

void ensure_parent_dir(const std::filesystem::path& path) {
    const std::filesystem::path dir = path.parent_path();
    if (dir.empty()) {
        return;
    }

    std::error_code ec;
    std::filesystem::create_directories(dir, ec);
    if (ec) {
        throw std::runtime_error("Failed to create output directory: " +
                                 dir.string() +
                                 ", reason: " + ec.message());
    }
}

void write_outputs(const BuildResult& result,
                   const std::vector<std::filesystem::path>& out_paths) {
    for (const auto& out_path : out_paths) {
        ensure_parent_dir(out_path);
        const std::string ext = out_path.extension().string();
        if (ext != ".ply" && ext != ".PLY") {
            throw std::runtime_error("Unsupported output extension: " + ext);
        }
        write_ply(out_path, result.vertices, result.faces);
        std::cout << "[ok] wrote " << out_path.string() << "\n";
    }
}

void log_source_info(const ParsedMvr& parsed) {
    std::cout << "[info] source: vertices=" << parsed.vertices.size()
              << ", triangles=" << parsed.triangles.size()
              << ", tetrahedra=" << parsed.tetrahedra.size() << "\n";
}

void log_build_result(const BuildResult& result) {
    std::cout << "[info] mode=" << surface_mode_name(result.mode)
              << ", output vertices=" << result.vertices.size()
              << ", faces=" << result.faces.size() << "\n";
}

}  // namespace mvrmesh
