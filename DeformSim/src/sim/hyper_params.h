#pragma once

#include <string>

// Simulation hyper-parameters, loaded from SIM2LEARN_PARAM_* env vars.
//
// Unit system (consistent mm-MPa-N, inherited from the ShapeReconstruction
// meshes which carry millimetre coordinates):
//   lengths/coordinates  mm
//   material_young       MPa (N/mm^2); kidney production runs use 0.03 MPa
//                        = 30 kPa, in the soft-tissue range
//   material_poisson     dimensionless, valid (-1, 0.5); 0.40 for kidney
//   forces               N (per-vertex nodal forces; force_*_min/max bound
//                        the sampled total contact force components)
//   angles               degrees, measured from the -z axis (contact cone)
// The angle window [min_angle_deg, max_angle_deg] restricts sampled force
// directions to a downward cone; values still need literature endorsement.
struct SimHyperParams {
    float material_young = 1.0f;
    float material_poisson = 0.40f;

    std::string ply_path = "./plate.ply";
    std::string annotation_path = "./annotation.json";
    // Optional explicit force list (bare "fx,fy,fz" CSV, no header). When set,
    // these vectors replace random+cone sampling for exact per-frame replay.
    std::string force_list_csv = "";

    int num_vector = 100;
    unsigned int seed = 20260328u;
    float force_x_min = -10.0f;
    float force_x_max = 10.0f;
    float force_y_min = -10.0f;
    float force_y_max = 10.0f;
    float force_z_min = -100.0f;
    float force_z_max = -0.1f;
    float min_angle_deg = 0.0f;
    float max_angle_deg = 45.0f;

    bool use_reuse_tetra_template = true;
    bool use_solver_lu = true;
    bool use_matrix_solver_cache = true;
    bool use_skip_normal_area = true;
    bool use_diag_contact_hash = false;
    bool isolate_output = true;
    int max_objects = 0;
    unsigned int num_threads = 4;
    unsigned int mkl_num_threads = 1;
    int diag_flush_interval = 32;
};

// Reads every SIM2LEARN_PARAM_* variable (with legacy fallbacks), validates
// ranges, and falls back to defaults with a printed warning on invalid input.
SimHyperParams LoadSimHyperParams();

// Derives the MKL thread count (auto when mkl_num_threads == 0), warns on
// oversubscription, and applies it through the MKL service API.
unsigned int ConfigureMklThreads(const SimHyperParams& params, unsigned int app_threads,
                                 unsigned int hardware_threads, bool& auto_derived);
