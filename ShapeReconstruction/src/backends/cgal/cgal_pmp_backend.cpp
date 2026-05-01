#include "mvrmesh/backends/cgal/cgal_pmp_backend.h"

#include <array>
#include <exception>
#include <limits>
#include <string>

#include <CGAL/Polygon_mesh_processing/remesh.h>
#include <CGAL/Polygon_mesh_processing/repair.h>
#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/boost/graph/helpers.h>

namespace mvrmesh {

namespace {

// Simple_cartesian<double> is sufficient for isotropic_remeshing and
// remove_isolated_vertices: those operations rely on linear constructions
// (midpoints, tangential relaxation) and topological predicates only, so the
// extra robustness of Exact_predicates_inexact_constructions_kernel is not
// needed here. Avoiding EPICK keeps this translation unit out of the
// CGAL::Interval_nt / GMP code path on inexact-construction operations.
using CgalKernel = CGAL::Simple_cartesian<double>;
using CgalPoint = CgalKernel::Point_3;
using CgalSurfaceMesh = CGAL::Surface_mesh<CgalPoint>;
namespace PMP = CGAL::Polygon_mesh_processing;

CgalPmpResult make_base_result(const std::vector<Vec3>& vertices, const std::vector<Face>& faces) {
    CgalPmpResult result;
    result.input_vertex_count = vertices.size();
    result.input_face_count = faces.size();
    return result;
}

bool validate_options(const CgalPmpOptions& options, CgalPmpResult& result) {
    if (options.target_edge_length < 0.0) {
        result.diagnostic = "CGAL PMP target edge length must be >= 0";
        return false;
    }
    if (options.remesh_iterations < 1) {
        result.diagnostic = "CGAL PMP remesh iterations must be >= 1";
        return false;
    }
    return true;
}

bool can_store_face_index(int index, std::size_t vertex_count) {
    return index >= 0 && static_cast<std::size_t>(index) < vertex_count;
}

bool build_cgal_mesh(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    CgalSurfaceMesh& mesh,
    CgalPmpResult& result
) {
    std::vector<CgalSurfaceMesh::Vertex_index> vertex_map;
    vertex_map.reserve(vertices.size());
    for (const Vec3& vertex : vertices) {
        vertex_map.push_back(mesh.add_vertex(CgalPoint(vertex.x, vertex.y, vertex.z)));
    }

    for (std::size_t face_index = 0; face_index < faces.size(); ++face_index) {
        const Face& face = faces[face_index];
        if (!can_store_face_index(face[0], vertices.size()) ||
            !can_store_face_index(face[1], vertices.size()) ||
            !can_store_face_index(face[2], vertices.size())) {
            result.diagnostic = "CGAL PMP input face has an out-of-range vertex index";
            return false;
        }

        const CgalSurfaceMesh::Face_index cgal_face = mesh.add_face(
            vertex_map[static_cast<std::size_t>(face[0])],
            vertex_map[static_cast<std::size_t>(face[1])],
            vertex_map[static_cast<std::size_t>(face[2])]
        );
        if (cgal_face == CgalSurfaceMesh::null_face()) {
            result.diagnostic = "CGAL PMP could not add face " + std::to_string(face_index);
            return false;
        }
    }

    if (!CGAL::is_triangle_mesh(mesh)) {
        result.diagnostic = "CGAL PMP input mesh is not triangular";
        return false;
    }
    return true;
}

bool convert_cgal_mesh(CgalSurfaceMesh& mesh, CgalPmpResult& result) {
    auto vertex_id_map =
        mesh.add_property_map<CgalSurfaceMesh::Vertex_index, int>("v:mvrmesh_index", -1).first;

    std::size_t next_vertex_index = 0;
    for (CgalSurfaceMesh::Vertex_index vertex_descriptor : mesh.vertices()) {
        if (next_vertex_index > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
            result.diagnostic = "CGAL PMP output has too many vertices for mvrmesh::Face indices";
            return false;
        }
        const CgalPoint& point = mesh.point(vertex_descriptor);
        result.output_vertices.push_back(Vec3{
            CGAL::to_double(point.x()),
            CGAL::to_double(point.y()),
            CGAL::to_double(point.z()),
        });
        vertex_id_map[vertex_descriptor] = static_cast<int>(next_vertex_index);
        ++next_vertex_index;
    }

    for (CgalSurfaceMesh::Face_index face_descriptor : mesh.faces()) {
        Face face{0, 0, 0};
        int face_vertex_count = 0;
        for (CgalSurfaceMesh::Vertex_index vertex_descriptor :
             CGAL::vertices_around_face(mesh.halfedge(face_descriptor), mesh)) {
            if (face_vertex_count >= 3) {
                result.diagnostic = "CGAL PMP output contains a non-triangular face";
                return false;
            }
            face[static_cast<std::size_t>(face_vertex_count)] = vertex_id_map[vertex_descriptor];
            ++face_vertex_count;
        }
        if (face_vertex_count != 3) {
            result.diagnostic = "CGAL PMP output contains a degenerate face";
            return false;
        }
        result.output_faces.push_back(face);
    }

    result.output_vertex_count = result.output_vertices.size();
    result.output_face_count = result.output_faces.size();
    return true;
}

}  // namespace

CgalPmpResult run_cgal_pmp_backend(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    const CgalPmpOptions& options
) {
    CgalPmpResult result = make_base_result(vertices, faces);
    if (!validate_options(options, result)) {
        return result;
    }

    try {
        CgalSurfaceMesh mesh;
        if (!build_cgal_mesh(vertices, faces, mesh, result)) {
            return result;
        }
        PMP::remove_isolated_vertices(mesh);
        if (mesh.has_garbage()) {
            mesh.collect_garbage();
        }

        if (options.target_edge_length > 0.0) {
            PMP::isotropic_remeshing(
                mesh.faces(),
                options.target_edge_length,
                mesh,
                CGAL::parameters::number_of_iterations(
                    static_cast<unsigned int>(options.remesh_iterations)
                )
            );
            if (mesh.has_garbage()) {
                mesh.collect_garbage();
            }
            PMP::remove_isolated_vertices(mesh);
            if (mesh.has_garbage()) {
                mesh.collect_garbage();
            }
        }

        if (!convert_cgal_mesh(mesh, result)) {
            result.output_vertices.clear();
            result.output_faces.clear();
            result.output_vertex_count = 0;
            result.output_face_count = 0;
            return result;
        }

        result.success = true;
        result.diagnostic = options.target_edge_length > 0.0
                                ? "CGAL PMP backend cleaned and remeshed the surface"
                                : "CGAL PMP backend cleaned and validated the surface";
        return result;
    } catch (const std::exception& ex) {
        result.success = false;
        result.output_vertices.clear();
        result.output_faces.clear();
        result.output_vertex_count = 0;
        result.output_face_count = 0;
        result.diagnostic = std::string("CGAL PMP backend exception: ") + ex.what();
        return result;
    }
}

}  // namespace mvrmesh
