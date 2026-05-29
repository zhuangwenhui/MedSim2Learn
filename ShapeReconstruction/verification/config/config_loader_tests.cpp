// verification/config/config_loader_tests.cpp

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "test_helpers.h"

#include "mvrmesh/config/config_loader.h"

namespace {

#ifndef MVRMESH_FIXTURE_DIR
#error "MVRMESH_FIXTURE_DIR must be defined by CMake"
#endif
#ifndef MVRMESH_CONFIGS_DIR
#error "MVRMESH_CONFIGS_DIR must be defined by CMake"
#endif

const std::filesystem::path kFixtureDir = MVRMESH_FIXTURE_DIR;
const std::filesystem::path kConfigsDir = MVRMESH_CONFIGS_DIR;

using mvrmesh::test::require;

// -- YAML tests --------------------------------------------------------------

void test_load_yaml_uniform_taubin() {
    const auto cfg = mvrmesh::load_config_from_yaml(
        kConfigsDir / "uniform_taubin.yaml");

    require(cfg.mode == mvrmesh::SurfaceMode::UniformTaubin,
            "mode should be UniformTaubin");
    require(cfg.uniform_subdivide.iterations == 2,
            "uniform_subdivide.iterations should be 2");
    require(cfg.taubin.iterations == 8,
            "taubin.iterations should be 8");
    require(cfg.taubin.lambda == 0.5,
            "taubin.lambda should be 0.5");
    require(cfg.taubin.mu == -0.53,
            "taubin.mu should be -0.53");
}

void test_load_yaml_sdf() {
    const auto cfg = mvrmesh::load_config_from_yaml(
        kConfigsDir / "sdf_reconstruct.yaml");

    require(cfg.mode == mvrmesh::SurfaceMode::SdfReconstruct,
            "mode should be SdfReconstruct");
    require(cfg.sdf_reconstruct.resolution == 72,
            "sdf_reconstruct.resolution should be 72");
    require(cfg.sdf_reconstruct.target_edge_length == 0.025,
            "sdf_reconstruct.target_edge_length should be 0.025");
    require(cfg.sdf_reconstruct.remesh_iterations == 3,
            "sdf_reconstruct.remesh_iterations should be 3");
}

// -- CLI tests ----------------------------------------------------------------

void test_cli_args_basic() {
    std::vector<std::string> args_str = {
        "mvr_to_mesh_cli", "test.mvr",
        "--mode", "uniform_subdivide",
        "--uniform-iterations", "3",
        "-o", "out.ply"
    };
    std::vector<char*> argv;
    for (auto& s : args_str) argv.push_back(s.data());

    auto cfg = mvrmesh::load_config(
        static_cast<int>(argv.size()), argv.data());

    require(cfg.mode == mvrmesh::SurfaceMode::UniformSubdivide,
            "mode should be UniformSubdivide");
    require(cfg.uniform_subdivide.iterations == 3,
            "uniform_subdivide.iterations should be 3");
    require(cfg.output == std::filesystem::path("out.ply"),
            "output should be out.ply");
    require(cfg.input == std::filesystem::path("test.mvr"),
            "input should be test.mvr");
}

void test_cli_legacy_flags() {
    std::vector<std::string> args_str = {
        "mvr_to_mesh_cli", "test.mvr",
        "--uniform-subdivide", "--taubin-smooth"
    };
    std::vector<char*> argv;
    for (auto& s : args_str) argv.push_back(s.data());

    auto cfg = mvrmesh::load_config(
        static_cast<int>(argv.size()), argv.data());

    require(cfg.mode == mvrmesh::SurfaceMode::UniformTaubin,
            "mode should be UniformTaubin from legacy flags");
}

void test_cli_overrides_yaml() {
    // Build a --config path pointing to the test fixture.
    const std::string yaml_path =
        (kConfigsDir / "uniform_taubin.yaml").string();

    std::vector<std::string> args_str = {
        "mvr_to_mesh_cli", "test.mvr",
        "--config", yaml_path,
        "--taubin-iterations", "16"
    };
    std::vector<char*> argv;
    for (auto& s : args_str) argv.push_back(s.data());

    auto cfg = mvrmesh::load_config(
        static_cast<int>(argv.size()), argv.data());

    // Mode preserved from YAML.
    require(cfg.mode == mvrmesh::SurfaceMode::UniformTaubin,
            "mode should be preserved from YAML as UniformTaubin");
    // CLI override wins.
    require(cfg.taubin.iterations == 16,
            "taubin.iterations should be overridden to 16 by CLI");
    // Other YAML values preserved.
    require(cfg.uniform_subdivide.iterations == 2,
            "uniform_subdivide.iterations should be preserved from YAML");
}

void test_load_yaml_postprocess_defaults() {
    const auto cfg = mvrmesh::load_config_from_yaml(
        kConfigsDir / "uniform_taubin.yaml");

    require(cfg.voxel_spacing_mm == 1.0,
            "voxel_spacing_mm default should be 1.0");
    require(cfg.restore_physical_coords == true,
            "restore_physical_coords default should be true");
    require(cfg.mesh_quality_fix == true,
            "mesh_quality_fix default should be true");
}

void test_cli_postprocess_flags() {
    std::vector<std::string> args_str = {
        "mvr_to_mesh_cli", "test.mvr",
        "--voxel-spacing-mm", "0.35",
        "--restore-physical-coords", "false",
        "--mesh-quality-fix", "false"
    };
    std::vector<char*> argv;
    for (auto& s : args_str) argv.push_back(s.data());

    auto cfg = mvrmesh::load_config(
        static_cast<int>(argv.size()), argv.data());

    require(cfg.voxel_spacing_mm == 0.35,
            "voxel_spacing_mm should be 0.35 from CLI");
    require(cfg.restore_physical_coords == false,
            "restore_physical_coords should be false from CLI");
    require(cfg.mesh_quality_fix == false,
            "mesh_quality_fix should be false from CLI");
}

void test_canonicalize_pose_from_cli() {
    std::vector<std::string> args_str = {
        "mvr_to_mesh_cli", "test.mvr",
        "--canonicalize-pose", "true"
    };
    std::vector<char*> argv;
    for (auto& s : args_str) argv.push_back(s.data());

    auto cfg = mvrmesh::load_config(
        static_cast<int>(argv.size()), argv.data());

    require(cfg.canonicalize_pose == true,
            "canonicalize_pose should be true from CLI");
}

}  // namespace

int main() {
    return mvrmesh::test::run_tests({
        {test_load_yaml_uniform_taubin, "test_load_yaml_uniform_taubin"},
        {test_load_yaml_sdf,            "test_load_yaml_sdf"},
        {test_cli_args_basic,           "test_cli_args_basic"},
        {test_cli_legacy_flags,         "test_cli_legacy_flags"},
        {test_cli_overrides_yaml,       "test_cli_overrides_yaml"},
        {test_load_yaml_postprocess_defaults, "test_load_yaml_postprocess_defaults"},
        {test_cli_postprocess_flags,          "test_cli_postprocess_flags"},
        {test_canonicalize_pose_from_cli,     "test_canonicalize_pose_from_cli"},
    });
}
