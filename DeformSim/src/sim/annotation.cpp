// Annotation JSON loading and contact-region (k-ring) precomputation.
#include "sim/annotation.h"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <utility>

#include <nlohmann/json.hpp>

bool LoadAnnotationJSON(const std::string& path, int nNode, AnnotationData& out) {
    std::ifstream fin(path);
    if (!fin.is_open()) {
        printf("Error: Cannot open annotation file: %s\n", path.c_str());
        return false;
    }

    nlohmann::json doc;
    out.freeze_vertices.clear();
    out.contacts.clear();

    // One guard for the whole load: parse_error, type_error and out_of_range
    // all derive from json::exception; a typo'd key or wrong-typed field must
    // produce a clean error, not terminate the process.
    try {
        fin >> doc;

        if (doc.contains("freeze") && doc["freeze"].is_object() &&
            doc["freeze"].contains("vertices")) {
            if (!doc["freeze"]["vertices"].is_array()) {
                printf("Error: 'freeze.vertices' must be an array in %s\n", path.c_str());
                return false;
            }
            for (const auto& v : doc["freeze"]["vertices"]) {
                int idx = v.get<int>();
                if (idx < 0 || idx >= nNode) {
                    printf("Error: freeze vertex index %d out of range [0, %d)\n", idx, nNode);
                    return false;
                }
                out.freeze_vertices.push_back(idx);
            }
        }

        std::unordered_set<int> freeze_set(out.freeze_vertices.begin(), out.freeze_vertices.end());
        std::unordered_set<int> seed_set;

        if (!doc.contains("contacts") || !doc["contacts"].is_array() || doc["contacts"].empty()) {
            printf("Error: annotation file must contain a non-empty 'contacts' array\n");
            return false;
        }

        for (const auto& c : doc["contacts"]) {
            ContactSeed cs;
            cs.vertex_index = c.at("seed").get<int>();
            cs.k_ring = c.at("k_ring").get<int>();

            if (cs.vertex_index < 0 || cs.vertex_index >= nNode) {
                printf("Error: contact seed index %d out of range [0, %d)\n", cs.vertex_index,
                       nNode);
                return false;
            }
            if (freeze_set.count(cs.vertex_index)) {
                printf("Error: contact seed %d is also in freeze list\n", cs.vertex_index);
                return false;
            }
            if (seed_set.count(cs.vertex_index)) {
                printf("Error: duplicate contact seed index %d\n", cs.vertex_index);
                return false;
            }
            if (cs.k_ring < 1) {
                printf("Error: k_ring must be >= 1, got %d for seed %d\n", cs.k_ring,
                       cs.vertex_index);
                return false;
            }

            seed_set.insert(cs.vertex_index);
            out.contacts.push_back(cs);
        }
    } catch (const nlohmann::json::exception& e) {
        printf("Error: invalid annotation JSON in %s: %s\n", path.c_str(), e.what());
        return false;
    }

    printf("Annotation loaded: %zu freeze vertices, %zu contact seeds\n",
           out.freeze_vertices.size(), out.contacts.size());
    return true;
}

std::vector<int> SelectKRingNeighbors(int seed, int k, const Vertex* vertices, int nNode,
                                      const std::unordered_set<int>& freeze_set) {
    std::unordered_set<int> visited;
    visited.insert(seed);
    std::vector<int> frontier;
    frontier.push_back(seed);

    for (int hop = 0; hop < k; ++hop) {
        std::vector<int> next_frontier;
        for (int v : frontier) {
            for (int u : vertices[v].neighborVertex) {
                if (u >= 0 && u < nNode && visited.find(u) == visited.end()) {
                    visited.insert(u);
                    next_frontier.push_back(u);
                }
            }
        }
        frontier = std::move(next_frontier);
    }

    std::vector<int> result;
    result.reserve(visited.size());
    for (int v : visited) {
        if (freeze_set.find(v) == freeze_set.end()) {
            result.push_back(v);
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::vector<std::vector<int>> PrecomputeContactRegions(const AnnotationData& annotation,
                                                       const Vertex* vertices, int nNode) {
    std::unordered_set<int> freeze_set(annotation.freeze_vertices.begin(),
                                       annotation.freeze_vertices.end());

    std::vector<std::vector<int>> regions;
    regions.reserve(annotation.contacts.size());

    for (size_t i = 0; i < annotation.contacts.size(); ++i) {
        const ContactSeed& cs = annotation.contacts[i];
        std::vector<int> region =
            SelectKRingNeighbors(cs.vertex_index, cs.k_ring, vertices, nNode, freeze_set);
        printf("  Contact seed %d (k=%d): %zu vertices in region\n", cs.vertex_index, cs.k_ring,
               region.size());
        regions.push_back(std::move(region));
    }

    return regions;
}
