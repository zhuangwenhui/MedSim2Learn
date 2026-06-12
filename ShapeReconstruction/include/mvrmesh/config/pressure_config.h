#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <utility>
#include <vector>

namespace mvrmesh {

// Settings for check_fem_pressure_cli: evaluate FEM pressure metrics on one
// .ply surface mesh (single mode, JSON output) or compare several meshes side
// by side (matrix mode, Markdown output).
struct PressureConfig {
    bool matrix_mode = false;

    // single mode
    std::filesystem::path input;
    std::filesystem::path output;

    // matrix mode
    std::vector<std::filesystem::path> inputs;
    std::filesystem::path baseline;
    // Friendly display names per input, from repeatable --label PATH=NAME.
    std::vector<std::pair<std::filesystem::path, std::string>> labels;

    // shared
    std::size_t n_samples = 22500;  // DeformSim sample count, must be > 0
    std::string switches = "pYQ";  // TetGen command-line switches

    // Throws std::runtime_error when n_samples is 0 or the input/output
    // paths required by the selected mode are missing.
    void validate() const;
};

// Parses argv into a PressureConfig and validates it. On bad arguments or
// -h/--help, prints usage to stderr and throws std::runtime_error.
PressureConfig load_pressure_config(int argc, char** argv);

}  // namespace mvrmesh
