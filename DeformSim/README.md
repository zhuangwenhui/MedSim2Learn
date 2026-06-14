# DeformSim

Headless linear-elastic FEM sample generator. Reads a watertight surface PLY
(produced by `ShapeReconstruction`), tetrahedralizes it with the vendored
TetGen, assembles a linear isotropic stiffness matrix, applies sampled or
replayed contact forces, and writes deformed PLY samples plus a force-label
CSV for `Deform_post` / `KiDKNet` training.

## Layout

- `src/main.cpp` -- run orchestration: load params -> sample/replay forces ->
  read PLY -> annotation -> tetra/matrix templates -> worker pool -> final
  CSV and consistency check
- `src/sim/` -- orchestrator modules: `hyper_params` (env config),
  `annotation` (freeze/contact JSON, k-ring regions), `force_sampling`
  (mt19937 cone sampling, CSV replay), `sample_pipeline` (tetra template
  clone, material/freeze/contact state, cache keys), `output_writer`
  (verified PLY, CSV journal and final CSV, diagnostics), `progress`
  (console bar, heartbeat), `worker` (thread pool)
- `BMGL/` -- frozen legacy zone (FEM kernel); compiles against the root
  `stdafx.h` umbrella header, which new code must not extend
- third-party code (TetGen 1.6.0, nlohmann json) is vendored once for the
  whole workspace at `../third_party/` and referenced in place; see
  `../THIRD_PARTY_NOTICES.md`
- `verification/` -- standalone check tools (see below)

## Build

```powershell
cd DeformSim
cmake --preset vs2022-x64
cmake --build ..\build\DeformSim\vs2022-x64 --config Release
```

Dependencies: Intel oneAPI MKL (paths in `cmake/FindLocalDeps.cmake`, default
`C:/Program Files (x86)/Intel/oneAPI/.../latest`). MKL runtime DLLs must be on
`PATH` at run time (`scripts/setup_env.ps1` or `run_kidney_sim.ps1` handle it).

## Unit system

Consistent mm-MPa-N, inherited from the millimetre coordinates of the
ShapeReconstruction meshes:

| Quantity | Unit |
|---|---|
| coordinates / displacements | mm |
| Young's modulus | MPa (N/mm^2); kidney runs use 0.03 MPa = 30 kPa |
| Poisson ratio | dimensionless, valid (-1, 0.5); kidney runs use 0.40 |
| forces | N |
| angles | degrees from the -z axis |

## Configuration (environment variables)

All configuration is read from `SIM2LEARN_PARAM_*` environment variables;
`main` takes no CLI arguments. Invalid values fall back to the default with a
warning; `nan`/`inf` are rejected.

| Variable | Default | Meaning |
|---|---|---|
| `SIM2LEARN_PARAM_PLY_PATH` | (required) | input surface PLY (ascii, triangles); canonical fixture `DataFlow/DeformSim/fixtures/plate.ply` |
| `SIM2LEARN_PARAM_ANNOTATION_PATH` | `./annotation.json` | freeze + contact-seed JSON (0-based indices) |
| `SIM2LEARN_PARAM_FORCE_LIST_CSV` | empty | replay mode: bare `fx,fy,fz` rows replace sampling |
| `SIM2LEARN_PARAM_NUM_VECTOR` | 100 | force vectors per contact seed |
| `SIM2LEARN_PARAM_SEED` | 20260328 | mt19937 seed for force sampling |
| `SIM2LEARN_PARAM_MATERIAL_YOUNG` | 1.0 | Young's modulus in MPa |
| `SIM2LEARN_PARAM_MATERIAL_POISSON` | 0.40 | Poisson ratio |
| `SIM2LEARN_PARAM_FORCE_{X,Y,Z}_{MIN,MAX}` | x,y: +-10; z: [-100, -0.1] | sampled force component bounds (N) |
| `SIM2LEARN_PARAM_{MIN,MAX}_ANGLE_DEG` | 0 / 45 | sampling cone around -z (deg) |
| `SIM2LEARN_PARAM_NUM_THREADS` | 4 | worker threads |
| `SIM2LEARN_PARAM_MKL_NUM_THREADS` | 1 | MKL threads (0 = auto-derive) |
| `SIM2LEARN_PARAM_USE_REUSE_TETRA_TEMPLATE` | 1 | tetrahedralize once, clone per sample |
| `SIM2LEARN_PARAM_USE_MATRIX_SOLVER_CACHE` | 1 | factorize K once, share LU factors read-only |
| `SIM2LEARN_PARAM_ISOLATE_OUTPUT` | 1 | timestamp+PID output directory per run |
| `SIM2LEARN_PARAM_MAX_OBJECTS` | 0 | cap on total samples (0 = unlimited) |
| `SIM2LEARN_PARAM_USE_DIAG_CONTACT_HASH` | 0 | write DiagContactHash.csv |
| `SIM2LEARN_PARAM_DIAG_FLUSH_INTERVAL` | 32 | diag/journal flush cadence |

## Outputs

Per run, under `./DeformedSample_ComplexObject_<YY_MM_DD_HHMMSS>_p<PID>/`
(relative to the working directory; launch scripts place it under
`DataFlow/`):

- `deformed_s<seed>_v<vec>.ply` — deformed mesh per sample (ascii, written
  via temp+rename so partial files never survive)
- `SampleID_log<run>.csv` — sorted force labels, `%.9g` (round-trip exact for
  replay); a `.partial` write-through journal exists during the run and is
  removed on success
- `DiagContactHash.csv` — optional contact diagnostics

## Verification tools

Built when `DEFORMSIM_ENABLE_VERIFICATION=ON` (default):

- `deformsim_ply_tetra_smoke <in.ply> <out.json>` — PLY -> tetra pipeline
  smoke test
- `deformsim_ply_tetra_diagnostic <in.ply> <out.json>` — tetra mesh quality
  diagnostics
- `deformsim_fem_bar_bench` — analytic FEM benchmark: axial bar with
  consistent end loads; with Poisson 0 the linear-tet solution must match
  delta = F*L/(E*A) to patch-test accuracy
