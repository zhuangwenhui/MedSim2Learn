#include "mvrmesh/backends/cgal/cgal_robust_pipeline.h"

#if MVRMESH_CGAL_PMP_ENABLED

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <CGAL/Polygon_mesh_processing/detect_features.h>
#include <CGAL/Polygon_mesh_processing/measure.h>
#include <CGAL/Polygon_mesh_processing/orient_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/remesh.h>
#include <CGAL/Polygon_mesh_processing/repair_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/triangulate_hole.h>
#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Surface_mesh_simplification/edge_collapse.h>
#include <CGAL/Surface_mesh_simplification/Policies/Edge_collapse/Bounded_normal_change_filter.h>
#include <CGAL/Surface_mesh_simplification/Policies/Edge_collapse/Edge_count_stop_predicate.h>
#include <CGAL/Surface_mesh_simplification/Policies/Edge_collapse/LindstromTurk_cost.h>
#include <CGAL/Surface_mesh_simplification/Policies/Edge_collapse/LindstromTurk_placement.h>
// Note: GarlandHeckbert_plane_policies requires Eigen3, which is not installed in this
// vcpkg environment. LindstromTurk (also QEM-based) is used as a drop-in substitute
// until Eigen3 is added to vcpkg dependencies.

namespace mvrmesh {

namespace {

using CgalKernel       = CGAL::Simple_cartesian<double>;
using CgalPoint        = CgalKernel::Point_3;
using CgalSurfaceMesh  = CGAL::Surface_mesh<CgalPoint>;
using CgalVertexIndex  = CgalSurfaceMesh::Vertex_index;
using CgalFaceIndex    = CgalSurfaceMesh::Face_index;
using CgalHalfedgeIndex = CgalSurfaceMesh::Halfedge_index;
namespace PMP = CGAL::Polygon_mesh_processing;

void preflight_repair_input(const std::vector<Vec3>& vertices, const std::vector<Face>& faces) {
    if (vertices.size() < 3) {
        std::ostringstream oss;
        oss << "step 1: at least 3 vertices required, got " << vertices.size();
        throw std::runtime_error(oss.str());
    }
    const int upper = static_cast<int>(vertices.size());
    for (const Face& f : faces) {
        for (int idx : f) {
            if (idx < 0 || idx >= upper) {
                std::ostringstream oss;
                oss << "step 1: face index " << idx << " out of range [0, " << upper << ")";
                throw std::runtime_error(oss.str());
            }
        }
    }
}

void mvrmesh_to_polygon_soup(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::vector<CgalPoint>& points_out,
    std::vector<std::vector<std::size_t>>& polygons_out) {
    points_out.clear();
    points_out.reserve(vertices.size());
    for (const Vec3& v : vertices) {
        points_out.emplace_back(v.x, v.y, v.z);
    }
    polygons_out.clear();
    polygons_out.reserve(faces.size());
    for (const Face& f : faces) {
        polygons_out.push_back({static_cast<std::size_t>(f[0]),
                                static_cast<std::size_t>(f[1]),
                                static_cast<std::size_t>(f[2])});
    }
}

std::size_t triangulate_all_holes(CgalSurfaceMesh& mesh) {
    std::set<CgalHalfedgeIndex> visited;
    std::size_t holes_filled = 0;
    for (CgalHalfedgeIndex h : mesh.halfedges()) {
        if (!mesh.is_border(h) || visited.count(h) > 0) {
            continue;
        }
        // Mark every halfedge on this hole boundary as visited
        CgalHalfedgeIndex current = h;
        do {
            visited.insert(current);
            current = mesh.next(current);
        } while (current != h);

        std::vector<CgalFaceIndex> patch;
        PMP::triangulate_hole(mesh, h, std::back_inserter(patch));
        if (patch.empty()) {
            std::ostringstream oss;
            oss << "step 1 (repair): hole at halfedge " << h
                << " cannot be triangulated (non-manifold border or self-intersecting boundary).";
            throw std::runtime_error(oss.str());
        }
        ++holes_filled;
    }
    return holes_filled;
}

void mvrmesh_to_surface_mesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    CgalSurfaceMesh& mesh_out) {
    mesh_out.clear();
    std::vector<CgalVertexIndex> vmap;
    vmap.reserve(vertices.size());
    for (const Vec3& v : vertices) {
        vmap.push_back(mesh_out.add_vertex(CgalPoint(v.x, v.y, v.z)));
    }
    for (const Face& f : faces) {
        const CgalFaceIndex fd = mesh_out.add_face(
            vmap[static_cast<std::size_t>(f[0])],
            vmap[static_cast<std::size_t>(f[1])],
            vmap[static_cast<std::size_t>(f[2])]);
        if (fd == CgalSurfaceMesh::null_face()) {
            std::ostringstream oss;
            oss << "step 2 (remesh): could not add face (" << f[0] << "," << f[1] << "," << f[2]
                << ") to Surface_mesh";
            throw std::runtime_error(oss.str());
        }
    }
}

void surface_mesh_to_mvrmesh(
    CgalSurfaceMesh& mesh,
    std::vector<Vec3>& vertices_out,
    std::vector<Face>& faces_out) {
    vertices_out.clear();
    faces_out.clear();
    auto vid_map = mesh.add_property_map<CgalVertexIndex, int>("v:tmp_id", -1).first;
    int next = 0;
    for (CgalVertexIndex vd : mesh.vertices()) {
        const CgalPoint& p = mesh.point(vd);
        vertices_out.push_back(Vec3{p.x(), p.y(), p.z()});
        vid_map[vd] = next++;
    }
    for (CgalFaceIndex fd : mesh.faces()) {
        Face f{0, 0, 0};
        int slot = 0;
        for (CgalVertexIndex vd : CGAL::vertices_around_face(mesh.halfedge(fd), mesh)) {
            if (slot >= 3) {
                throw std::runtime_error(
                    "surface_mesh_to_mvrmesh: non-triangular face encountered");
            }
            f[slot++] = vid_map[vd];
        }
        faces_out.push_back(f);
    }
    mesh.remove_property_map(vid_map);
}

double mean_edge_length(const CgalSurfaceMesh& mesh) {
    if (mesh.number_of_edges() == 0) {
        return 0.0;
    }
    double total = 0.0;
    for (auto e : mesh.edges()) {
        total += PMP::edge_length(mesh.halfedge(e), mesh);
    }
    return total / static_cast<double>(mesh.number_of_edges());
}

void log_repair(const RepairStepReport& r) {
    std::cout << "[info] robust pipeline step 1 (repair): "
              << "in_v="    << r.input_vertex_count
              << " in_f="   << r.input_face_count
              << " out_v="  << r.output_vertex_count
              << " out_f="  << r.output_face_count
              << " dups="   << r.removed_duplicate_vertices
              << " degen="  << r.removed_degenerate_faces
              << " holes="  << r.holes_filled << "\n";
}

void log_remesh(const ProtectedRemeshStepReport& r) {
    std::cout << "[info] robust pipeline step 2 (remesh): "
              << "in_v="           << r.input_vertex_count
              << " in_f="          << r.input_face_count
              << " out_v="         << r.output_vertex_count
              << " out_f="         << r.output_face_count
              << " sharp_edges="   << r.sharp_edges_detected
              << " target_edge="   << r.target_edge_length_used
              << " iters="         << r.remesh_iterations_used << "\n";
}

void log_simplify(const SimplifyToBudgetStepReport& r) {
    if (r.skipped_within_budget) {
        std::cout << "[info] robust pipeline step 3 (simplify): "
                  << "skipped (within_budget): bytes=" << r.bytes_initial
                  << " budget=" << r.budget_bytes << "\n";
        return;
    }
    std::cout << "[info] robust pipeline step 3 (simplify): "
              << "in_v="     << r.input_vertex_count
              << " in_f="    << r.input_face_count
              << " out_v="   << r.output_vertex_count
              << " out_f="   << r.output_face_count
              << " budget="  << r.budget_bytes
              << " init="    << r.bytes_initial
              << " final="   << r.bytes_final
              << " target_v=" << r.target_vertex_count << "\n";
}

}  // namespace

namespace detail {

RepairStepIO repair_polygon_soup_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces) {
    preflight_repair_input(vertices, faces);

    RepairStepIO io;
    io.report.input_vertex_count = vertices.size();
    io.report.input_face_count   = faces.size();

    std::vector<CgalPoint> points;
    std::vector<std::vector<std::size_t>> polygons;
    mvrmesh_to_polygon_soup(vertices, faces, points, polygons);

    const std::size_t before_points   = points.size();
    const std::size_t before_polygons = polygons.size();
    PMP::repair_polygon_soup(points, polygons);
    if (polygons.empty()) {
        throw std::runtime_error(
            "step 1 (repair): all input polygons were degenerate or duplicate; "
            "nothing remains after repair. Verify input .mvr is not corrupt.");
    }

    io.report.removed_duplicate_vertices = (before_points > points.size())
                                               ? before_points - points.size()
                                               : 0;
    io.report.removed_degenerate_faces   = (before_polygons > polygons.size())
                                               ? before_polygons - polygons.size()
                                               : 0;

    const bool oriented = PMP::orient_polygon_soup(points, polygons);
    io.report.oriented_successfully = oriented;
    if (!oriented) {
        throw std::runtime_error(
            "step 1 (repair): input cannot be oriented (Mobius-strip-like topology or "
            "self-intersection density too high). Consider externally repairing the input "
            "before --robust-pipeline.");
    }

    CgalSurfaceMesh mesh;
    PMP::polygon_soup_to_polygon_mesh(points, polygons, mesh);
    if (mesh.number_of_vertices() == 0) {
        throw std::runtime_error(
            "step 1 (repair): polygon soup could not be assembled into a valid surface mesh.");
    }

    io.report.holes_filled = triangulate_all_holes(mesh);

    // Convert back to mvrmesh containers. The "v:mvrmesh_index" property map below
    // does not need an explicit remove_property_map call because `mesh` is a local
    // variable destroyed when this function returns. Helpers like
    // surface_mesh_to_mvrmesh that operate on caller-owned meshes do explicit
    // cleanup; the asymmetry is intentional.
    io.vertices.reserve(mesh.number_of_vertices());
    auto v_index_map = mesh.add_property_map<CgalVertexIndex, int>("v:mvrmesh_index", -1).first;
    int next_vid = 0;
    for (CgalVertexIndex vd : mesh.vertices()) {
        const CgalPoint& p = mesh.point(vd);
        io.vertices.push_back(Vec3{p.x(), p.y(), p.z()});
        v_index_map[vd] = next_vid++;
    }
    io.faces.reserve(mesh.number_of_faces());
    for (CgalFaceIndex fd : mesh.faces()) {
        Face f{0, 0, 0};
        int slot = 0;
        for (CgalVertexIndex vd : CGAL::vertices_around_face(mesh.halfedge(fd), mesh)) {
            if (slot >= 3) {
                throw std::runtime_error(
                    "step 1 (repair): non-triangular face emitted by polygon_soup_to_polygon_mesh");
            }
            f[slot++] = v_index_map[vd];
        }
        if (slot != 3) {
            throw std::runtime_error(
                "step 1 (repair): degenerate face emitted by polygon_soup_to_polygon_mesh");
        }
        io.faces.push_back(f);
    }

    io.report.output_vertex_count = io.vertices.size();
    io.report.output_face_count   = io.faces.size();
    return io;
}

ProtectedRemeshStepIO protected_remesh_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double sharp_edge_dihedral_degrees,
    double target_edge_length,
    int    remesh_iterations) {
    if (sharp_edge_dihedral_degrees <= 0.0 || sharp_edge_dihedral_degrees >= 180.0) {
        std::ostringstream oss;
        oss << "step 2 (remesh): sharp_edge_dihedral_degrees out of range (0, 180); got "
            << sharp_edge_dihedral_degrees;
        throw std::runtime_error(oss.str());
    }
    if (remesh_iterations < 1) {
        throw std::runtime_error("step 2 (remesh): remesh_iterations must be >= 1");
    }
    if (target_edge_length < 0.0) {
        throw std::runtime_error("step 2 (remesh): target_edge_length must be >= 0");
    }

    ProtectedRemeshStepIO io;
    io.report.input_vertex_count = vertices.size();
    io.report.input_face_count   = faces.size();

    CgalSurfaceMesh mesh;
    mvrmesh_to_surface_mesh(vertices, faces, mesh);

    double resolved_target = target_edge_length;
    if (resolved_target == 0.0) {
        resolved_target = mean_edge_length(mesh);
        if (resolved_target <= 0.0) {
            throw std::runtime_error(
                "step 2 (remesh): input mesh has no valid edges (mean edge length = 0). "
                "Repair step 1 must have produced an empty/degenerate mesh.");
        }
    }
    io.report.target_edge_length_used = resolved_target;
    io.report.remesh_iterations_used  = remesh_iterations;

    auto eim = mesh.add_property_map<CgalSurfaceMesh::Edge_index, bool>(
                       "e:robust_constrained", false).first;
    PMP::detect_sharp_edges(mesh, sharp_edge_dihedral_degrees, eim);

    std::size_t sharp_count = 0;
    for (auto e : mesh.edges()) {
        if (eim[e]) {
            ++sharp_count;
        }
    }
    io.report.sharp_edges_detected = sharp_count;
    if (sharp_count == mesh.number_of_edges()) {
        std::ostringstream oss;
        oss << "step 2 (remesh): every edge detected as sharp at threshold "
            << sharp_edge_dihedral_degrees
            << " degrees; isotropic_remeshing has nothing to remesh. "
            << "Consider raising --sharp-edge-degrees (current: "
            << sharp_edge_dihedral_degrees << ").";
        throw std::runtime_error(oss.str());
    }

    try {
        PMP::isotropic_remeshing(
            mesh.faces(), resolved_target, mesh,
            CGAL::parameters::number_of_iterations(static_cast<unsigned>(remesh_iterations))
                             .edge_is_constrained_map(eim)
                             .protect_constraints(true));
    } catch (const std::exception& ex) {
        std::ostringstream oss;
        oss << "step 2 (remesh): isotropic_remeshing failed internally: " << ex.what()
            << ". Consider lowering --remesh-iterations (current: " << remesh_iterations << ").";
        throw std::runtime_error(oss.str());
    }

    surface_mesh_to_mvrmesh(mesh, io.vertices, io.faces);
    io.report.output_vertex_count = io.vertices.size();
    io.report.output_face_count   = io.faces.size();
    return io;
}

SimplifyToBudgetStepIO simplify_to_budget_step(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    std::size_t max_dense_kl_bytes,
    double      safety_margin) {
    if (max_dense_kl_bytes == 0) {
        throw std::runtime_error("step 3 (simplify): max_dense_kl_bytes must be > 0");
    }
    if (!(safety_margin > 0.0 && safety_margin <= 1.0)) {
        throw std::runtime_error("step 3 (simplify): safety_margin must be in (0, 1]");
    }

    SimplifyToBudgetStepIO io;
    io.report.input_vertex_count = vertices.size();
    io.report.input_face_count   = faces.size();
    io.report.budget_bytes       = max_dense_kl_bytes;

    // First pressure evaluation
    DeformSimPressureOptions po;  // defaults: switches="pYQ"
    po.input_ply = "robust_pipeline_internal";
    DeformSimPressureResult p0 = evaluate_deformsim_pressure(vertices, faces, po);
    if (!p0.success) {
        std::ostringstream oss;
        oss << "step 3 (simplify): TetGen failed during initial pressure evaluation. "
            << p0.diagnostic << ". Cannot determine if simplification is needed.";
        throw std::runtime_error(oss.str());
    }
    io.report.bytes_initial = p0.estimated_dense_k_l_bytes;

    if (p0.estimated_dense_k_l_bytes <= max_dense_kl_bytes) {
        io.report.skipped_within_budget = true;
        io.report.bytes_final           = p0.estimated_dense_k_l_bytes;
        io.report.output_vertex_count   = vertices.size();
        io.report.output_face_count     = faces.size();
        io.report.target_vertex_count   = 0;
        io.vertices                     = vertices;
        io.faces                        = faces;
        io.final_pressure_result        = std::move(p0);
        return io;
    }

    // Derive target vertex count
    const double ratio = static_cast<double>(max_dense_kl_bytes) /
                         static_cast<double>(p0.estimated_dense_k_l_bytes);
    const double n_target_raw = static_cast<double>(vertices.size()) * std::sqrt(ratio);
    const std::size_t n_target = static_cast<std::size_t>(
        std::floor(n_target_raw * safety_margin));
    io.report.target_vertex_count = n_target;
    if (n_target < 3) {
        std::ostringstream oss;
        oss << "step 3 (simplify): budget " << max_dense_kl_bytes
            << " is too tight; target vertex count " << n_target
            << " is below the minimum 3 to form a closed surface. "
            << "Raise --max-dense-kl-bytes.";
        throw std::runtime_error(oss.str());
    }

    // Build CGAL Surface_mesh and run edge_collapse
    CgalSurfaceMesh mesh;
    mvrmesh_to_surface_mesh(vertices, faces, mesh);

    namespace SMS = CGAL::Surface_mesh_simplification;
    try {
        // Edge_count_stop_predicate stops on EDGE count, not vertex count.
        // For a triangulated manifold surface mesh, Euler's formula gives
        // E ~= 3V - 6, so to stop at ~n_target vertices we set the edge
        // target to 3 * n_target. The post-check pressure evaluation below
        // still validates the final byte budget, so any small approximation
        // error here is bounded by that envelope.
        const std::size_t edge_target = 3u * n_target;
        SMS::Edge_count_stop_predicate<CgalSurfaceMesh> stop(edge_target);
        SMS::edge_collapse(
            mesh, stop,
            CGAL::parameters::get_cost(SMS::LindstromTurk_cost<CgalSurfaceMesh>())
                             .get_placement(SMS::LindstromTurk_placement<CgalSurfaceMesh>())
                             .filter(SMS::Bounded_normal_change_filter<>()));
    } catch (const std::exception& ex) {
        std::ostringstream oss;
        oss << "step 3 (simplify): edge_collapse failed: " << ex.what();
        throw std::runtime_error(oss.str());
    }

    surface_mesh_to_mvrmesh(mesh, io.vertices, io.faces);
    io.report.output_vertex_count = io.vertices.size();
    io.report.output_face_count   = io.faces.size();

    // Second pressure evaluation
    DeformSimPressureResult p1 = evaluate_deformsim_pressure(io.vertices, io.faces, po);
    if (!p1.success) {
        std::ostringstream oss;
        oss << "step 3 (simplify): TetGen failed during final pressure verification. "
            << p1.diagnostic << ". Final mesh may be valid but pressure cannot be confirmed.";
        throw std::runtime_error(oss.str());
    }
    io.report.bytes_final = p1.estimated_dense_k_l_bytes;
    if (p1.estimated_dense_k_l_bytes > max_dense_kl_bytes) {
        std::ostringstream oss;
        oss << "step 3 (simplify): envelope predicate prevented sufficient collapse; "
            << "target=" << n_target << " reached=" << io.vertices.size()
            << "; final bytes=" << p1.estimated_dense_k_l_bytes
            << " > budget=" << max_dense_kl_bytes
            << ". Consider raising --max-dense-kl-bytes from " << max_dense_kl_bytes << ".";
        throw std::runtime_error(oss.str());
    }

    io.final_pressure_result = std::move(p1);
    return io;
}

}  // namespace detail

RobustPipelineResult run_cgal_robust_pipeline(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const RobustPipelineOptions& options) {
    auto repair = detail::repair_polygon_soup_step(vertices, faces);
    log_repair(repair.report);

    auto remesh = detail::protected_remesh_step(
        repair.vertices, repair.faces,
        options.sharp_edge_dihedral_degrees,
        options.target_edge_length,
        options.remesh_iterations);
    log_remesh(remesh.report);

    auto simplify = detail::simplify_to_budget_step(
        remesh.vertices, remesh.faces,
        options.max_dense_kl_bytes,
        options.simplify_safety_margin);
    log_simplify(simplify.report);

    RobustPipelineResult result;
    result.vertices              = std::move(simplify.vertices);
    result.faces                 = std::move(simplify.faces);
    result.repair_report         = repair.report;
    result.remesh_report         = remesh.report;
    result.simplify_report       = simplify.report;
    result.final_pressure_result = std::move(simplify.final_pressure_result);
    return result;
}

}  // namespace mvrmesh

#endif  // MVRMESH_CGAL_PMP_ENABLED
