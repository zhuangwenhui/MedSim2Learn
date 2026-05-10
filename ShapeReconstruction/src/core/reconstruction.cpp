#include "mvrmesh/core/reconstruction.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <string>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "mvrmesh/core/compaction.h"
#include "mvrmesh/core/geometry.h"

#include <CGAL/AABB_face_graph_triangle_primitive.h>
#include <CGAL/AABB_tree.h>
#include <CGAL/AABB_traits_3.h>
#include <CGAL/Side_of_triangle_mesh.h>
#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/squared_distance_3.h>

namespace mvrmesh {

namespace {

using CgalKernel = CGAL::Simple_cartesian<double>;
using CgalPoint = CgalKernel::Point_3;
using CgalSurfaceMesh = CGAL::Surface_mesh<CgalPoint>;
using CgalTrianglePrimitive = CGAL::AABB_face_graph_triangle_primitive<CgalSurfaceMesh>;
using CgalAabbTraits = CGAL::AABB_traits_3<CgalKernel, CgalTrianglePrimitive>;
using CgalAabbTree = CGAL::AABB_tree<CgalAabbTraits>;
using CgalSideOfMesh = CGAL::Side_of_triangle_mesh<CgalSurfaceMesh, CgalKernel>;

constexpr double k_zero_tolerance = 1e-12;
constexpr double k_degenerate_area_tolerance = 1e-12;
constexpr std::size_t k_default_face_reserve_cap = 1'000'000;
constexpr std::size_t k_default_edge_reserve_cap = 1'000'000;
constexpr std::size_t k_default_node_vertex_reserve_cap = 500'000;

std::size_t checked_size_t_mul(std::size_t lhs, std::size_t rhs, const char* context) {
    if (lhs == 0 || rhs == 0) {
        return 0;
    }
    const std::size_t max = std::numeric_limits<std::size_t>::max();
    if (lhs > max / rhs) {
        throw std::runtime_error(
            std::string("reconstruct_surface_sdf: integer overflow while computing ") + context
        );
    }
    return lhs * rhs;
}

std::size_t checked_size_t_mul3(std::size_t a, std::size_t b, std::size_t c, const char* context) {
    return checked_size_t_mul(checked_size_t_mul(a, b, context), c, context);
}

std::size_t checked_size_t_add(std::size_t lhs, std::size_t rhs, const char* context) {
    if (lhs > std::numeric_limits<std::size_t>::max() - rhs) {
        throw std::runtime_error(
            std::string("reconstruct_surface_sdf: integer overflow while computing ") + context
        );
    }
    return lhs + rhs;
}

struct BBox {
    Vec3 min_v;
    Vec3 max_v;
};

struct SampledGrid {
    int resolution = 0;
    int span = 0;
    Vec3 origin;
    Vec3 spacing;
    std::vector<double> sdf;
};

struct EdgeCacheHash {
    std::size_t operator()(const std::pair<int, int>& key) const noexcept {
        return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(key.first)) << 32)
            ^ static_cast<std::uint32_t>(key.second);
    }
};

BBox compute_bbox(const std::vector<Vec3>& vertices) {
    BBox box{vertices[0], vertices[0]};
    for (const Vec3& v : vertices) {
        box.min_v.x = std::min(box.min_v.x, v.x);
        box.min_v.y = std::min(box.min_v.y, v.y);
        box.min_v.z = std::min(box.min_v.z, v.z);
        box.max_v.x = std::max(box.max_v.x, v.x);
        box.max_v.y = std::max(box.max_v.y, v.y);
        box.max_v.z = std::max(box.max_v.z, v.z);
    }
    return box;
}

void validate_inputs(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfReconstructionOptions& options
) {
    if (options.grid_resolution < 2) {
        throw std::runtime_error("reconstruct_surface_sdf: grid_resolution must be >= 2");
    }
    if (options.grid_resolution > kMaxSdfGridResolution) {
        throw std::runtime_error(
            "reconstruct_surface_sdf: grid_resolution must be <= "
            + std::to_string(kMaxSdfGridResolution)
        );
    }
    if (options.padding_ratio < 0.0) {
        throw std::runtime_error("reconstruct_surface_sdf: padding_ratio must be >= 0");
    }
    if (boundary_faces.empty()) {
        throw std::runtime_error("reconstruct_surface_sdf: boundary_faces is empty");
    }
    const int n_vertices = static_cast<int>(boundary_vertices.size());
    for (const Face& face : boundary_faces) {
        for (int idx : face) {
            if (idx < 0 || idx >= n_vertices) {
                std::ostringstream oss;
                oss << "reconstruct_surface_sdf: face index out of range: " << idx
                    << ", vertex_count=" << n_vertices;
                throw std::runtime_error(oss.str());
            }
        }
    }
}

void setup_grid(
    const BBox& box,
    double padding_ratio,
    int grid_resolution,
    SampledGrid& grid_out
) {
    const double span_x = box.max_v.x - box.min_v.x;
    const double span_y = box.max_v.y - box.min_v.y;
    const double span_z = box.max_v.z - box.min_v.z;
    const double max_span = std::max(span_x, std::max(span_y, span_z));
    if (max_span <= 0.0) {
        throw std::runtime_error("reconstruct_surface_sdf: boundary bbox has zero extent");
    }

    const double padding = max_span * padding_ratio;
    grid_out.resolution = grid_resolution;
    grid_out.span = grid_resolution + 1;
    grid_out.origin = {
        box.min_v.x - padding,
        box.min_v.y - padding,
        box.min_v.z - padding,
    };
    grid_out.spacing = {
        (box.max_v.x - box.min_v.x + 2.0 * padding) / static_cast<double>(grid_resolution),
        (box.max_v.y - box.min_v.y + 2.0 * padding) / static_cast<double>(grid_resolution),
        (box.max_v.z - box.min_v.z + 2.0 * padding) / static_cast<double>(grid_resolution),
    };
    if (grid_out.spacing.x <= 0.0 || grid_out.spacing.y <= 0.0 || grid_out.spacing.z <= 0.0) {
        throw std::runtime_error("reconstruct_surface_sdf: invalid sampling spacing");
    }

    grid_out.sdf.assign(
        checked_size_t_mul3(
            static_cast<std::size_t>(grid_out.span),
            static_cast<std::size_t>(grid_out.span),
            static_cast<std::size_t>(grid_out.span),
            "sdf grid voxel count"
        ),
        0.0
    );
}

int node_index(const SampledGrid& grid, int i, int j, int k) {
    const std::size_t span = static_cast<std::size_t>(grid.span);
    const std::size_t first = checked_size_t_mul(
        static_cast<std::size_t>(i),
        span,
        "node_index i*span"
    );
    const std::size_t second = checked_size_t_mul(
        checked_size_t_add(first, static_cast<std::size_t>(j), "node_index i*span+j"),
        span,
        "node_index (i*span+j)*span"
    );
    const std::size_t index = checked_size_t_add(second, static_cast<std::size_t>(k), "node_index final add k");
    if (index > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("reconstruct_surface_sdf: node_index overflowed int range");
    }
    return static_cast<int>(index);
}

Vec3 node_position(const SampledGrid& grid, int i, int j, int k) {
    return Vec3{
        grid.origin.x + static_cast<double>(i) * grid.spacing.x,
        grid.origin.y + static_cast<double>(j) * grid.spacing.y,
        grid.origin.z + static_cast<double>(k) * grid.spacing.z,
    };
}

void decode_node(int node_id, const SampledGrid& grid, int& i_out, int& j_out, int& k_out) {
    const int plane = grid.span * grid.span;
    i_out = node_id / plane;
    const int rem = node_id - i_out * plane;
    j_out = rem / grid.span;
    k_out = rem - j_out * grid.span;
}

void fill_signed_distance(
    const CgalAabbTree& tree,
    const CgalSideOfMesh& side_of_mesh,
    SampledGrid& grid
) {
    // Compute signed distance at every grid node using CGAL containment query. Negative = inside mesh.
    const int span = grid.span;
    for (int i = 0; i < span; ++i) {
        for (int j = 0; j < span; ++j) {
            for (int k = 0; k < span; ++k) {
                const int idx = node_index(grid, i, j, k);
                const Vec3 p = node_position(grid, i, j, k);
                const CgalPoint query(p.x, p.y, p.z);
                const CgalPoint nearest = tree.closest_point(query);

                const double dist = std::sqrt(CGAL::squared_distance(query, nearest));
                const auto side = side_of_mesh(query);
                if (side == CGAL::ON_BOUNDED_SIDE) {
                    grid.sdf[static_cast<std::size_t>(idx)] = -dist;
                } else if (side == CGAL::ON_UNBOUNDED_SIDE) {
                    grid.sdf[static_cast<std::size_t>(idx)] = dist;
                } else if (side == CGAL::ON_BOUNDARY) {
                    grid.sdf[static_cast<std::size_t>(idx)] = 0.0;
                } else {
                    throw std::runtime_error(
                        "reconstruct_surface_sdf: unknown result from CGAL::Side_of_triangle_mesh"
                    );
                }
            }
        }
    }
}

std::pair<int, int> sorted_node_pair(int a, int b) {
    if (a < b) {
        return std::make_pair(a, b);
    }
    return std::make_pair(b, a);
}

int get_or_add_intersection(
    int node_a,
    int node_b,
    double sdf_a,
    double sdf_b,
    const SampledGrid& grid,
    std::vector<Vec3>& vertices,
    std::unordered_map<int, int>& node_vertex_cache,
    std::unordered_map<std::pair<int, int>, int, EdgeCacheHash>& edge_cache
) {
    if (std::fabs(sdf_a) <= k_zero_tolerance) {
        if (const auto found = node_vertex_cache.find(node_a); found != node_vertex_cache.end()) {
            return found->second;
        }
        int ai = 0;
        int aj = 0;
        int ak = 0;
        decode_node(node_a, grid, ai, aj, ak);
        const Vec3 p = node_position(grid, ai, aj, ak);
        const int out_idx = static_cast<int>(vertices.size());
        vertices.push_back(p);
        node_vertex_cache.emplace(node_a, out_idx);
        return out_idx;
    }
    if (std::fabs(sdf_b) <= k_zero_tolerance) {
        if (const auto found = node_vertex_cache.find(node_b); found != node_vertex_cache.end()) {
            return found->second;
        }
        int bi = 0;
        int bj = 0;
        int bk = 0;
        decode_node(node_b, grid, bi, bj, bk);
        const Vec3 p = node_position(grid, bi, bj, bk);
        const int out_idx = static_cast<int>(vertices.size());
        vertices.push_back(p);
        node_vertex_cache.emplace(node_b, out_idx);
        return out_idx;
    }

    const auto key = sorted_node_pair(node_a, node_b);
    if (const auto found = edge_cache.find(key); found != edge_cache.end()) {
        return found->second;
    }

    if (std::fabs(sdf_b - sdf_a) < k_zero_tolerance) {
        const double t = 0.5;
        int ai = 0;
        int aj = 0;
        int ak = 0;
        decode_node(node_a, grid, ai, aj, ak);
        int bi = 0;
        int bj = 0;
        int bk = 0;
        decode_node(node_b, grid, bi, bj, bk);

        const Vec3 pa = node_position(grid, ai, aj, ak);
        const Vec3 pb = node_position(grid, bi, bj, bk);
        const Vec3 p{
            pa.x + (pb.x - pa.x) * t,
            pa.y + (pb.y - pa.y) * t,
            pa.z + (pb.z - pa.z) * t,
        };
        const int out_idx = static_cast<int>(vertices.size());
        vertices.push_back(p);
        edge_cache.emplace(key, out_idx);
        return out_idx;
    }

    double t = (-sdf_a) / (sdf_b - sdf_a);
    if (t < 0.0 - k_zero_tolerance || t > 1.0 + k_zero_tolerance) {
        throw std::runtime_error("reconstruct_surface_sdf: invalid interpolation factor while extracting surface");
    }
    t = std::clamp(t, 0.0, 1.0);

    int ai = 0;
    int aj = 0;
    int ak = 0;
    decode_node(node_a, grid, ai, aj, ak);

    int bi = 0;
    int bj = 0;
    int bk = 0;
    decode_node(node_b, grid, bi, bj, bk);

    const Vec3 pa = node_position(grid, ai, aj, ak);
    const Vec3 pb = node_position(grid, bi, bj, bk);
    const Vec3 p{
        pa.x + (pb.x - pa.x) * t,
        pa.y + (pb.y - pa.y) * t,
        pa.z + (pb.z - pa.z) * t,
    };

    const int out_idx = static_cast<int>(vertices.size());
    vertices.push_back(p);
    edge_cache.emplace(key, out_idx);
    return out_idx;
}

bool face_is_degenerate(const Face& face, const std::vector<Vec3>& vertices) {
    if (face[0] == face[1] || face[0] == face[2] || face[1] == face[2]) {
        return true;
    }
    const Vec3 a = vertices.at(static_cast<std::size_t>(face[0]));
    const Vec3 b = vertices.at(static_cast<std::size_t>(face[1]));
    const Vec3 c = vertices.at(static_cast<std::size_t>(face[2]));
    return norm(cross(vsub(b, a), vsub(c, a))) <= k_degenerate_area_tolerance;
}

void append_triangle(
    const Face& face,
    std::vector<Face>& faces,
    const std::vector<Vec3>& vertices
) {
    if (face_is_degenerate(face, vertices)) {
        return;
    }
    faces.push_back(face);
}

void orient_faces_outward(const std::vector<Vec3>& vertices, std::vector<Face>& faces) {
    if (faces.empty() || vertices.empty()) {
        return;
    }

    Vec3 centroid{0.0, 0.0, 0.0};
    for (const Vec3& vertex : vertices) {
        centroid = vadd(centroid, vertex);
    }
    centroid = vmul(centroid, 1.0 / static_cast<double>(vertices.size()));

    for (Face& face : faces) {
        const Vec3& a = vertices[static_cast<std::size_t>(face[0])];
        const Vec3& b = vertices[static_cast<std::size_t>(face[1])];
        const Vec3& c = vertices[static_cast<std::size_t>(face[2])];
        const Vec3 normal = cross(vsub(b, a), vsub(c, a));
        if (norm(normal) <= k_degenerate_area_tolerance) {
            continue;
        }

        const Vec3 face_center = vmul(vadd(vadd(a, b), c), 1.0 / 3.0);
        const Vec3 to_face = vsub(face_center, centroid);
        if (dot(normal, to_face) < 0.0) {
            std::swap(face[1], face[2]);
        }
    }
}

int local_index(int node_id, const std::array<int, 4>& nodes) {
    for (int i = 0; i < 4; ++i) {
        if (nodes[static_cast<std::size_t>(i)] == node_id) {
            return i;
        }
    }
    throw std::runtime_error("reconstruct_surface_sdf: node not in tetrahedron");
}

void process_tetrahedron(
    const std::array<int, 4>& tet_nodes,
    const std::array<double, 4>& tet_sdf,
    const SampledGrid& grid,
    std::vector<Vec3>& vertices,
    std::vector<Face>& faces,
    std::unordered_map<int, int>& node_vertex_cache,
    std::unordered_map<std::pair<int, int>, int, EdgeCacheHash>& edge_cache
) {
    std::array<int, 4> inside_nodes{};
    std::array<int, 4> outside_nodes{};
    int inside_count = 0;
    int outside_count = 0;

    for (int i = 0; i < 4; ++i) {
        if (tet_sdf[static_cast<std::size_t>(i)] <= 0.0) {
            inside_nodes[static_cast<std::size_t>(inside_count++)] = tet_nodes[static_cast<std::size_t>(i)];
        } else {
            outside_nodes[static_cast<std::size_t>(outside_count++)] = tet_nodes[static_cast<std::size_t>(i)];
        }
    }

    if (inside_count == 0 || outside_count == 0) {
        return;
    }

    // Handle 3 marching-tetrahedra cut cases: 1-inside/3-outside, 2/2, and 3/1.
    if (inside_count == 1 && outside_count == 3) {
        const int in = inside_nodes[0];
        const int in_local = local_index(in, tet_nodes);
        const int o0 = outside_nodes[0];
        const int o1 = outside_nodes[1];
        const int o2 = outside_nodes[2];

        const int p0 = get_or_add_intersection(
            in, o0, tet_sdf[static_cast<std::size_t>(in_local)], tet_sdf[static_cast<std::size_t>(local_index(o0, tet_nodes))],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p1 = get_or_add_intersection(
            in, o1, tet_sdf[static_cast<std::size_t>(in_local)], tet_sdf[static_cast<std::size_t>(local_index(o1, tet_nodes))],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p2 = get_or_add_intersection(
            in, o2, tet_sdf[static_cast<std::size_t>(in_local)], tet_sdf[static_cast<std::size_t>(local_index(o2, tet_nodes))],
            grid, vertices, node_vertex_cache, edge_cache
        );
        append_triangle(Face{p0, p1, p2}, faces, vertices);
        return;
    }

    if (inside_count == 2 && outside_count == 2) {
        const int i0 = inside_nodes[0];
        const int i1 = inside_nodes[1];
        const int o0 = outside_nodes[0];
        const int o1 = outside_nodes[1];
        const int i0_local = local_index(i0, tet_nodes);
        const int i1_local = local_index(i1, tet_nodes);
        const int o0_local = local_index(o0, tet_nodes);
        const int o1_local = local_index(o1, tet_nodes);

        const int p0 = get_or_add_intersection(
            i0, o0, tet_sdf[static_cast<std::size_t>(i0_local)], tet_sdf[static_cast<std::size_t>(o0_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p1 = get_or_add_intersection(
            i1, o0, tet_sdf[static_cast<std::size_t>(i1_local)], tet_sdf[static_cast<std::size_t>(o0_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p2 = get_or_add_intersection(
            i1, o1, tet_sdf[static_cast<std::size_t>(i1_local)], tet_sdf[static_cast<std::size_t>(o1_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p3 = get_or_add_intersection(
            i0, o1, tet_sdf[static_cast<std::size_t>(i0_local)], tet_sdf[static_cast<std::size_t>(o1_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        append_triangle(Face{p0, p1, p2}, faces, vertices);
        append_triangle(Face{p0, p2, p3}, faces, vertices);
        return;
    }

    if (inside_count == 3 && outside_count == 1) {
        const int o = outside_nodes[0];
        const int i0 = inside_nodes[0];
        const int i1 = inside_nodes[1];
        const int i2 = inside_nodes[2];
        const int o_local = local_index(o, tet_nodes);
        const int i0_local = local_index(i0, tet_nodes);
        const int i1_local = local_index(i1, tet_nodes);
        const int i2_local = local_index(i2, tet_nodes);

        const int p0 = get_or_add_intersection(
            i0, o, tet_sdf[static_cast<std::size_t>(i0_local)], tet_sdf[static_cast<std::size_t>(o_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p1 = get_or_add_intersection(
            i1, o, tet_sdf[static_cast<std::size_t>(i1_local)], tet_sdf[static_cast<std::size_t>(o_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        const int p2 = get_or_add_intersection(
            i2, o, tet_sdf[static_cast<std::size_t>(i2_local)], tet_sdf[static_cast<std::size_t>(o_local)],
            grid, vertices, node_vertex_cache, edge_cache
        );
        append_triangle(Face{p0, p1, p2}, faces, vertices);
    }
}

CgalSurfaceMesh to_surface_mesh(const std::vector<Vec3>& vertices, const std::vector<Face>& faces) {
    CgalSurfaceMesh mesh;
    std::vector<CgalSurfaceMesh::Vertex_index> vmap;
    vmap.reserve(vertices.size());
    for (const Vec3& v : vertices) {
        vmap.push_back(mesh.add_vertex(CgalPoint(v.x, v.y, v.z)));
    }

    for (const Face& face : faces) {
        const CgalSurfaceMesh::Face_index fd = mesh.add_face(
            vmap[static_cast<std::size_t>(face[0])],
            vmap[static_cast<std::size_t>(face[1])],
            vmap[static_cast<std::size_t>(face[2])]
        );
        if (fd == CgalSurfaceMesh::null_face()) {
            std::ostringstream oss;
            oss << "reconstruct_surface_sdf: could not add CGAL face (" << face[0] << ", "
                << face[1] << ", " << face[2] << ")";
            throw std::runtime_error(oss.str());
        }
    }

    if (mesh.number_of_faces() == 0) {
        throw std::runtime_error("reconstruct_surface_sdf: CGAL Surface_mesh has no faces");
    }
    return mesh;
}

}  // namespace

ReconstructedMesh reconstruct_surface_sdf(
    const std::vector<Vec3>& boundary_vertices,
    const std::vector<Face>& boundary_faces,
    const SdfReconstructionOptions& options
) {
    validate_inputs(boundary_vertices, boundary_faces, options);

    const std::pair<std::vector<Vec3>, std::vector<Face>> compacted =
        compact_mesh_to_referenced_vertices(boundary_vertices, boundary_faces);
    const std::vector<Vec3>& vertices = compacted.first;
    const std::vector<Face>& faces = compacted.second;
    if (vertices.empty() || faces.empty()) {
        throw std::runtime_error("reconstruct_surface_sdf: compacted boundary mesh is empty");
    }

    const BBox box = compute_bbox(vertices);
    SampledGrid grid;
    setup_grid(box, options.padding_ratio, options.grid_resolution, grid);

    CgalSurfaceMesh mesh;
    CgalAabbTree tree;

    try {
        mesh = to_surface_mesh(vertices, faces);
        tree = CgalAabbTree(mesh.faces().begin(), mesh.faces().end(), mesh);
        if (tree.empty()) {
            throw std::runtime_error("AABB tree is empty");
        }
        tree.accelerate_distance_queries();
        const CgalSideOfMesh side_of_mesh(mesh);
        fill_signed_distance(tree, side_of_mesh, grid);
    } catch (const std::exception& ex) {
        throw std::runtime_error(
            std::string("reconstruct_surface_sdf: CGAL mesh/AABB/containment initialization failed: ")
            + ex.what()
        );
    }

    std::vector<Vec3> reconstructed_vertices;
    std::vector<Face> reconstructed_faces;
    const std::size_t r = static_cast<std::size_t>(grid.resolution);
    const std::size_t s = static_cast<std::size_t>(grid.span);
    const std::size_t estimated_tetra_count = checked_size_t_mul3(r, r, r, "cube tetra count");
    const std::size_t estimated_face_count = checked_size_t_mul(estimated_tetra_count, 2u, "tetra face upper bound");
    reconstructed_faces.reserve(std::min(estimated_face_count, k_default_face_reserve_cap));
    std::unordered_map<std::pair<int, int>, int, EdgeCacheHash> edge_cache;
    const std::size_t estimated_intersections = checked_size_t_mul3(r, r, r, "cube edge interpolation count");
    edge_cache.reserve(std::min(
        checked_size_t_mul(estimated_intersections, 24u, "edge interpolation reserve"),
        k_default_edge_reserve_cap
    ));
    std::unordered_map<int, int> node_vertex_cache;
    const std::size_t max_node_vertices = checked_size_t_mul3(s, s, s, "node vertex cache candidate count");
    node_vertex_cache.reserve(std::min(max_node_vertices, k_default_node_vertex_reserve_cap));

    // Decompose each cube into 6 tetrahedra sharing the main diagonal (nodes 0 and 6).
    const std::array<std::array<int, 4>, 6> tetrahedra = {{
        {0, 1, 2, 6},
        {0, 2, 3, 6},
        {0, 3, 7, 6},
        {0, 7, 4, 6},
        {0, 4, 5, 6},
        {0, 5, 1, 6},
    }};

    for (int i = 0; i < grid.resolution; ++i) {
        for (int j = 0; j < grid.resolution; ++j) {
            for (int k = 0; k < grid.resolution; ++k) {
                const std::array<int, 8> cube_nodes{
                    node_index(grid, i, j, k),         // 0
                    node_index(grid, i + 1, j, k),     // 1
                    node_index(grid, i + 1, j + 1, k), // 2
                    node_index(grid, i, j + 1, k),     // 3
                    node_index(grid, i, j, k + 1),     // 4
                    node_index(grid, i + 1, j, k + 1), // 5
                    node_index(grid, i + 1, j + 1, k + 1), // 6
                    node_index(grid, i, j + 1, k + 1), // 7
                };

                for (const auto& tetra : tetrahedra) {
                    const std::array<int, 4> tet_nodes{
                        cube_nodes[static_cast<std::size_t>(tetra[0])],
                        cube_nodes[static_cast<std::size_t>(tetra[1])],
                        cube_nodes[static_cast<std::size_t>(tetra[2])],
                        cube_nodes[static_cast<std::size_t>(tetra[3])],
                    };

                    const std::array<double, 4> tet_sdf{
                        grid.sdf[static_cast<std::size_t>(tet_nodes[0])],
                        grid.sdf[static_cast<std::size_t>(tet_nodes[1])],
                        grid.sdf[static_cast<std::size_t>(tet_nodes[2])],
                        grid.sdf[static_cast<std::size_t>(tet_nodes[3])],
                    };
                    process_tetrahedron(
                        tet_nodes,
                        tet_sdf,
                        grid,
                        reconstructed_vertices,
                        reconstructed_faces,
                        node_vertex_cache,
                        edge_cache
                    );
                }
            }
        }
    }

    orient_faces_outward(reconstructed_vertices, reconstructed_faces);

    const std::pair<std::vector<Vec3>, std::vector<Face>> compacted_out =
        compact_mesh_to_referenced_vertices(reconstructed_vertices, reconstructed_faces);

    return ReconstructedMesh{
        std::move(compacted_out.first),
        std::move(compacted_out.second),
    };
}

}  // namespace mvrmesh
