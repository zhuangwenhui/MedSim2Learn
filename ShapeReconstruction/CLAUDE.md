# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Workspace-wide rules (language, git, verification, sub-agent delegation, branch hygiene) live in [`../CLAUDE.md`](../CLAUDE.md) and `../AGENTS.md`. This file documents only what is specific to the `ShapeReconstruction` module.

## Module scope

`ShapeReconstruction` is the C++20 surface-reconstruction stage of MedSim2Learn. The library `mvrmesh` reads `.mvr` volumetric data (vertices + triangles + tetrahedra) and produces watertight triangle surfaces (PLY) plus optional pre-flight diagnostics for the downstream `DeformSim` solver. Two CLI executables exist: `mvr_to_mesh_cli` (surface reconstruction) and `check_fem_pressure` (TetGen-based pressure diagnostics). `legacy/mvr_to_mesh.py` is kept for parity reference and is not built. For user-facing build, run, and CLI flag documentation, see [README.md](README.md).

## Build and test

The build expects `vcpkg` (for CGAL) and a local TetGen 1.6 source checkout. CGAL and TetGen are both mandatory dependencies. Build output goes to `../build/ShapeReconstruction/`, **not** inside this folder.

Required environment:
- `VCPKG_ROOT` env var set; vcpkg toolchain provides `CGAL` for triplet `x64-windows`.
- TetGen 1.6 source available at `D:/dev/tetgen-1.6.0` (overridable via `-DTETGEN_ROOT=...`). The CMake module asserts the presence of `predicates.cxx`, `tetgen.cxx`, and `tetgen.h` and fails fast if missing.

Common commands (run from `d:/MedSim2Learn/ShapeReconstruction`):

```powershell
# Configure (Visual Studio 2022, x64). Reads CMakePresets.json.
cmake --preset vs2022-x64

# Build (Debug or Release).
cmake --build --preset vs2022-x64-debug
cmake --build --preset vs2022-x64-release

# Run the full CTest suite (Debug).
ctest --preset vs2022-x64-debug

# Run a single test by name (regex).
ctest --preset vs2022-x64-debug -R mvrmesh_smoke
ctest --preset vs2022-x64-debug -R mvrmesh_pressure_matrix_kidney
```

## Test matrix

Each suite is registered via `cmake/MvrmeshTests.cmake`:

| Test name | Source | What it covers |
|-----------|--------|----------------|
| `mvrmesh_smoke` | `verification/core/smoke_tests.cpp` | Unit tests for `mvrmesh::*` core APIs (topology, algorithms, indexing, pipeline build modes, metrics, PLY I/O). |
| `mvrmesh_quality_smoothing` | `verification/core/quality_smoothing_tests.cpp` | Unit tests for quality metrics, shape comparison, Taubin smoothing, vertex projection, SDF reconstruction, surface acceptance, FEM budget classification. |
| `mvrmesh_cgal_mesh` | `verification/backends/cgal/cgal_mesh_tests.cpp` | Unit tests for the `run_cgal_mesh` two-stage pipeline (repair + protected remesh). |
| `mvrmesh_pressure_evaluator` | `verification/pressure/pressure_evaluator_tests.cpp` | TetGen-based pressure pre-flight unit tests. |
| `mvrmesh_tetgen_no_direct_exit` | `verification/cmake/check_tetgen_no_direct_exit.cmake` | Guards that the vendored TetGen source contains no raw `exit(1)` -- must use `terminatetetgen(1)`. |
| `mvrmesh_cli_cgal_mesh` | CLI invocation | Smoke test: `--cgal-mesh --sharp-edge-degrees 130` on `tiny_surface.mvr`. |
| `mvrmesh_cli_uniform_subdivide` | CLI invocation | Smoke test: `--uniform-subdivide --uniform-iterations 1` on `tiny_surface.mvr`. |
| `mvrmesh_cli_uniform_taubin` | CLI invocation | Smoke test: `--uniform-subdivide --taubin-smooth` on `tiny_surface.mvr`. |
| `mvrmesh_cli_sdf_reconstruct` | CLI invocation | Smoke test: `--sdf-reconstruct` with resolution 8 on `tiny_surface.mvr`. |
| `mvrmesh_cli_cgal_mesh_rejects_adaptive_remesh` | CLI (WILL_FAIL) | `--cgal-mesh --adaptive-remesh` is rejected. |
| `mvrmesh_cli_cgal_mesh_rejects_unrelated_flag_without_pipeline` | CLI (WILL_FAIL) | `--target-edge-length` without `--cgal-mesh` is rejected. |
| `mvrmesh_cli_uniform_subdivide_rejects_adaptive_remesh` | CLI (WILL_FAIL) | `--uniform-subdivide --adaptive-remesh` is rejected. |
| `mvrmesh_cli_uniform_subdivide_rejects_cgal_mesh` | CLI (WILL_FAIL) | `--uniform-subdivide --cgal-mesh` is rejected. |
| `mvrmesh_cli_uniform_iterations_requires_uniform_subdivide` | CLI (WILL_FAIL) | `--uniform-iterations` without `--uniform-subdivide` is rejected. |
| `mvrmesh_cli_taubin_requires_uniform_subdivide` | CLI (WILL_FAIL) | `--taubin-smooth` without `--uniform-subdivide` is rejected. |
| `mvrmesh_cli_sdf_resolution_requires_sdf_reconstruct` | CLI (WILL_FAIL) | `--sdf-resolution` without `--sdf-reconstruct` is rejected. |
| `check_fem_pressure_single` | cmake driver script | End-to-end: `mvr_to_mesh_cli` produces PLY, then `check_fem_pressure` runs TetGen on it. |
| `mvrmesh_cli_direct` | CLI invocation | Conditional on `kidney.mvr` -- default mesh path end-to-end on kidney sample. |
| `mvrmesh_cli_cgal_mesh_kidney` | CLI invocation | Conditional on `kidney.mvr` -- `--cgal-mesh` on kidney sample. |
| `mvrmesh_pressure_matrix_kidney` | `scripts/run_pressure_matrix.ps1` | Conditional on `kidney.mvr` -- 6-candidate algorithm comparison matrix producing `pressure_matrix.md`. |

## Architecture

### Layered library shape

The `mvrmesh` target is a single library composed of three layers:

```
include/mvrmesh/
  core/        # Reconstruction kernel. Depends on CGAL for SDF containment queries.
  backends/
    cgal/      # CGAL Polygon Mesh Processing remesh (repair + protected remesh).
  pressure/    # TetGen-based DeformSim pressure evaluator (used by check_fem_pressure).
```

Backends depend on core but never on each other. `core/reconstruction.cpp` directly includes CGAL headers for AABB-tree and `Side_of_triangle_mesh` queries; `core/reconstruction_pipeline.cpp` includes `backends/cgal/cgal_mesh.h` to orchestrate SDF reconstruction + CGAL remesh. This cross-layer dependency is intentional and load-bearing.

The headers are deliberately small and free-function-oriented (no big "Mesh" class). Add new functionality as free functions in the matching header rather than introducing a new class hierarchy.

### Core modules

`core/types.h` defines the foundation: `Vec3`, `Face`, `Tet`, `Edge`, `ParsedMvr`, `SurfaceMode` (5 modes), `BuildOptions` (16 fields), `BuildResult`. Everything else in `core/` builds on these types.

| Header | Role |
|--------|------|
| `geometry.h` | Vec3 arithmetic: `vsub`, `vadd`, `vmul`, `dot`, `cross`, `norm`, `normalize`, `face_normal`. |
| `topology.h` | Index normalization (1-based to 0-based auto-detect), boundary face extraction from tets, face orientation. |
| `io.h` | `parse_mvr` (section-based `@N` format), `write_ply`, `read_ply`. |
| `algorithms.h` | Curvature estimation, edge selection, face splitting, `uniform_subdivide`, `adaptive_remesh`, `compact_mesh_to_referenced_vertices`. |
| `metrics.h` | `SurfaceMetrics` (10 fields), `compute_surface_metrics`, `metrics_to_json`. Contains `DisjointSet` in anonymous namespace. |
| `quality_metrics.h` | `MeshQualityMetrics` (aspect ratio, edge length, angles), `ShapeComparisonMetrics` (Hausdorff, mean distance), JSON serializers. |
| `smoothing.h` | `taubin_smooth` (two-pass Laplacian with lambda/mu), `project_vertices_to_surface`. |
| `reconstruction.h` | `reconstruct_surface_sdf` -- marching tetrahedra on SDF grid. Depends on CGAL AABB-tree. |
| `reconstruction_pipeline.h` | `reconstruct_and_remesh_surface` -- orchestrates SDF reconstruction + CGAL remesh. |
| `surface_acceptance.h` | `evaluate_surface_acceptance` quality gate, `classify_fem_budget` (FEM cost classification). |
| `pipeline.h` | `build_surface` dispatch (selects mode based on `BuildOptions`), `outputs_for_mode`, `surface_mode_to_string`. |

### Pipeline (the surface build path)

`build_surface` in `pipeline.cpp` dispatches to one of five `SurfaceMode` paths based on `BuildOptions` flags:

| Mode | Trigger flags | Path |
|------|--------------|------|
| `DirectSurface` | (default, no flags) | `boundary_faces_from_tets` |
| `AdaptiveRemesh` | `--adaptive-remesh` | `boundary_faces_from_tets` then `adaptive_remesh` |
| `UniformSubdivide` | `--uniform-subdivide` | `boundary_faces_from_tets` then `uniform_subdivide` (iterated) |
| `UniformTaubin` | `--uniform-subdivide --taubin-smooth` | `boundary_faces_from_tets` then `uniform_subdivide` then `taubin_smooth` then `project_vertices_to_surface` |
| `SdfReconstruct` | `--sdf-reconstruct` | `reconstruct_and_remesh_surface` (SDF grid + marching tets + CGAL remesh) |

End-to-end flow through `mvr_to_mesh_cli.cpp:main`: `parse_args` -> `find_project_root` (locates `originalData/` + `CMakeLists.txt`) -> `parse_mvr` -> `build_surface` (dispatches to one of the five modes above) -> optional `run_cgal_mesh` (Stage 1 repair + Stage 2 remesh, only for non-SDF modes with `--cgal-mesh`) -> `write_ply`.

The five modes are mutually exclusive; `parse_args` enforces conflict rules (e.g. `--cgal-mesh` + `--uniform-subdivide` is rejected). When modifying the pipeline, also update README.md algorithm reference.

### Default I/O conventions

The CLI applies project-aware path defaults -- keep them when adding new flags:
- Relative input paths are searched in cwd, then `<project_root>/`, then `<project_root>/originalData/`.
- Without `--output`, output is written under `<project_root>/outPut/PLY/<stem>.ply`.
- Project root is detected via the `originalData/` + `CMakeLists.txt` pair, not hardcoded.

### Indexing-parity quirks

The C++ port preserves a few subtle behaviors of `legacy/mvr_to_mesh.py` because tests assert them:

- `normalize_faces_indices` / `normalize_tet_indices` auto-detect 1-based vs 0-based indexing and convert when needed.
- `boundary_faces_from_tets` orients each boundary face outward using the opposite tet vertex, matching the Python output exactly.

When changing any of these, update both the implementation and the smoke-test assertions in lockstep, and explain the parity break.

### TetGen integration constraint

The TetGen library in `D:/dev/tetgen-1.6.0` is built as a static library with `TETLIBRARY` defined (see `cmake/MvrmeshPressure.cmake`). Stock TetGen calls `exit(1)` on internal errors, which would terminate the entire CLI process. The vendored copy must be patched to call `terminatetetgen(1)` instead so it throws and the C++ wrapper can catch it. The `mvrmesh_tetgen_no_direct_exit` CTest enforces this -- if it fails, the TetGen source has regressed; fix the source rather than disabling the test.

## Module-local conventions

- C++20. `std::runtime_error` for I/O and CLI argument errors is fine -- `mvr_to_mesh_cli.cpp` catches them at `main`.
- Free functions in `mvrmesh::` namespace; no global state; no singletons.
- Python parity tests are load-bearing -- when in doubt, mirror the legacy script's behavior.
