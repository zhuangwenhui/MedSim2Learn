// src/config/pressure_config.cpp

#include "mvrmesh/config/pressure_config.h"

#include <iostream>
#include <stdexcept>
#include <string>

namespace {

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

}  // namespace

namespace mvrmesh {

void PressureConfig::validate() const {
    if (n_samples == 0) {
        throw std::runtime_error("n_samples must be > 0");
    }
    if (matrix_mode) {
        if (inputs.empty()) {
            throw std::runtime_error(
                "--matrix requires at least one .ply input");
        }
        if (output.empty()) {
            throw std::runtime_error("output path must not be empty");
        }
    } else {
        if (input.empty()) {
            throw std::runtime_error("input path must not be empty");
        }
        if (output.empty()) {
            throw std::runtime_error("output path must not be empty");
        }
    }
}

PressureConfig load_pressure_config(int argc, char** argv) {
    PressureConfig config;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "-o") {
            if (i + 1 >= argc) { usage(argv[0]); throw std::runtime_error("-o requires a value"); }
            config.output = argv[++i];
        } else if (arg == "--matrix") {
            config.matrix_mode = true;
            while (i + 1 < argc && argv[i + 1][0] != '-') {
                config.inputs.push_back(argv[++i]);
            }
        } else if (arg == "--n-samples") {
            if (i + 1 >= argc) { usage(argv[0]); throw std::runtime_error("--n-samples requires a value"); }
            config.n_samples = std::stoull(argv[++i]);
        } else if (arg == "--switches") {
            if (i + 1 >= argc) { usage(argv[0]); throw std::runtime_error("--switches requires a value"); }
            config.switches = argv[++i];
        } else if (arg == "--baseline") {
            if (i + 1 >= argc) { usage(argv[0]); throw std::runtime_error("--baseline requires a value"); }
            config.baseline = argv[++i];
        } else if (arg == "--label") {
            if (i + 1 >= argc) { usage(argv[0]); throw std::runtime_error("--label requires a value"); }
            std::string spec = argv[++i];
            auto eq = spec.find('=');
            if (eq == std::string::npos) {
                throw std::runtime_error(
                    "--label expects PATH=NAME, got: " + spec);
            }
            config.labels.emplace_back(spec.substr(0, eq), spec.substr(eq + 1));
        } else if (arg == "--help" || arg == "-h") {
            usage(argv[0]);
            throw std::runtime_error("help requested");
        } else if (!arg.empty() && arg[0] != '-' && !config.matrix_mode) {
            config.input = arg;
        } else {
            std::cerr << "[error] unexpected arg: " << arg << "\n";
            usage(argv[0]);
            throw std::runtime_error("unexpected argument: " + arg);
        }
    }

    config.validate();
    return config;
}

}  // namespace mvrmesh
