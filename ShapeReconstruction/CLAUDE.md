# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Workspace-wide rules (language, git, verification, sub-agent delegation, branch hygiene) live in [`../CLAUDE.md`](../CLAUDE.md) and `../AGENTS.md`. This file documents only what is specific to the `ShapeReconstruction` module.

## Module scope

`ShapeReconstruction` is the C++20 surface-reconstruction stage of MedSim2Learn. The library `mvrmesh` reads `.mvr` volumetric data (vertices + triangles + tetrahedra) and produces watertight triangle surfaces (PLY) plus optional pre-flight diagnostics for the downstream `DeformSim` solver. The CLI `mvr_to_mesh_cli` is the only executable entry point; `legacy/mvr_to_mesh.py` is kept for parity reference and is not built. For user-facing build, run, and CLI flag documentation, see [README.md](README.md).

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
ctest --preset vs2022-x64-debug -R mvrmesh_pressure_matrix_kidney
```

CGAL (via vcpkg) and TetGen (vendored at `D:/dev/tetgen-1.6.0`) are mandatory dependencies; cmake config fails fast if either is missing.

## Test matrix

Each suite is registered via `cmake/MvrmeshTests.cmake`:

| Test name | Source | What it covers |
|-----------|--------|----------------|
| `mvrmesh_smoke` | `verification/core/smoke_tests.cpp` | Pure unit tests for `mvrmesh::*` core APIs (topology, algorithms, indexing). |
| `mvrmesh_pressure_evaluator` | `verification/pressure/pressure_evaluator_tests.cpp` | TetGen-based pressure pre-flight unit tests. |
| `mvrmesh_tetgen_no_direct_exit` | `verification/cmake/check_tetgen_no_direct_exit.cmake` | Guards that the vendored TetGen source contains no raw `exit(1)` — must use `terminatetetgen(1)` so `TETLIBRARY` callers can recover. |
| `mvrmesh_cgal_mesh` | `verification/backends/cgal/cgal_mesh_tests.cpp` | Unit tests for the `run_cgal_mesh` two-stage pipeline. |
| `mvrmesh_cli_cgal_mesh` | direct CLI invocation | CLI smoke test: runs `--cgal-mesh --sharp-edge-degrees 130` on `tiny_surface.mvr`. Requires CGAL+TetGen. |
| `mvrmesh_cli_cgal_mesh_rejects_adaptive_remesh` | direct CLI invocation | Negative test (WILL_FAIL): verifies that `--cgal-mesh --adaptive-remesh` is rejected. |
| `mvrmesh_cli_cgal_mesh_rejects_unrelated_flag_without_pipeline` | direct CLI invocation | Negative test (WILL_FAIL): verifies that `--target-edge-length` without `--cgal-mesh` is rejected. |
| `mvrmesh_cli_direct` | direct CLI invocation | Only added if `originalData/MVR/kidney.mvr` is present — runs the default mesh path end-to-end on the kidney sample. |
| `mvrmesh_cli_cgal_mesh_kidney` | direct CLI invocation | Only added if `originalData/MVR/kidney.mvr` is present — runs `--cgal-mesh` on the kidney sample. |
| `mvrmesh_pressure_matrix_kidney` | `scripts/run_pressure_matrix.ps1` | Only added if `originalData/MVR/kidney.mvr` is present — runs the 6-candidate algorithm comparison matrix and produces `pressure_matrix.md`. |

## Architecture

### Layered library shape

The `mvrmesh` target is a single library composed of two layers:

```
include/mvrmesh/
├── core/        # Pure C++20, no third-party deps. The reconstruction kernel.
├── backends/
│   └── cgal/    # Optional CGAL Polygon Mesh Processing remesh.
└── pressure/    # TetGen-based DeformSim pressure evaluator (used by check_fem_pressure).
```

Core is self-contained — `core/types.h` defines `Vec3`, `Face`, `Tet`, `Edge`, `ParsedMvr`, `SurfaceMode`, `BuildOptions`, `BuildResult`; everything else in `core/` builds on those types only. Backends depend on core but never on each other, and are guarded by `MVRMESH_*_ENABLED` macros so the library still compiles with either disabled.

The headers are deliberately small and free-function-oriented (no big "Mesh" class). Add new functionality as free functions in the matching header rather than introducing a new class hierarchy.

### Pipeline (the surface build path)

End-to-end pipeline through `mvr_to_mesh_cli.cpp:main` is documented for users in [README.md § 4](README.md#4-algorithm-reference). For the agent's reference, the high-level dispatch is: `parse_args` → `find_project_root` (locates `originalData/` + `CMakeLists.txt`) → `parse_mvr` → `build_surface` (selects boundary extraction or `algorithms::adaptive_remesh`) → optional `run_cgal_mesh` (Stage 1 repair + Stage 2 remesh) → `write_ply`. When modifying any of these, also update README.md § 4.

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

The TetGen library in `D:/dev/tetgen-1.6.0` is built as a static library with `TETLIBRARY` defined (see `cmake/MvrmeshPressure.cmake`). Stock TetGen calls `exit(1)` on internal errors, which would terminate the entire CLI process. The vendored copy must be patched to call `terminatetetgen(1)` instead so it throws and the C++ wrapper can catch it. The `mvrmesh_tetgen_no_direct_exit` CTest enforces this — if it fails, the TetGen source has regressed; fix the source rather than disabling the test.

## Module-local conventions

- C++20. `std::runtime_error` for I/O and CLI argument errors is fine — `mvr_to_mesh_cli.cpp` catches them at `main`.
- Free functions in `mvrmesh::` namespace; no global state; no singletons.
- Python parity tests are load-bearing — when in doubt, mirror the legacy script's behavior.
