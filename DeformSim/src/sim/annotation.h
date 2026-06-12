#pragma once

#include <string>
#include <unordered_set>
#include <vector>

#include "bmgl.h"

struct ContactSeed {
    int vertex_index;
    int k_ring;
};

struct AnnotationData {
    std::vector<int> freeze_vertices;
    std::vector<ContactSeed> contacts;
};

// Loads freeze vertices and contact seeds (0-based indices) from the
// annotation JSON, validating every index against nNode and rejecting
// duplicate or frozen seeds. Returns false with a printed error on any
// malformed input.
bool LoadAnnotationJSON(const std::string& path, int nNode, AnnotationData& out);

// Breadth-first k-ring expansion around `seed`, excluding frozen vertices;
// the result is sorted ascending.
std::vector<int> SelectKRingNeighbors(int seed, int k, const Vertex* vertices, int nNode,
                                      const std::unordered_set<int>& freeze_set);

// Expands every contact seed into its k-ring vertex region.
std::vector<std::vector<int>> PrecomputeContactRegions(const AnnotationData& annotation,
                                                       const Vertex* vertices, int nNode);
