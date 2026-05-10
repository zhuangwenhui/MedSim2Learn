# 2026-05-10 Maintenance Log

## Scope

This log records three maintenance events on 2026-05-10:

1. Config-driven CLI refactoring -- introduce YAML config files and three-layer merge for `mvr_to_mesh_cli`.
2. Code simplification -- deduplicate shared utilities, extract test helpers, add readability comments.
3. Scaffolding cleanup -- remove historical race outputs, planning documents, and restructure `outPut/`.

Input fixture for hash verification: `originalData/MVR/kidney.mvr`.

## Event 1: Config-Driven CLI Refactoring

### Decision

- Extract `PipelineConfig` and `PressureConfig` structs with per-mode sub-configs into a dedicated `config/` module.
- Introduce `load_config_from_yaml` for YAML-based configuration.
- Implement three-layer merge in `load_config`: hardcoded defaults -> YAML file (`--config`) -> CLI flag overrides.
- Add `--mode` flag for explicit mode selection alongside legacy boolean flags (`--adaptive-remesh`, `--uniform-subdivide --taubin-smooth`, etc.).
- Create 7 user-facing YAML config files in `configs/` covering all main-flow modes.
- Split CLI infrastructure into `cli/cli_common.h` (path resolution, output writing, logging).
- Build `mvrmesh_config` as a separate static library that links yaml-cpp PRIVATE so the core `mvrmesh` library has zero yaml-cpp dependency.

### New Module Structure

```
include/mvrmesh/config/     # PipelineConfig, PressureConfig, config_loader
include/mvrmesh/cli/        # Shared CLI infrastructure
include/mvrmesh/pressure/   # pressure_metrics (separated from core)
src/config/                  # config_loader.cpp, pipeline_config.cpp, pressure_config.cpp
src/cli/                     # cli_common.cpp
src/pressure/                # pressure_metrics.cpp
configs/                     # 7 user-facing YAML config files
```

### Config Files

| File | Mode | Key parameters |
|---|---|---|
| `configs/direct_surface.yaml` | `direct_surface` | (none) |
| `configs/adaptive_remesh.yaml` | `adaptive_remesh` | iterations=1, split_ratio=0.5 |
| `configs/uniform_subdivide.yaml` | `uniform_subdivide` | iterations=1 |
| `configs/uniform_taubin.yaml` | `uniform_taubin` | uniform iterations=2, taubin iterations=8, lambda=0.5, mu=-0.53 |
| `configs/sdf_reconstruct.yaml` | `sdf_reconstruct` | resolution=72, target_edge_length=0.025, remesh_iterations=3 |
| `configs/sdf_highest_precision.yaml` | `sdf_reconstruct` | resolution=96, target_edge_length=0, remesh_iterations=3 |
| `configs/cgal_mesh.yaml` | `direct_surface` + cgal_mesh_post | sharp_edge=60, remesh_iterations=3 |

### Verification Notes

- CTest full suite: 24/24 passed.
- Config loader unit tests: YAML parsing, CLI args, legacy flag resolution, YAML+CLI override merge.
- CLI integration tests: `--config`, `--config` + CLI override, `--mode` flag.

## Event 2: Code Simplification

### Decision

Consolidate duplicated utilities across core modules before hardening the project. Three tiers of changes, each behavior-preserving:

- **Tier 1**: Extract `make_edge_key`, `triangle_area`, `closest_point_on_triangle` into `geometry.h/cpp`. Removes ~200 lines of duplication across 5 files (metrics, smoothing, quality_metrics, curvature, subdivision).
- **Tier 2**: Extract `extract_faces_from_cgal_mesh` helper in `cgal_mesh.cpp`. Add 7 readability comments for non-obvious algorithms (Taubin alternating passes, marching-tetrahedra cube decomposition, SDF grid sign convention, boundary detection, etc.).
- **Tier 3**: Replace if-chain with switch in `fem_budget_classification_to_string`. Extract shared test helpers (`require`, `near`, `require_vec3_near`, `run_tests`) into `verification/test_helpers.h`.

### Files Modified

Tier 1 (geometry extraction):

- `include/mvrmesh/core/geometry.h` -- added 3 new public declarations.
- `src/core/geometry.cpp` -- added implementations + internal helpers (`clamp01`, `segment_param`, `closest_on_segment`).
- `src/core/curvature.cpp` -- removed local `make_edge_key` (6 lines).
- `src/core/metrics.cpp` -- removed local `make_edge_key` + `triangle_area` (9 lines).
- `src/core/quality_metrics.cpp` -- removed `make_edge_key`, `triangle_area`, `clamp01`, `segment_parameter_clamped`, `closest_point_to_segment`, `closest_point_on_triangle_distance` (~80 lines).
- `src/core/smoothing.cpp` -- removed `make_edge_key`, `clamp01`, `segment_parameter_clamped`, `closest_point_to_segment`, `closest_point_on_triangle` (~90 lines).
- `src/core/subdivision.cpp` -- removed local `make_edge_key` (6 lines).

Tier 2 (CGAL dedup + comments):

- `src/backends/cgal/cgal_mesh.cpp` -- extracted `extract_faces_from_cgal_mesh` helper.
- `src/core/reconstruction.cpp` -- 2 comments (cube decomposition, SDF grid).
- `src/core/topology.cpp` -- 2 comments (boundary detection, face orientation).
- `src/core/smoothing.cpp` -- 1 comment (Taubin alternating passes).
- `src/core/quality_metrics.cpp` -- 1 comment (acos stability).
- `src/core/reconstruction.cpp` -- 1 comment (marching-tetrahedra cut cases).

Tier 3 (test helpers + switch):

- `src/core/surface_acceptance.cpp` -- switch statement for enum-to-string.
- `verification/test_helpers.h` -- new shared test utilities.
- 6 test files updated to use shared helpers.
- `cmake/MvrmeshTests.cmake` -- added `MVRMESH_TEST_INCLUDE_DIR` for all 6 test targets.

### Verification Notes

- CTest full suite after all 3 tiers: 24/24 passed.
- SHA256 hash verification against `outPut/closure_baseline/` (7/7 MATCH):

| Output | SHA256 | Result |
|---|---|---|
| `kidney_direct.ply` | `4F2F4D71764F3BDE...CBFC82` | MATCH |
| `kidney_adaptive.ply` | `C6C07A8457395EB9...991C` | MATCH |
| `kidney_uniform.ply` | `62D36392426B6354...EC7BF` | MATCH |
| `kidney_uniform_taubin.ply` | `840BB5A7111AA654...6EA9BB` | MATCH |
| `kidney_sdf_reconstruct.ply` | `02881BFFF78A1082...CE89B` | MATCH |
| `kidney_sdf96_highest_precision.ply` | `7D29A4BCC7BD3E67...68C5` | MATCH |
| `kidney_cgal.ply` | `3635A4B971DE9D5C...A01E0` | MATCH |

Hash verification used `--config configs/<name>.yaml` for all 7 modes, confirming both code simplification and config-driven CLI produce identical outputs.

## Event 3: Scaffolding Cleanup

### Decision

Remove all historical race-phase artifacts, development planning documents, and temporary validation files. Restructure `outPut/` for production use.

### Cleanup Record

Removed race output directories (~19.3 MB):

- `outPut/race/kidney_u2/` (6 files, 1.2 MB)
- `outPut/race/kidney_alpha_wrap/` (18 files, 0.9 MB)
- `outPut/race/kidney_decimation/` (2 files, <0.1 MB)
- `outPut/race/kidney_budget/` (18 files, 3.5 MB)
- `outPut/race/kidney_recon_sdf/` (4 files, 9.2 MB)
- `outPut/race/kidney_multi_track/` (35 files, 4.5 MB)

Removed planning documents (32 files):

- `docs/superpowers/specs/ShapeReconstruction/` (15 files)
- `docs/superpowers/plans/ShapeReconstruction/` (10 files)
- `docs/superpowers/specs/DeformSim/` (1 file)
- `docs/superpowers/plans/DeformSim/` (1 file)
- Root-level plans (2 files)
- `docs/verification/ShapeReconstruction/` (4 race roster files)

Removed build validation artifacts:

- `build/validation/robust-pipeline-roster.md`
- `build/validation/robust-pipeline-evidence.md`

Removed regenerable cache:

- `.graphify_python`

### Directory Restructure

Before:

```
outPut/
  race/
    closure/          # 7 PLY baselines + ACCEPTANCE_REPORT.md
    kidney_u2/        # (removed)
    kidney_alpha_wrap/ # (removed)
    ...
  PLY/                # production output
```

After:

```
outPut/
  closure_baseline/   # 7 PLY baselines + ACCEPTANCE_REPORT.md (renamed from race/closure)
  PLY/                # production output
```

Workflow: run `mvr_to_mesh_cli` with `--config configs/<name>.yaml`, output to `outPut/PLY/`. The `closure_baseline/` directory serves as the hash-verified reference set for behavioral equivalence testing. Pressure testing with `check_fem_pressure` takes any `.ply` from `outPut/` as input.

### Verification Notes

- Updated `ACCEPTANCE_REPORT.md` path references from `outPut/race/closure` to `outPut/closure_baseline`.
- Refreshed graphify knowledge graph: 545 nodes, 1070 edges, 54 communities.
- Confirmed no active source/CMake/test paths reference the removed `outPut/race/` directories.
- Deleted files are all gitignored or untracked; no git history impact.
