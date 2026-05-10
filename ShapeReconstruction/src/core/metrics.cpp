#include "mvrmesh/core/metrics.h"

#include <algorithm>
#include <array>
#include <iomanip>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>

#include "mvrmesh/core/geometry.h"

namespace mvrmesh {

namespace {

std::array<int, 3> make_face_key(const Face& face) {
    std::array<int, 3> key{face[0], face[1], face[2]};
    std::sort(key.begin(), key.end());
    return key;
}

struct EdgeDirectionCounts {
    int canonical = 0;
    int opposite = 0;
};

void add_half_edge_direction(std::map<Edge, EdgeDirectionCounts>& edge_directions, int from, int to) {
    const Edge key = make_edge_key(from, to);
    EdgeDirectionCounts& counts = edge_directions[key];
    if (from == key.first && to == key.second) {
        ++counts.canonical;
    } else {
        ++counts.opposite;
    }
}

class DisjointSet {
public:
    explicit DisjointSet(std::size_t n) : parent_(n), rank_(n, 0) {
        std::iota(parent_.begin(), parent_.end(), 0);
    }

    std::size_t find(std::size_t value) {
        if (parent_[value] != value) {
            parent_[value] = find(parent_[value]);
        }
        return parent_[value];
    }

    void unite(std::size_t lhs, std::size_t rhs) {
        std::size_t root_l = find(lhs);
        std::size_t root_r = find(rhs);
        if (root_l == root_r) {
            return;
        }
        if (rank_[root_l] < rank_[root_r]) {
            std::swap(root_l, root_r);
        }
        parent_[root_r] = root_l;
        if (rank_[root_l] == rank_[root_r]) {
            ++rank_[root_l];
        }
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<int> rank_;
};

void validate_face_index(const std::vector<Vec3>& vertices, int idx) {
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertices.size()) {
        std::ostringstream oss;
        oss << "Face index out of range while computing metrics: " << idx
            << ", n_vertices=" << vertices.size();
        throw std::runtime_error(oss.str());
    }
}

}  // namespace

SurfaceMetrics compute_surface_metrics(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces,
    double degeneracy_epsilon
) {
    SurfaceMetrics metrics;
    metrics.vertex_count = vertices.size();
    metrics.face_count = faces.size();
    metrics.degeneracy_epsilon = degeneracy_epsilon;

    if (!vertices.empty()) {
        metrics.bounding_box.valid = true;
        metrics.bounding_box.min = vertices.front();
        metrics.bounding_box.max = vertices.front();
        for (const Vec3& vertex : vertices) {
            metrics.bounding_box.min.x = std::min(metrics.bounding_box.min.x, vertex.x);
            metrics.bounding_box.min.y = std::min(metrics.bounding_box.min.y, vertex.y);
            metrics.bounding_box.min.z = std::min(metrics.bounding_box.min.z, vertex.z);
            metrics.bounding_box.max.x = std::max(metrics.bounding_box.max.x, vertex.x);
            metrics.bounding_box.max.y = std::max(metrics.bounding_box.max.y, vertex.y);
            metrics.bounding_box.max.z = std::max(metrics.bounding_box.max.z, vertex.z);
        }
    }

    std::map<Edge, int> edge_counts;
    std::map<Edge, EdgeDirectionCounts> edge_directions;
    std::map<std::array<int, 3>, int> face_counts;
    DisjointSet components(vertices.size());
    std::vector<bool> used_vertices(vertices.size(), false);

    for (const Face& face : faces) {
        validate_face_index(vertices, face[0]);
        validate_face_index(vertices, face[1]);
        validate_face_index(vertices, face[2]);

        const Vec3& a = vertices[static_cast<std::size_t>(face[0])];
        const Vec3& b = vertices[static_cast<std::size_t>(face[1])];
        const Vec3& c = vertices[static_cast<std::size_t>(face[2])];
        const double area = triangle_area(a, b, c);
        metrics.surface_area += area;
        if (area <= degeneracy_epsilon) {
            ++metrics.degenerate_face_count;
        }

        face_counts[make_face_key(face)] += 1;

        edge_counts[make_edge_key(face[0], face[1])] += 1;
        edge_counts[make_edge_key(face[1], face[2])] += 1;
        edge_counts[make_edge_key(face[2], face[0])] += 1;
        add_half_edge_direction(edge_directions, face[0], face[1]);
        add_half_edge_direction(edge_directions, face[1], face[2]);
        add_half_edge_direction(edge_directions, face[2], face[0]);

        used_vertices[static_cast<std::size_t>(face[0])] = true;
        used_vertices[static_cast<std::size_t>(face[1])] = true;
        used_vertices[static_cast<std::size_t>(face[2])] = true;
        components.unite(static_cast<std::size_t>(face[0]), static_cast<std::size_t>(face[1]));
        components.unite(static_cast<std::size_t>(face[1]), static_cast<std::size_t>(face[2]));
    }

    for (const auto& entry : edge_counts) {
        if (entry.second == 1) {
            ++metrics.boundary_edge_count;
        } else if (entry.second > 2) {
            ++metrics.non_manifold_edge_count;
        } else {
            const EdgeDirectionCounts& counts = edge_directions[entry.first];
            if (counts.canonical != 1 || counts.opposite != 1) {
                ++metrics.inconsistent_orientation_edge_count;
            }
        }
    }

    for (const auto& entry : face_counts) {
        if (entry.second > 1) {
            metrics.duplicate_face_count += static_cast<std::size_t>(entry.second - 1);
        }
    }

    std::set<std::size_t> roots;
    for (std::size_t i = 0; i < used_vertices.size(); ++i) {
        if (!used_vertices[i]) {
            continue;
        }
        roots.insert(components.find(i));
    }
    metrics.connected_component_count = roots.size();

    return metrics;
}

std::string metrics_to_json(const SurfaceMetrics& metrics) {
    std::ostringstream out;
    out << std::setprecision(17);
    out << "{\n";
    out << "  \"vertex_count\": " << metrics.vertex_count << ",\n";
    out << "  \"face_count\": " << metrics.face_count << ",\n";
    out << "  \"degenerate_face_count\": " << metrics.degenerate_face_count << ",\n";
    out << "  \"duplicate_face_count\": " << metrics.duplicate_face_count << ",\n";
    out << "  \"boundary_edge_count\": " << metrics.boundary_edge_count << ",\n";
    out << "  \"non_manifold_edge_count\": " << metrics.non_manifold_edge_count << ",\n";
    out << "  \"inconsistent_orientation_edge_count\": " << metrics.inconsistent_orientation_edge_count << ",\n";
    out << "  \"connected_component_count\": " << metrics.connected_component_count << ",\n";
    out << "  \"degeneracy_epsilon\": " << metrics.degeneracy_epsilon << ",\n";
    out << "  \"surface_area\": " << metrics.surface_area << ",\n";
    out << "  \"bounding_box\": {\n";
    out << "    \"valid\": " << (metrics.bounding_box.valid ? "true" : "false") << ",\n";
    out << "    \"min\": ["
        << metrics.bounding_box.min.x << ", "
        << metrics.bounding_box.min.y << ", "
        << metrics.bounding_box.min.z << "],\n";
    out << "    \"max\": ["
        << metrics.bounding_box.max.x << ", "
        << metrics.bounding_box.max.y << ", "
        << metrics.bounding_box.max.z << "]\n";
    out << "  }\n";
    out << "}\n";
    return out.str();
}

}  // namespace mvrmesh
