// Environment-variable configuration loading for the sample generator.
#include "sim/hyper_params.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "mkl.h"

static bool ParseBoolStrict(const char* raw, bool& value) {
    if (raw == NULL || raw[0] == '\0') return false;
    if (strcmp(raw, "0") == 0) {
        value = false;
        return true;
    }
    if (strcmp(raw, "1") == 0) {
        value = true;
        return true;
    }
    return false;
}

static bool ParseFloatStrict(const char* raw, float& value) {
    if (raw == NULL || raw[0] == '\0') return false;
    char* endPtr = NULL;
    float parsed = strtof(raw, &endPtr);
    // Reject nan/inf: every range check downstream is NaN-transparent.
    if (endPtr != raw && *endPtr == '\0' && std::isfinite(parsed)) {
        value = parsed;
        return true;
    }
    return false;
}

static bool ParseIntStrict(const char* raw, int& value) {
    if (raw == NULL || raw[0] == '\0') return false;
    char* endPtr = NULL;
    long parsed = strtol(raw, &endPtr, 10);
    if (endPtr != raw && *endPtr == '\0') {
        value = static_cast<int>(parsed);
        return true;
    }
    return false;
}

static bool ParseUIntStrict(const char* raw, unsigned int& value) {
    if (raw == NULL || raw[0] == '\0') return false;
    char* endPtr = NULL;
    unsigned long parsed = strtoul(raw, &endPtr, 10);
    if (endPtr != raw && *endPtr == '\0') {
        value = static_cast<unsigned int>(parsed);
        return true;
    }
    return false;
}

static const char* PickEnv(const char* primary, const char* legacy) {
    const char* value = getenv(primary);
    if (value != NULL && value[0] != '\0') return value;
    if (legacy != NULL) {
        value = getenv(legacy);
        if (value != NULL && value[0] != '\0') return value;
    }
    return NULL;
}

static void LoadBoolParam(bool& target, const char* primary, const char* legacy = NULL) {
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    bool parsed = target;
    if (ParseBoolStrict(raw, parsed)) {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n", primary,
           (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadFloatParam(float& target, const char* primary, const char* legacy = NULL) {
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    float parsed = target;
    if (ParseFloatStrict(raw, parsed)) {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n", primary,
           (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadIntParam(int& target, const char* primary, const char* legacy = NULL,
                         bool require_positive = false) {
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    int parsed = target;
    if (ParseIntStrict(raw, parsed) && (!require_positive || parsed > 0)) {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n", primary,
           (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadUIntParam(unsigned int& target, const char* primary, const char* legacy = NULL) {
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    unsigned int parsed = target;
    if (ParseUIntStrict(raw, parsed)) {
        target = parsed;
        return;
    }
    printf("Warning: invalid %s%s%s=%s, fallback to default\n", primary,
           (legacy != NULL) ? " / " : "", (legacy != NULL) ? legacy : "", raw);
}

static void LoadStringParam(std::string& target, const char* primary, const char* legacy = NULL) {
    const char* raw = PickEnv(primary, legacy);
    if (raw == NULL) return;
    target = raw;
}

SimHyperParams LoadSimHyperParams() {
    SimHyperParams params;

    LoadFloatParam(params.material_young, "SIM2LEARN_PARAM_MATERIAL_YOUNG");
    LoadFloatParam(params.material_poisson, "SIM2LEARN_PARAM_MATERIAL_POISSON");

    LoadStringParam(params.ply_path, "SIM2LEARN_PARAM_PLY_PATH");
    LoadStringParam(params.annotation_path, "SIM2LEARN_PARAM_ANNOTATION_PATH");
    LoadStringParam(params.force_list_csv, "SIM2LEARN_PARAM_FORCE_LIST_CSV");

    LoadIntParam(params.num_vector, "SIM2LEARN_PARAM_NUM_VECTOR", NULL, true);
    LoadUIntParam(params.seed, "SIM2LEARN_PARAM_SEED");
    LoadFloatParam(params.force_x_min, "SIM2LEARN_PARAM_FORCE_X_MIN");
    LoadFloatParam(params.force_x_max, "SIM2LEARN_PARAM_FORCE_X_MAX");
    LoadFloatParam(params.force_y_min, "SIM2LEARN_PARAM_FORCE_Y_MIN");
    LoadFloatParam(params.force_y_max, "SIM2LEARN_PARAM_FORCE_Y_MAX");
    LoadFloatParam(params.force_z_min, "SIM2LEARN_PARAM_FORCE_Z_MIN");
    LoadFloatParam(params.force_z_max, "SIM2LEARN_PARAM_FORCE_Z_MAX");
    LoadFloatParam(params.min_angle_deg, "SIM2LEARN_PARAM_MIN_ANGLE_DEG");
    LoadFloatParam(params.max_angle_deg, "SIM2LEARN_PARAM_MAX_ANGLE_DEG");

    LoadBoolParam(params.use_reuse_tetra_template, "SIM2LEARN_PARAM_USE_REUSE_TETRA_TEMPLATE",
                  "SIM2LEARN_REUSE_TETRA_TEMPLATE");
    LoadBoolParam(params.use_solver_lu, "SIM2LEARN_PARAM_USE_SOLVER_LU", "SIM2LEARN_SOLVER_USE_LU");
    if (!params.use_solver_lu) {
        printf("Warning: SIM2LEARN_PARAM_USE_SOLVER_LU=0 is no longer supported; the LU direct "
               "solver is the only path\n");
        params.use_solver_lu = true;
    }
    LoadBoolParam(params.use_matrix_solver_cache, "SIM2LEARN_PARAM_USE_MATRIX_SOLVER_CACHE",
                  "SIM2LEARN_CACHE_MATRIX_SOLVER");
    LoadBoolParam(params.use_skip_normal_area, "SIM2LEARN_PARAM_SKIP_NORMAL_AREA",
                  "SIM2LEARN_SKIP_NORMAL_AREA");
    LoadBoolParam(params.use_diag_contact_hash, "SIM2LEARN_PARAM_USE_DIAG_CONTACT_HASH",
                  "SIM2LEARN_DIAG_CONTACT_HASH");
    LoadBoolParam(params.isolate_output, "SIM2LEARN_PARAM_ISOLATE_OUTPUT",
                  "SIM2LEARN_ISOLATE_OUTPUT");
    LoadIntParam(params.max_objects, "SIM2LEARN_PARAM_MAX_OBJECTS", "SIM2LEARN_MAX_OBJECTS", true);
    LoadUIntParam(params.mkl_num_threads, "SIM2LEARN_PARAM_MKL_NUM_THREADS",
                  "SIM2LEARN_MKL_NUM_THREADS");
    LoadIntParam(params.diag_flush_interval, "SIM2LEARN_PARAM_DIAG_FLUSH_INTERVAL", NULL, true);
    {
        int parsed_threads = static_cast<int>(params.num_threads);
        LoadIntParam(parsed_threads, "SIM2LEARN_PARAM_NUM_THREADS", "SIM2LEARN_NUM_THREADS", true);
        if (parsed_threads > 0) {
            params.num_threads = static_cast<unsigned int>(parsed_threads);
        }
    }

    if (params.num_vector <= 0) {
        printf("Warning: invalid SIM2LEARN_PARAM_NUM_VECTOR=%d, fallback to default\n",
               params.num_vector);
        params.num_vector = 100;
    }
    if (params.material_young <= 0.0f) {
        printf("Warning: invalid material young=%.3f, fallback to default\n",
               params.material_young);
        params.material_young = 1.0f;
    }
    if (params.material_poisson <= -1.0f || params.material_poisson >= 0.5f) {
        printf("Warning: invalid material poisson=%.3f, fallback to default\n",
               params.material_poisson);
        params.material_poisson = 0.40f;
    }
    if (params.min_angle_deg < 0.0f || params.max_angle_deg < params.min_angle_deg) {
        printf("Warning: invalid angle range [%.3f, %.3f], fallback to default\n",
               params.min_angle_deg, params.max_angle_deg);
        params.min_angle_deg = 0.0f;
        params.max_angle_deg = 45.0f;
    }
    if (params.force_x_min > params.force_x_max) {
        printf("Warning: invalid force X range [%.3f, %.3f], fallback to default\n",
               params.force_x_min, params.force_x_max);
        params.force_x_min = -10.0f;
        params.force_x_max = 10.0f;
    }
    if (params.force_y_min > params.force_y_max) {
        printf("Warning: invalid force Y range [%.3f, %.3f], fallback to default\n",
               params.force_y_min, params.force_y_max);
        params.force_y_min = -10.0f;
        params.force_y_max = 10.0f;
    }
    if (params.force_z_min > params.force_z_max) {
        printf("Warning: invalid force Z range [%.3f, %.3f], fallback to default\n",
               params.force_z_min, params.force_z_max);
        params.force_z_min = -100.0f;
        params.force_z_max = -0.1f;
    }
    if (params.diag_flush_interval <= 0) {
        printf("Warning: invalid diag_flush_interval=%d, fallback to default\n",
               params.diag_flush_interval);
        params.diag_flush_interval = 32;
    }

    return params;
}

unsigned int ConfigureMklThreads(const SimHyperParams& params, unsigned int app_threads,
                                 unsigned int hardware_threads, bool& auto_derived) {
    auto_derived = (params.mkl_num_threads == 0);
    unsigned int derived = params.mkl_num_threads;
    if (derived == 0) {
        // Avoid over-subscription: when app is already parallel, keep MKL single-threaded.
        derived = (app_threads > 1) ? 1u : std::max(1u, hardware_threads / 2u);
    }

    if (derived > hardware_threads) derived = hardware_threads;
    if (derived == 0) derived = 1u;

    if (!auto_derived && app_threads * derived > hardware_threads) {
        printf("Warning: thread oversubscription: %u app threads x %u MKL threads exceeds %u "
               "hardware threads\n",
               app_threads, derived, hardware_threads);
    }

    // Control MKL through its own service API only: the previous omp_set_*
    // calls bound to the compiler's OpenMP runtime (vcomp), not to MKL's
    // libiomp5md, and linking both runtimes is an Intel-documented hazard.
    mkl_set_dynamic(0);
    mkl_set_num_threads(static_cast<int>(derived));
    return derived;
}
