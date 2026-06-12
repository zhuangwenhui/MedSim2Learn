#pragma once

#include <array>
#include <memory>
#include <vector>

#include "sim/hyper_params.h"

// Seeds the dedicated force-sampling RNG (call once before generateVectors).
void SeedForceRng(unsigned int seed);

float RandomFloat(float min, float max);
float ComputeForceEuclidean(float x, float y, float z);
float AngleWithZAxis(float x, float y, float z);

// Produces the per-frame force vectors {fx, fy, fz, norm}. Sampling mode draws
// from the force box restricted to the [min, max] angle cone; replay mode
// (params.force_list_csv set) parses the CSV verbatim and updates
// params.num_vector to the row count. Returns nullptr on failure.
std::unique_ptr<std::vector<std::array<float, 4>>> generateVectors(SimHyperParams& params);

// Formats the canonical sample identifier "deformed_s%04d_v%04d".
void CreateSampleID(char* sampleID, int seed_vertex, int vec_i);
