#pragma once

#include <array>
#include <cstdio>
#include <string>
#include <vector>

#include "bmgl.h"
#include "sim/annotation.h"
#include "sim/hyper_params.h"
#include "sim/output_writer.h"
#include "sim/sample_pipeline.h"

// Runs the sample-generation loop on `num_threads` worker threads (dynamic
// atomic next-sample dispatch) and joins them before returning. Each worker
// clones the tetra template (or re-tetrahedralizes), applies contact force
// and freeze state, solves the deformation, and writes the verified outputs.
void RunSampleWorkers(unsigned int num_threads, int total_objects, const std::string& dir_path,
                      FILE* diag_fp, OutputStats* output_stats, Surface* surface,
                      const AnnotationData& annotation,
                      const std::vector<std::vector<int>>& contact_regions,
                      const std::vector<std::array<float, 4>>& force_vectors,
                      const SimHyperParams& params, const Object* tetra_template,
                      const Object* matrix_template, const MatrixCacheKey* matrix_cache_key);
