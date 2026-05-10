#include <filesystem>
#include <iostream>
#include <stdexcept>

#include "mvrmesh/backends/cgal/cgal_mesh.h"
#include "mvrmesh/cli/cli_common.h"
#include "mvrmesh/config/config_loader.h"
#include "mvrmesh/config/pipeline_config.h"
#include "mvrmesh/core/io.h"
#include "mvrmesh/core/pipeline.h"
#include "mvrmesh/core/types.h"

int main(int argc, char** argv) {
    try {
        const auto config = mvrmesh::load_config(argc, argv);
        const auto in_path = mvrmesh::resolve_input(config, argv[0]);
        const auto out_paths =
            mvrmesh::resolve_outputs(config, in_path, argv[0]);

        const mvrmesh::ParsedMvr parsed = mvrmesh::parse_mvr(in_path);
        mvrmesh::log_source_info(parsed);

        mvrmesh::BuildResult result = mvrmesh::build_surface(parsed, config);
        mvrmesh::log_build_result(result);

        if (config.cgal_mesh_post) {
            auto robust = mvrmesh::run_cgal_mesh(
                result.vertices, result.faces, config.cgal_mesh);
            result.vertices = std::move(robust.vertices);
            result.faces = std::move(robust.faces);
            std::cout << "[info] cgal_mesh post-step: vertices="
                      << result.vertices.size()
                      << ", faces=" << result.faces.size() << "\n";
        }

        mvrmesh::write_outputs(result, out_paths);
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }
    return 0;
}
