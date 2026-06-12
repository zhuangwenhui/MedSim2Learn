// Tests for config validation and surface-mode parsing in mvrmesh/config/pipeline_config.h.

#include <iostream>
#include <stdexcept>
#include <string>

#include "test_helpers.h"

#include "mvrmesh/config/pipeline_config.h"

namespace {

using mvrmesh::test::require;

void require_throws(auto fn, const char* substr, const char* test_name) {
    bool threw = false;
    try {
        fn();
    } catch (const std::runtime_error& ex) {
        threw = std::string(ex.what()).find(substr) != std::string::npos;
    }
    if (!threw) {
        throw std::runtime_error(
            std::string("Expected exception containing '") + substr
            + "' in test: " + test_name);
    }
}

// -- Test cases ---------------------------------------------------------------

void test_default_config_validates() {
    mvrmesh::PipelineConfig cfg;
    cfg.input = "dummy.mvr";
    cfg.validate();  // must not throw
}

void test_validate_rejects_empty_input() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.validate();
        },
        "input",
        "test_validate_rejects_empty_input");
}

void test_validate_rejects_zero_uniform_iterations() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.input = "dummy.mvr";
            cfg.mode = mvrmesh::SurfaceMode::UniformSubdivide;
            cfg.uniform_subdivide.iterations = 0;
            cfg.validate();
        },
        "iterations",
        "test_validate_rejects_zero_uniform_iterations");
}

void test_validate_rejects_sdf_with_cgal_post() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.input = "dummy.mvr";
            cfg.mode = mvrmesh::SurfaceMode::SdfReconstruct;
            cfg.cgal_mesh_post = true;
            cfg.validate();
        },
        "conflicts",
        "test_validate_rejects_sdf_with_cgal_post");
}

void test_validate_adaptive_split_ratio_above_1() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.input = "dummy.mvr";
            cfg.mode = mvrmesh::SurfaceMode::AdaptiveRemesh;
            cfg.adaptive_remesh.split_ratio = 1.5;
            cfg.validate();
        },
        "split_ratio",
        "test_validate_adaptive_split_ratio_above_1");
}

void test_validate_adaptive_split_ratio_zero() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.input = "dummy.mvr";
            cfg.mode = mvrmesh::SurfaceMode::AdaptiveRemesh;
            cfg.adaptive_remesh.split_ratio = 0.0;
            cfg.validate();
        },
        "split_ratio",
        "test_validate_adaptive_split_ratio_zero");
}

void test_parse_surface_mode_roundtrip() {
    using mvrmesh::SurfaceMode;
    const SurfaceMode modes[] = {
        SurfaceMode::DirectSurface,
        SurfaceMode::AdaptiveRemesh,
        SurfaceMode::UniformSubdivide,
        SurfaceMode::UniformTaubin,
        SurfaceMode::SdfReconstruct
    };
    for (auto m : modes) {
        const std::string name = mvrmesh::surface_mode_name(m);
        const SurfaceMode parsed = mvrmesh::parse_surface_mode(name);
        require(parsed == m,
                "round-trip failed for a SurfaceMode value");
    }
}

void test_parse_surface_mode_rejects_unknown() {
    require_throws(
        [] { mvrmesh::parse_surface_mode("bogus_mode"); },
        "Unknown",
        "test_parse_surface_mode_rejects_unknown");
}

void test_validate_sdf_resolution_too_high() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.input = "dummy.mvr";
            cfg.mode = mvrmesh::SurfaceMode::SdfReconstruct;
            cfg.sdf_reconstruct.resolution = 200;
            cfg.validate();
        },
        "resolution",
        "test_validate_sdf_resolution_too_high");
}

void test_validate_cgal_post_bad_angle() {
    require_throws(
        [] {
            mvrmesh::PipelineConfig cfg;
            cfg.input = "dummy.mvr";
            cfg.mode = mvrmesh::SurfaceMode::DirectSurface;
            cfg.cgal_mesh_post = true;
            cfg.cgal_mesh.sharp_edge_dihedral_degrees = 0.0;
            cfg.validate();
        },
        "sharp_edge_dihedral_degrees",
        "test_validate_cgal_post_bad_angle");
}

}  // namespace

int main() {
    return mvrmesh::test::run_tests({
        {test_default_config_validates,
         "test_default_config_validates"},
        {test_validate_rejects_empty_input,
         "test_validate_rejects_empty_input"},
        {test_validate_rejects_zero_uniform_iterations,
         "test_validate_rejects_zero_uniform_iterations"},
        {test_validate_rejects_sdf_with_cgal_post,
         "test_validate_rejects_sdf_with_cgal_post"},
        {test_validate_adaptive_split_ratio_above_1,
         "test_validate_adaptive_split_ratio_above_1"},
        {test_validate_adaptive_split_ratio_zero,
         "test_validate_adaptive_split_ratio_zero"},
        {test_parse_surface_mode_roundtrip,
         "test_parse_surface_mode_roundtrip"},
        {test_parse_surface_mode_rejects_unknown,
         "test_parse_surface_mode_rejects_unknown"},
        {test_validate_sdf_resolution_too_high,
         "test_validate_sdf_resolution_too_high"},
        {test_validate_cgal_post_bad_angle,
         "test_validate_cgal_post_bad_angle"},
    });
}
