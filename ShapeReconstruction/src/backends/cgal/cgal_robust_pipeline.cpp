#include "mvrmesh/backends/cgal/cgal_robust_pipeline.h"

#if MVRMESH_CGAL_PMP_ENABLED

#include <stdexcept>

namespace mvrmesh {

RobustPipelineResult run_cgal_robust_pipeline(
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/,
    const RobustPipelineOptions& /*options*/) {
    throw std::runtime_error("run_cgal_robust_pipeline: not implemented yet");
}

namespace detail {

RepairStepIO repair_polygon_soup_step(
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/) {
    throw std::runtime_error("repair_polygon_soup_step: not implemented yet");
}

ProtectedRemeshStepIO protected_remesh_step(
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/,
    double /*sharp_edge_dihedral_degrees*/,
    double /*target_edge_length*/,
    int    /*remesh_iterations*/) {
    throw std::runtime_error("protected_remesh_step: not implemented yet");
}

SimplifyToBudgetStepIO simplify_to_budget_step(
    const std::vector<Vec3>& /*vertices*/,
    const std::vector<Face>& /*faces*/,
    std::size_t /*max_dense_kl_bytes*/,
    double      /*safety_margin*/) {
    throw std::runtime_error("simplify_to_budget_step: not implemented yet");
}

}  // namespace detail
}  // namespace mvrmesh

#endif  // MVRMESH_CGAL_PMP_ENABLED
