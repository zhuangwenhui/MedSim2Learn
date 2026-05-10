#include <iostream>
#include <stdexcept>

#include "mvrmesh/config/pressure_config.h"
#include "mvrmesh/pressure/pressure_metrics.h"

int main(int argc, char** argv) {
    try {
        const auto config = mvrmesh::load_pressure_config(argc, argv);
        if (config.matrix_mode) {
            return mvrmesh::run_pressure_matrix(config);
        }
        return mvrmesh::run_pressure_single(config);
    } catch (const std::exception& ex) {
        std::cerr << "[error] " << ex.what() << "\n";
        return 1;
    }
}
