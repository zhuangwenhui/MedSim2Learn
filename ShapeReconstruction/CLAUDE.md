# CLAUDE.md

> Workspace-wide rules (language, git, verification, delegation, branch hygiene) live in [`../CLAUDE.md`](../CLAUDE.md) and `../AGENTS.md`. This file is **only** what is specific to the `ShapeReconstruction` module. For architecture and the module/test inventory, read `graphify-out/GRAPH_REPORT.md` instead of restating it here.

## Module scope

`ShapeReconstruction` is the C++20 surface-reconstruction stage: the `mvrmesh` library reads `.mvr` volumetric data and produces watertight PLY surfaces plus pre-flight FEM-pressure diagnostics for `DeformSim`. CLIs: `mvr_to_mesh_cli` (reconstruction) and `check_fem_pressure` (TetGen pressure). `legacy/mvr_to_mesh.py` is a parity-reference mirror — not built; do not delete or "modernize" it. It marks the module's minimal core (read `.mvr` -> mesh -> write PLY/STL); resist feature bloat that drifts from that. User-facing CLI docs: `README.md`.

## Build (non-obvious bits)

- Out-of-tree: build output goes to `../build/ShapeReconstruction/`, never inside this folder.
- Mandatory deps: vcpkg-provided CGAL (`VCPKG_ROOT` set, triplet `x64-windows`) **and** a local TetGen 1.6 source at `D:/dev/tetgen-1.6.0` (override `-DTETGEN_ROOT=...`); the CMake module fails fast if the TetGen sources are missing.
- Presets (see `CMakePresets.json`): `cmake --preset vs2022-x64`, then `cmake --build --preset vs2022-x64-{debug,release}`, then `ctest --preset vs2022-x64-debug`.

## Module-local rules

- **TetGen patch is load-bearing.** The vendored TetGen must call `terminatetetgen(1)`, not `exit(1)`, so the wrapper can catch internal errors instead of killing the CLI process. The `mvrmesh_tetgen_no_direct_exit` CTest enforces this — if it fails, fix the TetGen source, do not disable the test.
- **Python-parity quirks are tested.** `normalize_*_indices` (1-based/0-based auto-detect) and the outward face orientation in `boundary_faces_from_tets` deliberately match `legacy/mvr_to_mesh.py`. When changing them, update the implementation and the smoke-test assertions in lockstep and explain the parity break.
- **Update `README.md`'s algorithm reference when changing the pipeline** (surface modes / flags).
- **Style:** C++20; free functions in the `mvrmesh::` namespace; no new "Mesh" class hierarchy, no global state, no singletons. `std::runtime_error` for I/O and CLI errors (caught at `main`).
