// include/mvrmesh/config/pressure_config.h
#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <utility>
#include <vector>

namespace mvrmesh {

struct PressureConfig {
    bool matrix_mode = false;

    // single mode
    std::filesystem::path input;
    std::filesystem::path output;

    // matrix mode
    std::vector<std::filesystem::path> inputs;
    std::filesystem::path baseline;
    std::vector<std::pair<std::filesystem::path, std::string>> labels;

    // shared
    std::size_t n_samples = 22500;
    std::string switches = "pYQ";

    void validate() const;
};

PressureConfig load_pressure_config(int argc, char** argv);

}  // namespace mvrmesh
