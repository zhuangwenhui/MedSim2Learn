# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Workspace-wide rules (language, git, verification, sub-agent delegation, branch hygiene) live in [`../CLAUDE.md`](../CLAUDE.md) and `../AGENTS.md`. This file documents only what is specific to the `ShapeReconstruction` module.

## Module scope

`ShapeReconstruction` is the C++20 surface-reconstruction stage of MedSim2Learn. The library `mvrmesh` reads `.mvr` volumetric data (vertices + triangles + tetrahedra) and produces watertight triangle surfaces (PLY) plus optional pre-flight diagnostics for the downstream `DeformSim` solver. The CLI `mvr_to_mesh_cli` is the only executable entry point; `legacy/mvr_to_mesh.py` is kept for parity reference and is not built.

## Build and test

The build expects `vcpkg` (for CGAL) and a local TetGen 1.6 source checkout. Build output goes to `../build/ShapeReconstruction/`, **not** inside this folder.

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
ctest --preset vs2022-x64-debug -R mvrmesh_cli_deformsim_pressure
```

Backends can be toggled at configure time via `-DMVRMESH_ENABLE_CGAL=OFF` / `-DMVRMESH_ENABLE_TETGEN=OFF`. Disabling a backend disables both its sources and the CTest cases that depend on it (the relevant `MVRMESH_*_ENABLED` macro is set to `0` so call sites compile out cleanly — see the conditional `#if MVRMESH_*_ENABLED` blocks in `mvr_to_mesh_cli.cpp`).

## Test matrix

Each suite is registered via `cmake/MvrmeshTests.cmake`:

| Test name | Source | What it covers |
|-----------|--------|----------------|
| `mvrmesh_smoke` | `verification/core/smoke_tests.cpp` | Pure unit tests for `mvrmesh::*` core APIs (topology, algorithms, indexing). |
| `mvrmesh_tetgen_evaluator` | `verification/backends/tetgen/tetgen_evaluator_tests.cpp` | TetGen-based pressure pre-flight unit tests. Requires `MVRMESH_ENABLE_TETGEN=ON`. |
| `mvrmesh_tetgen_no_direct_exit` | `verification/cmake/check_tetgen_no_direct_exit.cmake` | Guards that the vendored TetGen source contains no raw `exit(1)` — must use `terminatetetgen(1)` so `TETLIBRARY` callers can recover. |
| `mvrmesh_cgal_mesh` | `verification/backends/cgal/cgal_mesh_tests.cpp` | Unit tests for the `run_cgal_mesh` two-stage pipeline. Requires `MVRMESH_ENABLE_CGAL=ON` and `MVRMESH_ENABLE_TETGEN=ON`. |
| `mvrmesh_cli_cgal_mesh` | direct CLI invocation | CLI smoke test: runs `--cgal-mesh --sharp-edge-degrees 130` on `tiny_surface.mvr`. Requires CGAL+TetGen. |
| `mvrmesh_cli_robust_pipeline_with_pressure` | direct CLI invocation | CLI run with `--cgal-mesh` and `--deformsim-pressure-output` on `tiny_surface.mvr` (retains old name, scheduled for deletion in P5). |
| `mvrmesh_cli_cgal_mesh_rejects_adaptive_remesh` | direct CLI invocation | Negative test (WILL_FAIL): verifies that `--cgal-mesh --adaptive-remesh` is rejected. |
| `mvrmesh_cli_cgal_mesh_rejects_unrelated_flag_without_pipeline` | direct CLI invocation | Negative test (WILL_FAIL): verifies that `--target-edge-length` without `--cgal-mesh` is rejected. |
| `mvrmesh_cli_deformsim_pressure` | `run_cli_deformsim_pressure.cmake` + `check_deformsim_pressure_json.cmake` | Runs the CLI with `--deformsim-pressure-output` and substring-matches expected fields in the JSON (e.g. `"tetgen_output_tetra_count": 1`). Scheduled for deletion in P5 alongside the flag. |
| `mvrmesh_cli_direct` | direct CLI invocation | Only added if `originalData/MVR/kidney.mvr` is present — runs the default mesh path end-to-end on the kidney sample. |
| `mvrmesh_cli_cgal_mesh_kidney` | direct CLI invocation | Only added if `originalData/MVR/kidney.mvr` is present — runs `--cgal-mesh` with `--deformsim-pressure-output` on the kidney sample. |

The CMake-script tests (`check_deformsim_pressure_json.cmake`) do **literal substring matching** on the JSON payload. Adding/removing whitespace or renaming a field is a breaking change for these tests; update the expected strings together with the producer.

## Architecture

### Layered library shape

The `mvrmesh` target is a single library composed of two layers:

```
include/mvrmesh/
├── core/        # Pure C++20, no third-party deps. The reconstruction kernel.
└── backends/
    ├── cgal/    # Optional CGAL Polygon Mesh Processing remesh.
    └── tetgen/  # Optional TetGen-based pre-flight for DeformSim.
```

Core is self-contained — `core/types.h` defines `Vec3`, `Face`, `Tet`, `Edge`, `ParsedMvr`, `SurfaceMode`, `BuildOptions`, `BuildResult`; everything else in `core/` builds on those types only. Backends depend on core but never on each other, and are guarded by `MVRMESH_*_ENABLED` macros so the library still compiles with either disabled.

The headers are deliberately small and free-function-oriented (no big "Mesh" class). Add new functionality as free functions in the matching header rather than introducing a new class hierarchy.

### Pipeline (the surface build path)

End-to-end path through `mvr_to_mesh_cli.cpp:main`:

1. `parse_args` -> `CliOptions` (validates flag combinations: `--cgal-mesh` conflicts with `--adaptive-remesh`; `--sharp-edge-degrees`, `--target-edge-length`, and `--remesh-iterations` each require `--cgal-mesh`; `--sharp-edge-degrees` must be in `(0, 180)`, `--target-edge-length` must be `>= 0`, `--remesh-iterations` must be `>= 1`).
2. `find_project_root(argv0)` walks up from cwd or the executable path looking for a directory containing both `originalData/` and `CMakeLists.txt` — this is how the CLI resolves relative input paths and chooses default outputs.
3. `parse_mvr` (`core/io.cpp`) -> `ParsedMvr { vertices, triangles, tetrahedra }`.
4. `build_surface` (`core/pipeline.cpp`) selects between explicit triangles and tet-boundary extraction (`topology::boundary_faces_from_tets`) and optionally runs `algorithms::adaptive_remesh` curvature-based midpoint subdivision.
5. If `--cgal-mesh`, `run_cgal_mesh` runs a two-stage pipeline (Stage 1: repair self-intersections; Stage 2: protected isotropic remesh) at `backends/cgal/cgal_mesh.cpp`.
6. Output is a single PLY written via `write_ply`.
7. Optional `--deformsim-pressure-output` triggers `evaluate_deformsim_pressure` (TetGen). This is **diagnostic only**: it tetrahedralizes the surface, then estimates the dense `K`/`L` matrix order and byte size DeformSim would need, plus a unique-line/edge upper bound. Result is written via `write_deformsim_pressure_json`.

### Default I/O conventions

The CLI applies project-aware path defaults — keep them when adding new flags:
- Relative input paths are searched in cwd, then `<project_root>/`, then `<project_root>/originalData/`.
- Without `--output`, output is written under `<project_root>/outPut/PLY/<stem>.ply`.
- Project root is detected via the `originalData/` + `CMakeLists.txt` pair, not hardcoded.

### Indexing-parity quirks

The C++ port preserves a few subtle behaviors of `legacy/mvr_to_mesh.py` because tests assert them:

- `normalize_faces_indices` / `normalize_tet_indices` auto-detect 1-based vs 0-based indexing and convert when needed.
- `boundary_faces_from_tets` orients each boundary face outward using the opposite tet vertex, matching the Python output exactly.

When changing any of these, update both the implementation and the smoke-test assertions in lockstep, and explain the parity break.

### TetGen integration constraint

The TetGen library in `D:/dev/tetgen-1.6.0` is built as a static library with `TETLIBRARY` defined (see `cmake/MvrmeshTetGen.cmake`). Stock TetGen calls `exit(1)` on internal errors, which would terminate the entire CLI process. The vendored copy must be patched to call `terminatetetgen(1)` instead so it throws and the C++ wrapper can catch it. The `mvrmesh_tetgen_no_direct_exit` CTest enforces this — if it fails, the TetGen source has regressed; fix the source rather than disabling the test.

## Module-local conventions

- C++20. `std::runtime_error` for I/O and CLI argument errors is fine — `mvr_to_mesh_cli.cpp` catches them at `main`.
- Free functions in `mvrmesh::` namespace; no global state; no singletons.
- Backend feature gates are compile-time only (`#if MVRMESH_CGAL_PMP_ENABLED`, `#if MVRMESH_TETGEN_ENABLED`). Don't introduce runtime feature flags for these.
- Python parity tests are load-bearing — when in doubt, mirror the legacy script's behavior.
