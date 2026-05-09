#pragma once

#include <cstddef>
#include <string>

#include "mvrmesh/core/metrics.h"

namespace mvrmesh {

struct SurfaceAcceptanceOptions {
    bool require_no_degenerate_faces = true;
    bool require_closed = true;
    bool require_manifold = true;
    bool require_consistent_orientation = true;
    bool require_single_component = true;
};

struct SurfaceAcceptanceResult {
    bool accepted = false;
    std::string failure_reason;
};

struct FemBudgetOptions {
    std::size_t max_recommended_v_tet = 3000;
    std::size_t max_review_v_tet = 5000;
};

enum class FemBudgetClassification {
    PressureFailed,
    Recommended,
    Review,
    OverBudget,
};

// Keep classification in a typed enum and map to JSON/summary strings through this helper.
std::string fem_budget_classification_to_string(FemBudgetClassification classification);

struct FemBudgetResult {
    FemBudgetClassification classification = FemBudgetClassification::PressureFailed;
    bool recommended = false;
    bool reviewable = false;
    std::size_t max_recommended_v_tet = 0;
    std::size_t max_review_v_tet = 0;
};

SurfaceAcceptanceResult evaluate_surface_acceptance(
    const SurfaceMetrics& metrics,
    const SurfaceAcceptanceOptions& options = {});

FemBudgetResult classify_fem_budget(
    bool tetgen_success,
    std::size_t v_tet,
    const FemBudgetOptions& options = {});

}  // namespace mvrmesh
