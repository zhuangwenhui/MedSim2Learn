# 2026-05-09 Maintenance Log

## Scope

This daily log consolidates the three ShapeReconstruction maintenance records created on 2026-05-09.

Merged source logs:

- `2026-05-09-mesh-in-place-merge.md`
- `2026-05-09-reconstruction-budget-merge.md`
- `2026-05-09-sdf-mainflow-closure.md`

The source files were removed after this consolidation so future maintenance work has one date-level record instead of several partially overlapping records.

## Event 1: Mesh-in-place Merge Closure

### Scope

This event records the closure step that folds the accepted mesh-in-place Taubin path into `mvr_to_mesh_cli`, then removes the temporary `mesh_race_cli` experiment entry.

### Decision

- Keep `uniform_taubin` as the only mesh-in-place race candidate promoted into the main flow.
- Treat `u2_control` as a duplicate of `mvr_to_mesh_cli --uniform-subdivide`.
- Treat `u2_repair_remesh` as a duplicate combination of already available `uniform_subdivide` and `cgal_mesh` building blocks; do not preserve its race name as a product algorithm.
- Treat `u2_taubin_project` as a technical reserve. It is distinct, but it was not selected because visual review preferred `u2_taubin` and projection adds an extra shape-error path.
- Remove `mesh_race_cli` and `race_candidates` after `mvr_to_mesh_cli` can produce the accepted Taubin output.

### Artifact Roster

| Path | Purpose | Owner | Cleanup expectation |
|---|---|---|---|
| `maintainLogs/2026-05-09-maintenance-log.md` | Consolidated permanent decision, verification, and cleanup record for 2026-05-09. | Main Agent | Keep in repository. |
| `../build/ShapeReconstruction/vs2022-x64/tiny_taubin.ply` | CTest output for the new main-flow Taubin CLI mode. | Main Agent | Build artifact; may be removed by future build cleanup. |
| `../build/ShapeReconstruction/vs2022-x64/tiny_taubin_manual.ply` | Manual positive CLI check output for `--uniform-subdivide --taubin-smooth`. | Main Agent | Build artifact; may be removed by future build cleanup. |
| `../build/ShapeReconstruction/vs2022-x64/mesh_budget_race_cli_test/` | Existing budget race smoke output used at that time to confirm cleanup did not break the maintained reconstruction race. | Main Agent | Historical build artifact; may be removed by future build cleanup. |

### Implementation Checklist

- Add `mvr_to_mesh_cli --taubin-smooth` after `--uniform-subdivide`.
- Add Taubin tuning flags while keeping the verified defaults from the race: iterations 8, lambda 0.5, mu -0.53, preserve boundary enabled.
- Reject `--taubin-smooth` unless `--uniform-subdivide` is enabled.
- Remove the temporary mesh race executable, candidate generator, and CTest driver.
- Preserve rejected race candidates in this log as technical reserve notes.

### Technical Reserve

- `u2_control`: duplicate of uniform subdivision. Use `mvr_to_mesh_cli --uniform-subdivide` instead.
- `u2_repair_remesh`: duplicate composition of uniform subdivision followed by CGAL repair/remesh. Keep the idea as a future product option only if a real workflow needs chained uniform + CGAL.
- `u2_taubin_project`: Taubin plus closest-point projection back to the reference surface. Keep as a reserve idea, but do not promote now because the selected visual result was `u2_taubin`.

### Cleanup Record

- Promoted `u2_taubin` into the main CLI as `mvr_to_mesh_cli --uniform-subdivide --taubin-smooth`.
- Removed the temporary first-round mesh-in-place race entry:
  - `mesh_race_cli.cpp`
  - `include/mvrmesh/core/race_candidates.h`
  - `src/core/race_candidates.cpp`
  - `verification/cmake/run_mesh_race_cli.cmake`
- Removed the temporary CMake target and CTest entry for `mesh_race_cli`.
- Removed `race_candidates` tests from `mvrmesh_quality_smoothing_tests`; retained budget race tests because `mesh_budget_race_cli` was still the active reconstruction-race entry at this merge step.
- Updated `README.md` to describe the accepted main-flow Taubin path and to point historical candidates to this maintain log.

### Verification Notes

2026-05-09 final verification:

- Built `mvrmesh_smoke_tests` with Visual Studio MSBuild: exit 0.
- Built `mvrmesh_quality_smoothing_tests` with Visual Studio MSBuild: exit 0.
- Built `mvr_to_mesh_cli` with Visual Studio MSBuild: exit 0.
- Built `mesh_budget_race_cli` with Visual Studio MSBuild: exit 0.
- Ran `mvrmesh_smoke_tests.exe`: `[ok] smoke tests passed`.
- Ran `mvrmesh_quality_smoothing_tests.exe`: `[ok] quality/smoothing tests passed`.
- Ran positive manual CLI check:
  - Command shape: `mvr_to_mesh_cli verification/fixtures/tiny_surface.mvr --uniform-subdivide --uniform-iterations 1 --taubin-smooth --taubin-iterations 2`.
  - Result: exit 0; mode `uniform_taubin`; output vertices 10, faces 16.
- Ran negative manual CLI check:
  - Command shape: `mvr_to_mesh_cli verification/fixtures/tiny_surface.mvr --taubin-smooth`.
  - Result: expected exit 1; message `--taubin-smooth requires --uniform-subdivide`.
- Ran CTest subset:
  - `mvrmesh_cli_uniform_taubin`: passed.
  - `mvrmesh_cli_taubin_requires_uniform_subdivide`: passed.
  - `mesh_budget_race_cli_tiny_skip_pressure`: passed.
- Deleted file audit:
  - `include/mvrmesh/core/race_candidates.h` => `False`.
  - `src/core/race_candidates.cpp` => `False`.
  - `mesh_race_cli.cpp` => `False`.
  - `verification/cmake/run_mesh_race_cli.cmake` => `False`.
- Removed-symbol scan:
  - Active source/CMake/test paths no longer reference `mesh_race_cli`, `mvrmesh/core/race_candidates`, `generate_race_candidates`, `RaceCandidateOptions`, or `u2_`.
  - The only non-maintainLog hit was the README historical note that the CLI was removed.
  - `budget_race_candidates` hits remained by design at this merge step because the closed FEM-budget reconstruction race was still active.
- `git diff --check`: exit 0. Git printed line-ending normalization warnings only.

### Superseded Reconstruction Entry Note

This event happened while `mesh_budget_race_cli` was still the maintained reconstruction-race entry. That entry was later superseded by `mvr_to_mesh_cli --sdf-reconstruct`, and `mesh_budget_race_cli` was removed from active code in Event 3.

## Event 2: Reconstruction / Budget Merge

### Scope

This event records the closure step that merges the verified SDF reconstruction reference path into the then-maintained `mesh_budget_race_cli` race entry, then removes the temporary `mesh_recon_race_cli` experiment entry.

### Decision

- Keep the SDF reconstruction core (`reconstruct_surface_sdf`) because it is the base capability behind both the budget race and the visually best reconstruction result.
- Keep the `recon_sdf96_remesh.ply` capability as the "Highest Precision Reference" path.
- Do not rank the highest-precision reference as a FEM-budget candidate. It is intentionally compute-heavy and exists as a visual/geometry ceiling for later comparison.
- Remove the standalone reconstruction race CLI after the reference path can be reproduced from `mesh_budget_race_cli`.

### Artifact Roster

| Path | Purpose | Owner | Cleanup expectation |
|---|---|---|---|
| `maintainLogs/2026-05-09-maintenance-log.md` | Consolidated permanent decision, verification, and cleanup record for 2026-05-09. | Main Agent | Keep in repository. |
| `../build/ShapeReconstruction/vs2022-x64/mesh_budget_race_cli_test` | CTest output for budget CLI tiny fixture. | Main Agent | Historical build artifact; may be removed by future build cleanup. |
| `../build/ShapeReconstruction/vs2022-x64/mesh_budget_race_cli_failure_test` | CTest output for controlled budget candidate failure. | Main Agent | Historical build artifact; may be removed by future build cleanup. |

### Implementation Checklist

- Add a budget-library helper for the highest-precision SDF + CGAL remesh reference path.
- Add `mesh_budget_race_cli --highest-precision` and `--highest-precision-resolution`.
- Write the reference as a separate metrics/summary section, not as a budget-ranked candidate.
- Remove the temporary reconstruction race CLI, CMake target, CTest driver, and dedicated recon race candidate helper.
- Preserve the historical result name `recon_sdf96_remesh.ply` in documentation as the proven visual reference.

### Verification Notes

- RED check: `MSBuild.exe ../build/ShapeReconstruction/vs2022-x64/mvrmesh_quality_smoothing_tests.vcxproj /p:Configuration=Debug /p:Platform=x64` failed before implementation because `HighestPrecisionReferenceOptions` and `generate_highest_precision_reference_candidate` were missing.
- GREEN check: the same `mvrmesh_quality_smoothing_tests` target built successfully after implementation.
- GREEN check: `Debug/mvrmesh_quality_smoothing_tests.exe` completed with `[ok] quality/smoothing tests passed`.
- GREEN check: `mesh_budget_race_cli` built successfully after adding `--highest-precision`.
- GREEN check: `verification/cmake/run_mesh_budget_race_cli.cmake` passed when invoked with the Visual Studio bundled `cmake.exe`; it validated the budget candidates plus the separate `highest_precision_reference` block.
- Cleanup check: `Test-Path` confirmed the removed reconstruction race files are absent.
- Cleanup check: `rg "mesh_recon_race_cli|recon_race_candidates|ReconRace|generate_recon_race_candidates"` only found the maintenance log.
- Formatting check: `git diff --check` exited with code 0; Git reported existing LF-to-CRLF warnings but no whitespace errors.
- Environment note: plain `cmake` and `ctest` were not available in PATH; validation used the Visual Studio bundled `MSBuild.exe` and `cmake.exe`.

### Cleanup Record

Removed from active code path after successful migration:

- `mesh_recon_race_cli.cpp`
- `include/mvrmesh/core/recon_race_candidates.h`
- `src/core/recon_race_candidates.cpp`
- `verification/cmake/run_mesh_recon_race_cli.cmake`
- `mesh_recon_race_cli` CMake target
- `mesh_recon_race_cli_tiny_skip_pressure` CTest entry

Kept at this event point:

- `src/core/reconstruction.cpp`
- `include/mvrmesh/core/reconstruction.h`
- `budget_race_candidates` SDF + CGAL remesh path
- Historical artifact references for `recon_sdf96_remesh.ply`

### Superseded On 2026-05-09

The temporary `mesh_budget_race_cli` entry and `budget_race_candidates` helper were later superseded by the product mainflow mode `mvr_to_mesh_cli --sdf-reconstruct`. Historical notes above are preserved as migration history, but they no longer describe the current maintained entry.

## Event 3: SDF Mainflow Closure

### Scope

This event tracks the final migration of the accepted closed FEM-budget SDF reconstruction path into `mvr_to_mesh_cli`, followed by deletion of the temporary `mesh_budget_race_cli` race entry.

### Decision

- Promote the accepted budget race family into a product mainflow mode: `mvr_to_mesh_cli --sdf-reconstruct`.
- Use `budget_sdf72_L025` as the product default parameter set.
- Preserve the highest-precision SDF96 + auto-CGAL-remesh reference through explicit `mvr_to_mesh_cli` parameters rather than through a race CLI.
- Keep `check_fem_pressure` as the FEM pressure evaluation entry.
- Delete `mesh_budget_race_cli`, `budget_race_candidates`, and their dedicated CTest driver after the mainflow mode is verified.

### Artifact Roster

| Path | Purpose | Owner | Cleanup expectation |
|---|---|---|---|
| `maintainLogs/2026-05-09-maintenance-log.md` | Consolidated permanent migration and cleanup record for 2026-05-09. | Main Agent | Keep in repository. |
| `../docs/superpowers/specs/ShapeReconstruction/2026-05-09-shapereconstruction-sdf-mainflow-closure-design.md` | Design record for this closure. | Main Agent | Keep in repository docs. |
| `../docs/superpowers/plans/ShapeReconstruction/2026-05-09-shapereconstruction-sdf-mainflow-closure.md` | Implementation plan for this closure. | Main Agent | Keep in repository docs. |
| `../build/ShapeReconstruction/vs2022-x64/tiny_sdf_manual.ply` | Manual CLI positive check output. | Main Agent | Build artifact; may be removed by future build cleanup. |
| `../build/ShapeReconstruction/vs2022-x64/tiny_sdf_manual_2.ply` | Repeat manual CLI positive check output after final integration. | Main Agent | Build artifact; may be removed by future build cleanup. |
| `../build/ShapeReconstruction/vs2022-x64/tiny_sdf_reconstruct.ply` | CTest output for the mainflow SDF CLI mode. | Main Agent | Build artifact; may be removed by future build cleanup. |

### Implementation Notes

- Added product helper:
  - `include/mvrmesh/core/reconstruction_pipeline.h`
  - `src/core/reconstruction_pipeline.cpp`
- Added `mvr_to_mesh_cli --sdf-reconstruct` mainflow mode through `BuildOptions` and `build_surface`.
- Added SDF tuning flags:
  - `--sdf-resolution`
  - `--sdf-padding-ratio`
  - `--sdf-target-edge-length`
  - `--sdf-remesh-iterations`
  - `--sdf-sharp-edge-degrees`
- Preserved the high-precision reference capability through explicit main CLI parameters:
  - `--sdf-reconstruct --sdf-resolution 96 --sdf-target-edge-length 0`

### Cleanup Record

- Removed active budget race entry:
  - `mesh_budget_race_cli.cpp`
  - `include/mvrmesh/core/budget_race_candidates.h`
  - `src/core/budget_race_candidates.cpp`
  - `verification/cmake/run_mesh_budget_race_cli.cmake`
- Removed the `mesh_budget_race_cli` CMake target.
- Removed `src/core/budget_race_candidates.cpp` from `MVRMESH_CORE_SOURCES`.
- Replaced budget race candidate tests with product helper tests.
- Replaced README budget race usage with `mvr_to_mesh_cli --sdf-reconstruct`.

### Verification Notes

Completed validation on 2026-05-09:

- TDD red check: `mvrmesh_smoke_tests` failed before implementation because `BuildOptions::sdf_reconstruct`, SDF option fields, and `SurfaceMode::SdfReconstruct` did not exist yet.
- Built and ran `mvrmesh_smoke_tests`; result: exit 0, `[ok] smoke tests passed`.
- Built and ran `mvrmesh_quality_smoothing_tests`; result: exit 0, `[ok] quality/smoothing tests passed`.
- Built `mvr_to_mesh_cli`; result: exit 0.
- Built `check_fem_pressure`; result: exit 0.
- Ran positive manual CLI check:
  - `mvr_to_mesh_cli.exe verification\fixtures\tiny_surface.mvr --sdf-reconstruct --sdf-resolution 8 --sdf-target-edge-length 0.3 --sdf-remesh-iterations 1 -o ..\build\ShapeReconstruction\vs2022-x64\tiny_sdf_manual_2`
  - Result: exit 0, mode `sdf_reconstruct`, output mesh `19` vertices and `34` faces.
- Ran negative manual CLI check:
  - `mvr_to_mesh_cli.exe verification\fixtures\tiny_surface.mvr --sdf-resolution 8 -o ..\build\ShapeReconstruction\vs2022-x64\should_not_exist_sdf_manual_2`
  - Result: exit 1, rejected SDF tuning flag without `--sdf-reconstruct`.
- Ran CTest SDF CLI subset:
  - `ctest --test-dir ..\build\ShapeReconstruction\vs2022-x64 -C Debug -R "mvrmesh_cli_sdf_reconstruct|mvrmesh_cli_sdf_resolution_requires_sdf_reconstruct" --output-on-failure`
  - Result: 2/2 tests passed.
- Ran full CTest:
  - `ctest --test-dir ..\build\ShapeReconstruction\vs2022-x64 -C Debug --output-on-failure`
  - Result: 20/20 tests passed.
- Scanned active source/CMake/test paths for removed budget race symbols. Only README historical cleanup note still referenced `mesh_budget_race_cli`.
- Confirmed removed files do not exist:
  - `mesh_budget_race_cli.cpp`
  - `include/mvrmesh/core/budget_race_candidates.h`
  - `src/core/budget_race_candidates.cpp`
  - `verification/cmake/run_mesh_budget_race_cli.cmake`
