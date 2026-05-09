#include "mvrmesh/core/surface_acceptance.h"

#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace mvrmesh {

SurfaceAcceptanceResult evaluate_surface_acceptance(
    const SurfaceMetrics& metrics,
    const SurfaceAcceptanceOptions& options) {
    std::vector<std::string> failures;
    if (options.require_no_degenerate_faces && metrics.degenerate_face_count != 0) {
        failures.push_back("degenerate_face_count=" + std::to_string(metrics.degenerate_face_count));
    }
    if (options.require_closed && metrics.boundary_edge_count != 0) {
        failures.push_back("boundary_edge_count=" + std::to_string(metrics.boundary_edge_count));
    }
    if (options.require_manifold && metrics.non_manifold_edge_count != 0) {
        failures.push_back("non_manifold_edge_count=" + std::to_string(metrics.non_manifold_edge_count));
    }
    if (options.require_consistent_orientation && metrics.inconsistent_orientation_edge_count != 0) {
        failures.push_back(
            "inconsistent_orientation_edge_count=" + std::to_string(metrics.inconsistent_orientation_edge_count));
    }
    if (options.require_single_component && metrics.connected_component_count != 1) {
        failures.push_back("connected_component_count=" + std::to_string(metrics.connected_component_count));
    }

    SurfaceAcceptanceResult result;
    result.accepted = failures.empty();
    if (!result.accepted) {
        std::ostringstream oss;
        oss << "surface gate failed: ";
        for (std::size_t i = 0; i < failures.size(); ++i) {
            if (i > 0) {
                oss << ", ";
            }
            oss << failures[i];
        }
        result.failure_reason = oss.str();
    }

    return result;
}

FemBudgetResult classify_fem_budget(
    bool tetgen_success,
    std::size_t v_tet,
    const FemBudgetOptions& options) {
    if (options.max_review_v_tet < options.max_recommended_v_tet) {
        throw std::runtime_error(
            "max_review_v_tet must be greater than or equal to max_recommended_v_tet");
    }
    FemBudgetResult result;
    result.max_recommended_v_tet = options.max_recommended_v_tet;
    result.max_review_v_tet = options.max_review_v_tet;
    if (!tetgen_success) {
        result.classification = FemBudgetClassification::PressureFailed;
        return result;
    }
    if (v_tet <= options.max_recommended_v_tet) {
        result.classification = FemBudgetClassification::Recommended;
        result.recommended = true;
        result.reviewable = true;
    } else if (v_tet <= options.max_review_v_tet) {
        result.classification = FemBudgetClassification::Review;
        result.reviewable = true;
    } else {
        result.classification = FemBudgetClassification::OverBudget;
    }
    return result;
}

std::string fem_budget_classification_to_string(FemBudgetClassification classification) {
    if (classification == FemBudgetClassification::PressureFailed) {
        return "pressure_failed";
    }
    if (classification == FemBudgetClassification::Recommended) {
        return "recommended";
    }
    if (classification == FemBudgetClassification::Review) {
        return "review";
    }
    if (classification == FemBudgetClassification::OverBudget) {
        return "over_budget";
    }
    return "pressure_failed";
}

}  // namespace mvrmesh
