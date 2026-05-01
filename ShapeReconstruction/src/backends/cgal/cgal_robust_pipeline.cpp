#include "mvrmesh/backends/cgal/cgal_robust_pipeline.h"

#if MVRMESH_CGAL_PMP_ENABLED

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <CGAL/Polygon_mesh_processing/orient_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/repair_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/triangulate_hole.h>
#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>

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

    // Convert back to mvrmesh containers
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
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/,
    double /*sharp_edge_dihedral_degrees*/,
    double /*target_edge_length*/,
    int    /*remesh_iterations*/) {
    throw std::runtime_error("protected_remesh_step: not implemented yet");
}

SimplifyToBudgetStepIO simplify_to_budget_step(
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/,
    std::size_t /*max_dense_kl_bytes*/,
    double      /*safety_margin*/) {
    throw std::runtime_error("simplify_to_budget_step: not implemented yet");
}

}  // namespace detail

RobustPipelineResult run_cgal_robust_pipeline(
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/,
    const RobustPipelineOptions& /*options*/) {
    throw std::runtime_error("run_cgal_robust_pipeline: not implemented yet");
}

}  // namespace mvrmesh

#endif  // MVRMESH_CGAL_PMP_ENABLED
