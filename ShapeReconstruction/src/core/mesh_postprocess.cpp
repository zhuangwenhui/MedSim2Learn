#include "mvrmesh/core/mesh_postprocess.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <unordered_set>
#include <vector>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/convex_hull_3.h>

#include "mvrmesh/core/geometry.h"
#include "mvrmesh/core/topology.h"

namespace mvrmesh {

namespace {

double edge_length_sq(const Vec3& a, const Vec3& b) {
    const double dx = b.x - a.x;
    const double dy = b.y - a.y;
    const double dz = b.z - a.z;
    return dx * dx + dy * dy + dz * dz;
}

double compute_min_edge_length(const std::vector<Vec3>& vertices,
                               const std::vector<Face>& faces) {
    double min_sq = std::numeric_limits<double>::max();
    for (const auto& f : faces) {
        const auto& a = vertices[static_cast<std::size_t>(f[0])];
        const auto& b = vertices[static_cast<std::size_t>(f[1])];
        const auto& c = vertices[static_cast<std::size_t>(f[2])];
        min_sq = std::min(min_sq, edge_length_sq(a, b));
        min_sq = std::min(min_sq, edge_length_sq(b, c));
        min_sq = std::min(min_sq, edge_length_sq(c, a));
    }
    return std::sqrt(min_sq);
}

// Symmetric 3x3 Jacobi eigen-decomposition. Eigenvector i is column i of evec.
void jacobi_eigen_3x3(const double in[3][3], double eval[3], double evec[3][3]) {
    double a[3][3];
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j) {
            a[i][j] = in[i][j];
            evec[i][j] = (i == j) ? 1.0 : 0.0;
        }
    // Each sweep annihilates the largest off-diagonal entry with one Givens
    // rotation; 3x3 symmetric input converges long before the iteration cap.
    for (int iter = 0; iter < 100; ++iter) {
        int p = 0, q = 1;
        double off = std::abs(a[0][1]);
        if (std::abs(a[0][2]) > off) { off = std::abs(a[0][2]); p = 0; q = 2; }
        if (std::abs(a[1][2]) > off) { off = std::abs(a[1][2]); p = 1; q = 2; }
        if (off < 1e-18) break;
        double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
        double t = (theta >= 0.0 ? 1.0 : -1.0) /
                   (std::abs(theta) + std::sqrt(theta * theta + 1.0));
        double c = 1.0 / std::sqrt(t * t + 1.0);
        double s = t * c;
        double app = a[p][p], aqq = a[q][q], apq = a[p][q];
        a[p][p] = c*c*app - 2.0*s*c*apq + s*s*aqq;
        a[q][q] = s*s*app + 2.0*s*c*apq + c*c*aqq;
        a[p][q] = 0.0; a[q][p] = 0.0;
        int r = 3 - p - q;
        double arp = a[r][p], arq = a[r][q];
        a[r][p] = c*arp - s*arq; a[p][r] = a[r][p];
        a[r][q] = s*arp + c*arq; a[q][r] = a[r][q];
        for (int i = 0; i < 3; ++i) {
            double vip = evec[i][p], viq = evec[i][q];
            evec[i][p] = c*vip - s*viq;
            evec[i][q] = s*vip + c*viq;
        }
    }
    for (int i = 0; i < 3; ++i) eval[i] = a[i][i];
}

// Principal-axes pose frame: orthonormal basis cx/cy/cz and its origin.
struct Frame { Vec3 cx, cy, cz, center; };

// Area-weighted PCA over face centroids. Axes are sorted by decreasing
// covariance: cx spans the longest extent, cz the thinnest. Degenerate input
// (zero total area) falls back to the identity frame at the origin.
Frame compute_principal_frame(const std::vector<Vec3>& v,
                              const std::vector<Face>& faces) {
    Vec3 center{0,0,0};
    double total_area = 0.0;
    std::vector<Vec3> fc; fc.reserve(faces.size());
    std::vector<double> fa; fa.reserve(faces.size());
    for (const auto& f : faces) {
        const Vec3& a = v[static_cast<std::size_t>(f[0])];
        const Vec3& b = v[static_cast<std::size_t>(f[1])];
        const Vec3& c = v[static_cast<std::size_t>(f[2])];
        double area = triangle_area(a, b, c);
        Vec3 cc{(a.x+b.x+c.x)/3.0, (a.y+b.y+c.y)/3.0, (a.z+b.z+c.z)/3.0};
        center.x += cc.x*area; center.y += cc.y*area; center.z += cc.z*area;
        total_area += area; fc.push_back(cc); fa.push_back(area);
    }
    if (total_area <= 0.0) { return Frame{{1,0,0},{0,1,0},{0,0,1},{0,0,0}}; }
    center.x /= total_area; center.y /= total_area; center.z /= total_area;

    double cov[3][3] = {{0,0,0},{0,0,0},{0,0,0}};
    for (std::size_t i = 0; i < fc.size(); ++i) {
        double w = fa[i];
        double dx = fc[i].x - center.x, dy = fc[i].y - center.y, dz = fc[i].z - center.z;
        cov[0][0]+=w*dx*dx; cov[0][1]+=w*dx*dy; cov[0][2]+=w*dx*dz;
        cov[1][1]+=w*dy*dy; cov[1][2]+=w*dy*dz; cov[2][2]+=w*dz*dz;
    }
    cov[1][0]=cov[0][1]; cov[2][0]=cov[0][2]; cov[2][1]=cov[1][2];

    double eval[3]; double evec[3][3];
    jacobi_eigen_3x3(cov, eval, evec);
    int idx[3] = {0,1,2};
    for (int i=0;i<3;i++) for(int j=i+1;j<3;j++) if (eval[idx[j]]>eval[idx[i]]) std::swap(idx[i],idx[j]);
    auto col = [&](int k){ return Vec3{evec[0][k], evec[1][k], evec[2][k]}; };
    Frame fr;
    fr.cx = normalize(col(idx[0]));
    fr.cy = normalize(col(idx[1]));
    fr.cz = normalize(col(idx[2]));
    fr.center = center;
    return fr;
}

// Rigid world-to-frame transform: translate each vertex by -center, then
// project onto the cx/cy/cz axes.
void apply_frame(std::vector<Vec3>& v, const Frame& fr) {
    for (auto& p : v) {
        Vec3 d{p.x - fr.center.x, p.y - fr.center.y, p.z - fr.center.z};
        p.x = dot(fr.cx, d);
        p.y = dot(fr.cy, d);
        p.z = dot(fr.cz, d);
    }
}

// Outward normal of the largest convex-hull facet on which the centroid projects
// inside the facet (most stable resting support). out_dir points "down" (toward
// the table). Returns false if no stable facet found.
bool hull_support_down_direction(const std::vector<Vec3>& verts, const Vec3& centroid,
                                 Vec3& out_dir) {
    using K = CGAL::Simple_cartesian<double>;
    using Point_3 = K::Point_3;
    using SMesh = CGAL::Surface_mesh<Point_3>;
    std::vector<Point_3> pts;
    pts.reserve(verts.size());
    for (const auto& p : verts) pts.emplace_back(p.x, p.y, p.z);
    SMesh hull;
    try {
        CGAL::convex_hull_3(pts.begin(), pts.end(), hull);
    } catch (const std::exception& ex) {
        // Degenerate input (e.g. all-coplanar points) must not kill the run;
        // fall back to the plain PCA orientation without the hull sign fix.
        std::cerr << "[warn] canonicalize_pose: convex_hull_3 failed ("
                  << ex.what() << "); skipping hull support-direction heuristic\n";
        return false;
    }

    double best_area = -1.0;
    bool found = false;
    for (auto fdesc : hull.faces()) {
        auto h = hull.halfedge(fdesc);
        auto q0 = hull.point(hull.source(h));
        auto q1 = hull.point(hull.target(h));
        auto q2 = hull.point(hull.target(hull.next(h)));
        Vec3 a{q0.x(), q0.y(), q0.z()};
        Vec3 b{q1.x(), q1.y(), q1.z()};
        Vec3 c{q2.x(), q2.y(), q2.z()};
        double area = triangle_area(a, b, c);
        if (area <= 1e-18) continue;
        Vec3 nrm = normalize(face_normal(a, b, c));   // unit outward normal
        // Foot = projection of centroid onto the facet plane along nrm.
        double dd = dot(vsub(centroid, a), nrm);
        Vec3 foot{centroid.x - dd * nrm.x, centroid.y - dd * nrm.y, centroid.z - dd * nrm.z};
        Vec3 cp = closest_point_on_triangle(centroid, a, b, c);
        bool inside = (norm(vsub(cp, foot)) < 1e-6 * (1.0 + norm(foot)));
        if (inside && area > best_area) { best_area = area; out_dir = nrm; found = true; }
    }
    return found;
}

}  // namespace

int mesh_quality_fix(std::vector<Vec3>& vertices, std::vector<Face>& faces) {
    if (vertices.empty() || faces.empty()) {
        return 0;
    }

    // -- Step 1: Vertex perturbation (always runs) --
    // Jitter amplitude is 1e-6 of the shortest edge: enough to break exact
    // coincidences, negligible against the mesh resolution.
    const double min_edge = compute_min_edge_length(vertices, faces);
    const double epsilon = min_edge * 1e-6;

    std::mt19937_64 rng(42);  // deterministic seed
    std::uniform_real_distribution<double> dist(-epsilon, epsilon);

    for (auto& v : vertices) {
        v.x += dist(rng);
        v.y += dist(rng);
        v.z += dist(rng);
    }

    std::cout << "[info] mesh_quality_fix: perturbed " << vertices.size()
              << " vertices, epsilon=" << epsilon << "\n";

    // -- Step 2: Degenerate triangle detection and removal --
    // The area threshold scales with the squared minimum edge so the test is
    // independent of mesh resolution.
    const double area_threshold = min_edge * min_edge * 1e-8;
    int fixed_count = 0;

    std::vector<std::size_t> degenerate_indices;
    for (std::size_t i = 0; i < faces.size(); ++i) {
        const auto& f = faces[i];
        const auto& a = vertices[static_cast<std::size_t>(f[0])];
        const auto& b = vertices[static_cast<std::size_t>(f[1])];
        const auto& c = vertices[static_cast<std::size_t>(f[2])];
        if (triangle_area(a, b, c) < area_threshold) {
            degenerate_indices.push_back(i);
        }
    }

    if (!degenerate_indices.empty()) {
        // Erase back-to-front so earlier indices stay valid.
        for (auto it = degenerate_indices.rbegin();
             it != degenerate_indices.rend(); ++it) {
            faces.erase(faces.begin() + static_cast<std::ptrdiff_t>(*it));
            ++fixed_count;
        }
        std::cout << "[info] mesh_quality_fix: removed " << fixed_count
                  << " degenerate triangles\n";
    }

    // -- Step 3: Remove duplicate faces --
    auto face_key = [](const Face& f) -> std::array<int, 3> {
        std::array<int, 3> sorted = f;
        std::sort(sorted.begin(), sorted.end());
        return sorted;
    };

    // Hash for sorted index triples (boost::hash_combine-style mixing).
    struct ArrayHash {
        std::size_t operator()(const std::array<int, 3>& a) const {
            std::size_t h = 0;
            for (int v : a) {
                h ^= std::hash<int>{}(v) + 0x9e3779b9 + (h << 6) + (h >> 2);
            }
            return h;
        }
    };

    std::unordered_set<std::array<int, 3>, ArrayHash> seen;
    std::vector<Face> unique_faces;
    unique_faces.reserve(faces.size());
    int dup_count = 0;
    for (const auto& f : faces) {
        auto key = face_key(f);
        if (seen.insert(key).second) {
            unique_faces.push_back(f);
        } else {
            ++dup_count;
        }
    }
    if (dup_count > 0) {
        faces = std::move(unique_faces);
        std::cout << "[info] mesh_quality_fix: removed " << dup_count
                  << " duplicate faces\n";
    }

    return fixed_count;
}

void restore_physical_coordinates(
    std::vector<Vec3>& vertices,
    const BoundingBox& bounding_box,
    double voxel_spacing_mm) {
    if (!bounding_box.valid) {
        std::cerr << "[warn] restore_physical_coordinates: "
                     "no valid bounding box, skipping\n";
        return;
    }
    if (vertices.empty()) {
        return;
    }

    // Compute current vertex bounding box.
    const MeshBoundingBox vbox = compute_bbox(vertices);
    const double v_x_min = vbox.min.x, v_x_max = vbox.max.x;
    const double v_y_min = vbox.min.y, v_y_max = vbox.max.y;
    const double v_z_min = vbox.min.z, v_z_max = vbox.max.z;

    const double v_x_span = v_x_max - v_x_min;
    const double v_y_span = v_y_max - v_y_min;
    const double v_z_span = v_z_max - v_z_min;
    const double bb_x_span = bounding_box.x_max - bounding_box.x_min;
    const double bb_y_span = bounding_box.y_max - bounding_box.y_min;
    const double bb_z_span = bounding_box.z_max - bounding_box.z_min;

    std::cout << "[info] restore_physical_coordinates: "
              << "vertex BB [" << v_x_min << ".." << v_x_max
              << "] x [" << v_y_min << ".." << v_y_max
              << "] x [" << v_z_min << ".." << v_z_max << "]\n";

    // Per axis: affine-map the current span onto the MVR header bounding box
    // (voxel units), then scale by the voxel spacing into mm. A zero-span
    // (flat) axis is translated only.
    for (auto& v : vertices) {
        if (v_x_span > 0.0 && bb_x_span > 0.0) {
            v.x = (bounding_box.x_min +
                   (v.x - v_x_min) / v_x_span * bb_x_span) *
                  voxel_spacing_mm;
        } else if (v_x_span == 0.0) {
            v.x = (v.x + bounding_box.x_min) * voxel_spacing_mm;
        }
        if (v_y_span > 0.0 && bb_y_span > 0.0) {
            v.y = (bounding_box.y_min +
                   (v.y - v_y_min) / v_y_span * bb_y_span) *
                  voxel_spacing_mm;
        } else if (v_y_span == 0.0) {
            v.y = (v.y + bounding_box.y_min) * voxel_spacing_mm;
        }
        if (v_z_span > 0.0 && bb_z_span > 0.0) {
            v.z = (bounding_box.z_min +
                   (v.z - v_z_min) / v_z_span * bb_z_span) *
                  voxel_spacing_mm;
        } else if (v_z_span == 0.0) {
            v.z = (v.z + bounding_box.z_min) * voxel_spacing_mm;
        }
    }

    // Log restored bounding box.
    const MeshBoundingBox rbox = compute_bbox(vertices);
    std::cout << "[info] restore_physical_coordinates: "
              << "restored BB [" << rbox.min.x << ".." << rbox.max.x
              << "] x [" << rbox.min.y << ".." << rbox.max.y
              << "] x [" << rbox.min.z << ".." << rbox.max.z
              << "] mm\n";
}

void canonicalize_pose(std::vector<Vec3>& vertices, const std::vector<Face>& faces, bool flip) {
    if (vertices.empty() || faces.empty()) return;
    Frame fr = compute_principal_frame(vertices, faces);
    // Orient so the most-stable convex-hull support facet faces -z (resting side).
    Vec3 down;
    if (hull_support_down_direction(vertices, fr.center, down)) {
        if (dot(fr.cz, down) > 0.0) {
            fr.cz = Vec3{-fr.cz.x, -fr.cz.y, -fr.cz.z};
        }
    }
    if (flip) {
        fr.cz = Vec3{-fr.cz.x, -fr.cz.y, -fr.cz.z};  // rest on the opposite broad face
    }
    // Ensure right-handed frame: cy = cz x cx, then cx = cy x cz.
    fr.cy = normalize(cross(fr.cz, fr.cx));
    fr.cx = normalize(cross(fr.cy, fr.cz));
    apply_frame(vertices, fr);
    std::cout << "[info] canonicalize_pose: centered + aligned (PCA + hull sign"
              << (flip ? ", flipped" : "") << ")\n";
}

}  // namespace mvrmesh
