#include "mvrmesh/core/pipeline.h"

#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mvrmesh/core/subdivision.h"
#include "mvrmesh/core/reconstruction_pipeline.h"
#include "mvrmesh/core/smoothing.h"
#include "mvrmesh/core/topology.h"

namespace mvrmesh {

BuildResult build_surface(
    const ParsedMvr& parsed,
    const PipelineConfig& config
) {
    std::vector<Face> base_faces;
    if (!parsed.triangles.empty()) {
        base_faces = parsed.triangles;
    } else if (!parsed.tetrahedra.empty()) {
        base_faces = boundary_faces_from_tets(parsed.vertices, parsed.tetrahedra);
    } else {
        throw std::runtime_error("No triangles in @3 and no tetrahedra in @4.");
    }

    switch (config.mode) {
    case SurfaceMode::AdaptiveRemesh: {
        auto remeshed = adaptive_remesh(
            parsed.vertices, base_faces,
            config.adaptive_remesh.iterations,
            config.adaptive_remesh.split_ratio);
        return BuildResult{
            std::move(remeshed.first),
            std::move(remeshed.second),
            SurfaceMode::AdaptiveRemesh};
    }
    case SurfaceMode::UniformSubdivide: {
        auto subdivided = uniform_subdivide(
            parsed.vertices, base_faces,
            config.uniform_subdivide.iterations);
        return BuildResult{
            std::move(subdivided.first),
            std::move(subdivided.second),
            SurfaceMode::UniformSubdivide};
    }
    case SurfaceMode::UniformTaubin: {
        auto subdivided = uniform_subdivide(
            parsed.vertices, base_faces,
            config.uniform_subdivide.iterations);
        auto smoothed = taubin_smooth(
            subdivided.first, subdivided.second,
            config.taubin.iterations,
            config.taubin.lambda,
            config.taubin.mu,
            config.taubin.preserve_boundary);
        return BuildResult{
            std::move(smoothed),
            std::move(subdivided.second),
            SurfaceMode::UniformTaubin};
    }
    case SurfaceMode::SdfReconstruct: {
        SdfRemeshOptions sdf_opts;
        sdf_opts.sdf_resolution = config.sdf_reconstruct.resolution;
        sdf_opts.padding_ratio = config.sdf_reconstruct.padding_ratio;
        sdf_opts.sharp_edge_dihedral_degrees = config.sdf_reconstruct.sharp_edge_dihedral_degrees;
        sdf_opts.target_edge_length = config.sdf_reconstruct.target_edge_length;
        sdf_opts.remesh_iterations = config.sdf_reconstruct.remesh_iterations;
        auto remeshed = reconstruct_and_remesh_surface(
            parsed.vertices, base_faces, sdf_opts);
        return BuildResult{
            std::move(remeshed.vertices),
            std::move(remeshed.faces),
            SurfaceMode::SdfReconstruct};
    }
    case SurfaceMode::DirectSurface:
    default:
        return BuildResult{
            parsed.vertices,
            std::move(base_faces),
            SurfaceMode::DirectSurface};
    }
}

std::vector<std::filesystem::path> outputs_for_mode(
    const std::filesystem::path& base_output
) {
    std::filesystem::path p = base_output;
    p.replace_extension(".ply");
    return { std::move(p) };
}

}  // namespace mvrmesh
