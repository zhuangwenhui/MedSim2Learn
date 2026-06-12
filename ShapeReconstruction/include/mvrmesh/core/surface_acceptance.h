#pragma once

#include <cstddef>
#include <string>

#include "mvrmesh/core/metrics.h"

namespace mvrmesh {

// Which surface defects veto acceptance; each flag enables one check against the
// corresponding SurfaceMetrics counter.
struct SurfaceAcceptanceOptions {
    bool require_no_degenerate_faces = true;
    bool require_closed = true;
    bool require_manifold = true;
    bool require_consistent_orientation = true;
    bool require_single_component = true;
};

// Outcome of the surface gate. When not accepted, failure_reason lists every
// failing counter as "surface gate failed: key=value, ..."; empty otherwise.
struct SurfaceAcceptanceResult {
    bool accepted = false;
    std::string failure_reason;
};

// Tet-mesh vertex-count thresholds for FEM budget classification.
struct FemBudgetOptions {
    std::size_t max_recommended_v_tet = 3000;
    std::size_t max_review_v_tet = 5000;
};

// FEM budget verdict for a tetrahedralized surface, from tetrahedralization
// failure through progressively larger vertex counts.
enum class FemBudgetClassification {
    PressureFailed,
    Recommended,
    Review,
    OverBudget,
};

// Returns the snake_case label used in JSON and summary output. Keep classification
// in a typed enum and map to strings only through this helper.
std::string fem_budget_classification_to_string(FemBudgetClassification classification);

// Budget verdict plus the convenience flags derived from it and the thresholds the
// classification was made against.
struct FemBudgetResult {
    FemBudgetClassification classification = FemBudgetClassification::PressureFailed;
    bool recommended = false;
    bool reviewable = false;
    std::size_t max_recommended_v_tet = 0;
    std::size_t max_review_v_tet = 0;
};

// Checks `metrics` against every enabled requirement. Failing checks do not throw;
// they are reported together through SurfaceAcceptanceResult::failure_reason.
SurfaceAcceptanceResult evaluate_surface_acceptance(
    const SurfaceMetrics& metrics,
    const SurfaceAcceptanceOptions& options = {});

// Classifies a tet mesh by vertex count: Recommended when v_tet is at most
// max_recommended_v_tet, Review up to max_review_v_tet, OverBudget above that, and
// PressureFailed when the TetGen run itself failed. Throws std::runtime_error if
// max_review_v_tet < max_recommended_v_tet.
FemBudgetResult classify_fem_budget(
    bool tetgen_success,
    std::size_t v_tet,
    const FemBudgetOptions& options = {});

}  // namespace mvrmesh
