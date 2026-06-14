# ShapeReconstruction

C++20 surface reconstruction stage of MedSim2Learn: reads `.mvr` volumetric data, repairs the surface, increases triangle count via configurable meshing algorithms, and writes `.ply`. Includes a separate `check_fem_pressure` executable for evaluating the FEM resource cost of the produced meshes.

---

## 1. Overview

ShapeReconstruction is the **mesh production + FEM pre-flight** stage of the [MedSim2Learn](../) workflow. It serves four goals:

- **G1 (input/output convention)**: reads `.mvr` from `DataFlow/ShapeReconstruction/originalData/MVR/`, writes `.ply` to `DataFlow/ShapeReconstruction/outputs/PLY/` (workspace data tier; legacy in-repo `originalData/`/`outPut/` still accepted as a fallback)
- **G2 (repair input)**: removes self-intersections, duplicate polygons, degenerate faces (CGAL Stage 1)
- **G3 (mesh control)**: increases or regularizes triangle count via configurable algorithms (`--adaptive-remesh`, `--uniform-subdivide`, `--taubin-smooth`, `--sdf-reconstruct`, `--cgal-mesh`)
- **G4 (FEM pressure preview)**: standalone tool projects DeformSim's K/L matrix memory + DGETRI/DGEMV flops + output disk for any candidate `.ply`

Two executables are produced:

| Executable | Role | Input | Output |
|---|---|---|---|
| `mvr_to_mesh_cli` | G1+G2+G3 mesh production | `.mvr` | `.ply` |
| `check_fem_pressure` | G4 standalone diagnostic | `.ply` (one or many) | `.json` (single) or `.md` (matrix) |

End-to-end position in the MedSim2Learn workflow:

```
 +-------------+         +----------------------+         +------------+         +--------+
 | raw scan +  |   -->   | ShapeReconstruction  |   -->   | DeformSim  |   -->   | KiDKNet |
 | tetrahedral |         | - mvr_to_mesh_cli    |         | (FEM)      |         | (ML)    |
 | .mvr        |         | - check_fem_pressure |         |            |         |         |
 +-------------+         +----------------------+         +------------+         +--------+
```

ShapeReconstruction is the only part of this chain that lives in this repo. DeformSim and KiDKNet are sibling sub-projects under `MedSim2Learn/`.

## 2. Quick Start

### Prerequisites

- **Visual Studio 2022** with C++20 toolchain
- **vcpkg** with `VCPKG_ROOT` environment variable set (the preset points at its toolchain file). Dependencies (`cgal`, `yaml-cpp`) are pinned by `vcpkg.json` (manifest mode, fixed baseline) and install into the build tree automatically on first configure -- no manual `vcpkg install` step.
- **TetGen 1.6 source**: vendored in-repo at `../third_party/tetgen-1.6.0` (the default; overridable via the `TETGEN_ROOT` env variable or `-DTETGEN_ROOT=...`). The CMake module asserts the presence of `predicates.cxx`, `tetgen.cxx`, `tetgen.h` and fails fast if missing.
- **PowerShell 5.1+** (for the matrix orchestration script)

### Build (3 commands)

From `d:/MedSim2Learn/ShapeReconstruction`:

```powershell
cmake --preset vs2022-x64
cmake --build --preset vs2022-x64-debug
ctest --preset vs2022-x64-debug
```

Expected ctest output: `100% tests passed, 0 tests failed`.

Build output goes to `../build/ShapeReconstruction/`, **not** inside this folder. Executables land at `..\build\ShapeReconstruction\vs2022-x64\Debug\`.

### Run on the kidney sample

The default mesh path on `kidney.mvr` (no flags = direct boundary extraction):

```powershell
cd d:\MedSim2Learn\ShapeReconstruction
& ..\build\ShapeReconstruction\vs2022-x64\Debug\mvr_to_mesh_cli.exe ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr
```

Output: `..\DataFlow\ShapeReconstruction\outputs\PLY\kidney.ply` (424 vertices, 500 triangles).

Then evaluate FEM pressure:

```powershell
& ..\build\ShapeReconstruction\vs2022-x64\Debug\check_fem_pressure.exe `
    ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney.ply -o ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_pressure.json

Get-Content ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_pressure.json
```

Expected JSON keys: `v_surface=424`, `v_tet=424`, `expansion_ratio=1.00`, `matrix_order_3v_tet=1272`, `memory_peak_bytes_kl=25887744` (~24.7 MiB), `tetgen_success=true`.

To generate a shape-preserving denser candidate for separate pressure testing:

```powershell
& ..\build\ShapeReconstruction\vs2022-x64\Debug\mvr_to_mesh_cli.exe `
    ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr `
    -o ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_uniform_iter1.ply `
    --uniform-subdivide `
    --uniform-iterations 1
```

This keeps the input shape vertices fixed and splits each triangle into four triangles per pass.

### Run the algorithm comparison matrix

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\run_pressure_matrix.ps1 `
    -InputMvr ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr `
    -OutDir ..\DataFlow\ShapeReconstruction\outputs\REPORT `
    -CliExe ..\build\ShapeReconstruction\vs2022-x64\Debug\mvr_to_mesh_cli.exe `
    -PressureExe ..\build\ShapeReconstruction\vs2022-x64\Debug\check_fem_pressure.exe `
    -BaselinePly ..\DataFlow\DeformSim\fixtures\plate.ply
```

This runs 6 mesh algorithm candidates on the kidney input and writes a Markdown comparison report at `..\DataFlow\ShapeReconstruction\outputs\REPORT\pressure_matrix.md` with V_surf, V_tet, memory, DGETRI, DGEMV, and output disk per row, including the DeformSim plate.ply baseline.

### Run the accepted uniform Taubin main-flow mesh

The accepted mesh-in-place race result is now exposed through `mvr_to_mesh_cli`: uniform subdivision followed by Taubin smoothing.

```powershell
& ..\build\ShapeReconstruction\vs2022-x64\Debug\mvr_to_mesh_cli.exe `
    ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr `
    -o ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_uniform_taubin.ply `
    --uniform-subdivide `
    --uniform-iterations 2 `
    --taubin-smooth
```

The removed first-round race candidates are recorded in `maintainLogs/2026-05-09-maintenance-log.md`.

### Run the accepted SDF reconstruction main-flow mesh

The accepted closed FEM-budget reconstruction path is now exposed through `mvr_to_mesh_cli` as a single-output product mode. It rebuilds the boundary surface through SDF reconstruction, then applies CGAL repair/remesh.

```powershell
& ..\build\ShapeReconstruction\vs2022-x64\Debug\mvr_to_mesh_cli.exe `
    ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr `
    -o ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_sdf_reconstruct.ply `
    --sdf-reconstruct
```

The default SDF product parameters match the accepted `budget_sdf72_L025` race result: SDF resolution 72, target edge length 0.025, padding ratio 0.05, sharp-edge threshold 179 degrees, and 3 remesh iterations.

To reproduce the historical highest-precision SDF + CGAL remesh reference path corresponding to `recon_sdf96_remesh.ply`, use explicit parameters:

```powershell
& ..\build\ShapeReconstruction\vs2022-x64\Debug\mvr_to_mesh_cli.exe `
    ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr `
    -o ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_sdf96_highest_precision.ply `
    --sdf-reconstruct `
    --sdf-resolution 96 `
    --sdf-target-edge-length 0
```

Evaluate FEM pressure separately with `check_fem_pressure` after writing the `.ply`.

### Historical race tracks

`mesh_race_cli`, `mesh_multi_track_race_cli`, and `mesh_budget_race_cli` have been removed from the current code path after their races closed and their accepted algorithms were migrated into `mvr_to_mesh_cli`.

Historical tracks and cleanup records are preserved in `maintainLogs/2026-05-05-remeshing-race-closure.md` and `maintainLogs/2026-05-09-maintenance-log.md`, including `multi_track_orchestrator`, `alpha_wrap`, `high_quality_decimation`, `adaptive_sdf`, `poisson_point_normal`, and the rejected mesh-in-place candidates.

## 3. CLI Reference

### 3.1 `mvr_to_mesh_cli` (G1+G2+G3)

| Flag | Default | Range / Type | Effect |
|---|---|---|---|
| `<input.mvr>` | required | path | Positional. Searched cwd -> `<project_root>/` -> `<workspace>/DataFlow/ShapeReconstruction/originalData/` -> legacy `<project_root>/originalData/`. |
| `-o <base>`, `--output <base>` | `<workspace>/DataFlow/ShapeReconstruction/outputs/PLY/<stem>.ply` | path | Output base path; extension must be `.ply` or `.PLY`. |
| `--config <yaml>`, `-c <yaml>` | none | path | YAML config file. Three-layer merge: hardcoded defaults -> YAML -> CLI overrides. |
| `--mode <name>` | `direct_surface` | string | Surface mode name. One of: `direct_surface`, `adaptive_remesh`, `uniform_subdivide`, `uniform_taubin`, `sdf_reconstruct`. |
| `--adaptive-remesh` | off | flag | Enable curvature-driven midpoint subdivision. |
| `--adaptive-iterations N` | 1 | integer >= 1 | Number of adaptive subdivision passes. |
| `--adaptive-split-ratio R` | 0.5 | float (0, 1] | Triangles whose curvature exceeds this ratio of mean are split. |
| `--uniform-subdivide` | off | flag | Enable shape-preserving global midpoint subdivision. Conflicts with `--adaptive-remesh` and `--cgal-mesh`. |
| `--uniform-iterations N` | 1 | integer >= 1 | Number of uniform subdivision passes. Requires `--uniform-subdivide`; each pass multiplies face count by 4. |
| `--taubin-smooth` | off | flag | Apply Taubin smoothing after uniform subdivision. Requires `--uniform-subdivide`. |
| `--taubin-iterations N` | 8 | integer >= 0 | Number of Taubin smoothing passes. Requires `--taubin-smooth`. |
| `--taubin-lambda X` | 0.5 | finite float | Taubin positive smoothing step. Requires `--taubin-smooth`. |
| `--taubin-mu X` | -0.53 | finite float | Taubin negative smoothing step. Requires `--taubin-smooth`. |
| `--sdf-reconstruct` | off | flag | Rebuild the surface through SDF reconstruction, then apply CGAL repair/remesh. Conflicts with `--adaptive-remesh`, `--uniform-subdivide`, and `--cgal-mesh`. |
| `--sdf-resolution N` | 72 | integer [2, 160] | SDF grid resolution for `--sdf-reconstruct`. |
| `--sdf-padding-ratio R` | 0.05 | finite float >= 0 | Bounding-box padding ratio for SDF sampling. Requires `--sdf-reconstruct`. |
| `--sdf-target-edge-length L` | 0.025 | finite float >= 0 | CGAL remesh target after SDF reconstruction. `0` uses CGAL auto target length. Requires `--sdf-reconstruct`. |
| `--sdf-remesh-iterations N` | 3 | integer >= 1 | CGAL remesh sweeps after SDF reconstruction. Requires `--sdf-reconstruct`. |
| `--sdf-sharp-edge-degrees D` | 179.0 | float (0, 180) | Protected-edge threshold after SDF reconstruction. Requires `--sdf-reconstruct`. |
| `--cgal-mesh` | off | flag | Enable CGAL Stage 1 (repair) + Stage 2 (isotropic remesh). Conflicts with `--adaptive-remesh` and `--uniform-subdivide`. |
| `--sharp-edge-degrees D` | 60.0 | float (0, 180) | Dihedral threshold for protected sharp edges in Stage 2. Requires `--cgal-mesh`. |
| `--target-edge-length L` | auto (= mean input edge) | float >= 0 | Target edge length for isotropic remeshing. Smaller L -> more triangles. Requires `--cgal-mesh`. |
| `--remesh-iterations N` | 3 | integer >= 1 | Number of isotropic remesh sweeps. Requires `--cgal-mesh`. |

`--cgal-mesh`, `--adaptive-remesh`, `--uniform-subdivide`, and `--sdf-reconstruct` are mutually exclusive. `--taubin-smooth` is a post-step of `--uniform-subdivide`, so it is not a standalone meshing mode. All `--sharp-edge-degrees`, `--target-edge-length`, `--remesh-iterations` require `--cgal-mesh`; `--uniform-iterations` requires `--uniform-subdivide`; all `--taubin-*` tuning flags require `--taubin-smooth`; all `--sdf-*` tuning flags require `--sdf-reconstruct`.

The legacy boolean flags (`--adaptive-remesh`, `--uniform-subdivide`, `--taubin-smooth`, `--sdf-reconstruct`, `--cgal-mesh`) are syntax sugar that resolve to `--mode`. When `--mode` or `--config` is used, the legacy conflict detection is skipped and the mode is taken directly from the explicit value.

**YAML config example** (`config.yaml`):
```yaml
mode: uniform_taubin
uniform_subdivide:
  iterations: 2
taubin:
  iterations: 8
  lambda: 0.5
  mu: -0.53
```
```powershell
& mvr_to_mesh_cli.exe kidney.mvr --config config.yaml -o kidney_taubin.ply
```

**Migration from older `--robust-pipeline`**: that flag was renamed to `--cgal-mesh` in P3 of the realignment. Any script using the old name needs the rename.

### 3.2 `check_fem_pressure` (G4)

Two modes share argument parsing:

| Flag | Default | Mode | Effect |
|---|---|---|---|
| `<input.ply>` (positional) | none | single | Input PLY for single-file evaluation. |
| `--matrix <ply1> <ply2> ...` | none | matrix | Variadic list of PLY inputs for matrix mode. |
| `-o <output>` | required | both | Output path. Single mode writes JSON; matrix mode writes Markdown. |
| `--n-samples N` | 22500 | both | DeformSim sample count assumed in DGEMV total flops + disk estimates. 22500 = Center Pattern default. |
| `--switches s` | `pYQ` | both | TetGen switches. `pYQ` = piecewise linear complex + suppress numbers + quiet. |
| `--baseline P.ply` | none | matrix | Adds a labeled baseline row at the end of the comparison table. |
| `--label PATH=NAME` | none | matrix | Friendly label for a candidate PLY (default uses filename). Repeatable. |

**Single mode** writes a JSON with 12 keys: `input_ply`, `v_surface`, `v_tet`, `expansion_ratio`, `matrix_order_3v_tet`, `memory_peak_bytes_kl`, `dgetri_flops`, `n_samples`, `dgemv_total_flops`, `estimated_disk_per_run_bytes`, `tetgen_success`, `tetgen_switches`. (When `tetgen_success: false`, an extra `failure_reason` is added.)

**Matrix mode** writes a Markdown report with header (input/timestamp/N_samples/switches), pressure-dimension legend, results table (one row per input + optional baseline), and an interpretation block.

### 3.3 `scripts/run_pressure_matrix.ps1` (orchestrator)

| Parameter | Default | Effect |
|---|---|---|
| `-InputMvr` | required | Path to input `.mvr`. |
| `-OutDir` | required | Working directory for intermediate `.ply` and the final `pressure_matrix.md`. |
| `-CliExe` | required | Path to `mvr_to_mesh_cli.exe`. |
| `-PressureExe` | required | Path to `check_fem_pressure.exe`. |
| `-BaselinePly` | "" | Optional plate.ply for matrix baseline row. |
| `-NSamples` | 22500 | Forwarded to `check_fem_pressure --n-samples`. |

The script currently runs 6 built-in candidates: `direct`, `adaptive_iter1`, `adaptive_iter3`, `cgal_default`, `cgal_L005` (target_edge_length 0.05), `cgal_L010` (target_edge_length 0.10). It does not include `--uniform-subdivide`. If you need uniform candidates, run a uniform `mvr_to_mesh_cli` command first (for example `mvr_to_mesh_cli.exe ..\DataFlow\ShapeReconstruction\originalData\MVR\kidney.mvr --uniform-subdivide -o ..\DataFlow\ShapeReconstruction\outputs\PLY\kidney_uniform.ply`) and then add the generated `.ply` files manually to the matrix list (or extend `$candidates` in this script).

Per-candidate failures (e.g., `cgal_L005` may fail CGAL precondition on certain inputs) are warned and skipped; the report still produces with the surviving rows.

## 4. Algorithm Reference

Six meshing paths are exposed by `mvr_to_mesh_cli`. The following kidney.mvr V_surf numbers are from real runs (see `pressure_matrix.md` produced by `mvrmesh_pressure_matrix_kidney` ctest, plus the manual uniform probe recorded in `D:/MedSim2Learn/docs/verification/ShapeReconstruction/2026-05-04-uniform-subdivision-roster.md`):

### 4.1 Direct extraction (default, no flags)

`parse_mvr` -> `boundary_faces_from_tets` -> `write_ply`.

- No repair, no remesh: 1:1 transcoding from .mvr boundary
- Triangle count: equal to input boundary face count
- kidney.mvr -> V_surf = 424, F = 500
- **When to use**: input is already clean and the goal is just format conversion.

### 4.2 `--adaptive-remesh`: curvature-driven subdivision

`build_surface` runs `algorithms::adaptive_remesh` after boundary extraction.

For each iteration, triangles whose face-normal angle versus their neighbors exceeds the split ratio threshold are subdivided at midpoints.

- Controlled by `--adaptive-iterations N` (passes) and `--adaptive-split-ratio R` (trigger)
- Strictly increases triangle count; no quality guarantee
- Does NOT repair self-intersection
- kidney.mvr -> V_surf 424 -> 839 (iter1) -> 5537 (iter3, 13x input)
- **When to use**: G3 increase is the priority and input mesh is already valid.

### 4.3 `--uniform-subdivide`: shape-preserving global subdivision

`build_surface` runs `algorithms::uniform_subdivide` after boundary extraction.

Each pass splits every triangle into four triangles by inserting edge midpoints. Shared edges reuse the same midpoint vertex, and no smoothing, projection, or relaxation is applied.

- Controlled by `--uniform-iterations N`
- Face count is exactly multiplied by 4 per pass
- Shape fidelity is prioritized because original vertices stay in place and new vertices lie on current triangle edges
- Does NOT repair self-intersection and does NOT equalize triangle quality as strongly as CGAL
- kidney.mvr manual probe -> output vertices = 1174, faces = 2000 for `--uniform-iterations 1`
- **When to use**: you need predictable denser candidates for `check_fem_pressure` while preserving the current surface shape.

### 4.4 `--uniform-subdivide --taubin-smooth`: accepted mesh-in-place smoothing path

`build_surface` runs `algorithms::uniform_subdivide`, then applies Taubin smoothing through `smoothing::taubin_smooth`.

Taubin smoothing alternates a positive smoothing step and a negative compensation step. This reduces the faceted look from pure subdivision while limiting global shrinkage compared with plain Laplacian smoothing.

- Controlled by `--uniform-iterations N`, `--taubin-iterations N`, `--taubin-lambda X`, and `--taubin-mu X`
- Keeps the mesh-in-place workflow: it does not run SDF reconstruction and does not change topology beyond uniform subdivision
- Was selected from the first-round mesh-in-place race by combined metric review and MeshLab visual review
- Does NOT repair self-intersection; use `--cgal-mesh` or `--sdf-reconstruct` when repair or implicit reconstruction is required
- **When to use**: you need the accepted shape-preserving high-density surface candidate from the main `mvr_to_mesh_cli` workflow.

### 4.5 `--sdf-reconstruct`: accepted implicit reconstruction + CGAL remesh path

`build_surface` rebuilds the boundary surface with `reconstruct_surface_sdf`, then applies CGAL repair/remesh through `run_cgal_mesh`.

This is the accepted product migration of the closed FEM-budget race. It is not a race mode and writes one `.ply`.

- Controlled by `--sdf-resolution N`, `--sdf-target-edge-length L`, `--sdf-padding-ratio R`, `--sdf-remesh-iterations N`, and `--sdf-sharp-edge-degrees D`
- Default parameters match the accepted `budget_sdf72_L025` result
- Produces a closed, continuous, more uniformly remeshed surface than the mesh-in-place path on the tested kidney data
- Can reproduce the highest-precision reference path with `--sdf-resolution 96 --sdf-target-edge-length 0`
- FEM pressure is evaluated separately through `check_fem_pressure`
- **When to use**: you need the selected high-quality reconstruction product rather than a mesh-in-place subdivision of the original triangles.

### 4.6 `--cgal-mesh`: CGAL 2-stage robust pipeline

Stage 1 (repair, `polygon_soup_to_polygon_mesh`): handles self-intersections, duplicate polygons, degenerate faces, Mobius-strip topology, hole insertion.

Stage 2 (`PMP::isotropic_remeshing`): sharp edges (dihedral > `--sharp-edge-degrees`) are protected; non-sharp edges are remeshed to length ~= `--target-edge-length`.

- Controlled by `--target-edge-length L`, `--remesh-iterations N`, `--sharp-edge-degrees D`
- Triangle count moves toward the implied target; can either **decrease or increase** depending on L vs current mean edge length
- Quality guarantee from Stage 2 is high
- kidney.mvr -> V_surf 424 -> 292 (cgal default, L=mean edge -> mild simplification) -> 140 (`-L 0.10` -> coarser)
- **When to use**: input has self-intersections, or G3 quality is the priority over raw triangle count.

### 4.7 Choosing an algorithm

```
input has self-intersection?
  yes -> --cgal-mesh
  no  -> need accepted high-quality reconstruction product?
           yes -> --sdf-reconstruct
           no  -> need shape-preserving higher density?
                    yes -> need smoother visual surface?
                             yes -> --uniform-subdivide --taubin-smooth
                             no  -> --uniform-subdivide
                    no  -> need feature-focused local growth?
                             yes -> --adaptive-remesh
                             no  -> direct
```

For kidney.mvr specifically, `cgal_L005` (target 0.05) fails CGAL's `protect_constraints` precondition because the input mesh has sharp edges of length ~0.0676, exceeding the required 4/3 * 0.05 = 0.0667. See Section 7 Troubleshooting.

## 5. DeformSim Integration

ShapeReconstruction's output `.ply` is consumed by the `DeformSim` sibling project as the deforming object input. DeformSim's reference fixture is `DataFlow/DeformSim/fixtures/plate.ply`, a 2D plate mesh with V_surf = 1922, F = 3840.

### 5.1 Format contract

- **ASCII PLY** (binary unsupported)
- Header: `format ascii 1.0`, `element vertex N`, `property float x/y/z`, `element face M`, `property list uchar int vertex_indices`
- Triangle faces only (`3 i j k` per face)
- Coordinates in input MVR's coordinate system (no rescaling)

### 5.2 Pressure matrix workflow

The recommended flow when introducing a new mesh into DeformSim:

1. **Generate candidates** via `scripts/run_pressure_matrix.ps1` (or run `mvr_to_mesh_cli` manually with different flags)
2. **Evaluate** with `check_fem_pressure --matrix` to produce `pressure_matrix.md`.
3. **Find sweet spot**: rows where `Memory (K+L)` < plate.ply baseline (526 MiB) AND `V_surf` is at or above the input's natural complexity
4. **Generate the chosen mesh** as the actual deliverable
5. **Hand off** the chosen `.ply` to DeformSim

### 5.3 Empirical sweet spot for kidney

From the `mvrmesh_pressure_matrix_kidney` CTest output (lives under the build directory at `..\build\ShapeReconstruction\vs2022-x64\pressure_matrix_kidney\pressure_matrix.md`):

| Config | V_surf | Memory (K+L) | vs plate baseline |
|---|---|---|---|
| direct | 424 | 24.7 MiB | 0.05x PASS very light |
| adaptive_iter1 | 839 | 96.7 MiB | 0.18x PASS light |
| adaptive_iter3 | 5537 | 4.20 GiB | 8.2x FAIL infeasible |
| cgal_default | 292 | 11.7 MiB | 0.02x PASS extra light (but G3 reverses) |
| cgal_L010 | 140 | 2.7 MiB | 0.005x PASS minimal (G3 strongly reversed) |
| **plate.ply (baseline)** | 1922 | 526 MiB | 1.00x |

`adaptive_iter1` is the closest non-baseline candidate to plate's complexity scale while keeping memory well under baseline; this is a reasonable G3 sweet spot.

`adaptive_iter3` demonstrates the FEM cost ceiling: increasing V_surf past ~2500 vaults memory past plate baseline by integer multiples.

## 6. FEM Pressure Model

DeformSim solves a finite-element problem on the tetrahedralized version of the input surface. The 4 cost dimensions `check_fem_pressure` projects:

| Dimension | Formula | Physical meaning |
|---|---|---|
| Memory peak (K + L) | `2 * (3*V_tet)^2 * 8 bytes` | Two dense matrices: K (stiffness) + L (= K^-1), held simultaneously by ADMM solver |
| DGETRI flops | `2 * (3*V_tet)^3` | One-time LAPACK matrix inversion |
| DGEMV total flops | `2 * (3*V_tet)^2 * N_samples` | Per-sample force-to-displacement solve, summed over all samples |
| Output disk | `N_samples * (V_surf * 64 + 256)` bytes | Per-sample output PLY, ASCII text |

`V_tet` is the TetGen output vertex count. For closed surfaces, V_tet >= V_surf (Steiner points added to fill volume); for open surfaces, V_tet = V_surf (no interior points).

### 6.1 DGETRI vs DGEMV crossover

DGETRI is one-time, scaling cubically with V_tet. DGEMV runs N_samples times, scaling quadratically.

For DeformSim's default N_samples = 22500 and TetGen expansion ratio ~= 3 (typical for closed organ surfaces):

```
DGETRI = DGEMV  <=>  2*(3*V_tet)^3 = 2*(3*V_tet)^2 * 22500
                 <=>  3*V_tet = 22500
                 <=>  V_tet = 7500  =>  V_surf ~= 2500
```

- Below V_surf ~= 2500: DGEMV total dominates (sample work outweighs one-time inversion)
- Above V_surf ~= 2500: DGETRI dominates (one-time inversion is cubically expensive)

For kidney.mvr (V_surf <= 5537 in tested candidates), the V_surf=2500 line is straddled; adaptive_iter3 is past it (DGETRI-bound), all others are below it (DGEMV-bound).

### 6.2 Worked example (kidney direct, V_surf = 424)

- V_tet = 424 (kidney is open surface, no Steiner points)
- (3*V_tet)^2 = 1272^2 = 1,617,984
- Memory = 2 * 1,617,984 * 8 = 25,887,744 bytes ~= 24.69 MiB
- DGETRI = 2 * 1272^3 = 4,116,151,296 ~= 4.12 * 10^9
- DGEMV total = 2 * 1,617,984 * 22500 = 7.28 * 10^10
- Output disk = 22500 * (424 * 64 + 256) = 616,320,000 bytes ~= 587.77 MiB

These match the JSON `check_fem_pressure` produces.

## 7. Troubleshooting

Common errors, ordered by frequency:

### 7.1 `Required TetGen file not found: .../predicates.cxx`

`TETGEN_ROOT` points at a missing or wrong path. The default is the
workspace-vendored copy at `../third_party/tetgen-1.6.0`; if the assertion
fires, either restore that directory or override at configure time:
`cmake --preset vs2022-x64 -DTETGEN_ROOT=C:/path/to/tetgen-1.6.0`

### 7.2 CGAL `protect_constraints` precondition violated

Symptom: `--cgal-mesh --target-edge-length L` fails immediately with a CGAL precondition error during Stage 2.

Cause: input mesh has sharp edges of length > 4/3 * L. CGAL's protected isotropic remesher cannot guarantee preservation if sharp edges are too long relative to the target.

Fixes (any one):
- **Decrease L** (target a smaller edge)
- **Increase `--sharp-edge-degrees`** (relax sharp detection so fewer edges are constrained)
- **Use `--cgal-mesh` without `--target-edge-length`** (auto target = mean input edge, never violates)

For kidney.mvr the sharp edge length is ~0.0676. `--target-edge-length 0.10` works; `--target-edge-length 0.05` doesn't.

### 7.3 `step 2 (remesh): every edge detected as sharp`

`--sharp-edge-degrees` is too low for the input mesh. Common on small fixture meshes (e.g., the corner tetrahedron `tiny_surface.mvr` has all dihedral angles > 60 degrees).

Fix: pass `--sharp-edge-degrees 130` (used by the CTest fixture).

### 7.4 `cmake --preset` fails to find CGAL

`VCPKG_ROOT` not set, or the manifest install failed during configure.

Fix: set `VCPKG_ROOT` and reconfigure -- manifest mode (`vcpkg.json`) installs
the pinned `cgal`/`yaml-cpp` into the build tree automatically:
```powershell
$env:VCPKG_ROOT = "C:\path\to\vcpkg"
cmake --preset vs2022-x64
```
The first configure on a cold machine builds the dependencies from source
(long); with a warm vcpkg binary cache it restores in seconds.

### 7.5 TetGen `exit(1)` terminates the CLI

Stock TetGen 1.6 calls `exit(1)` on internal errors. Our build patches the vendored source to call `terminatetetgen(1)` instead, so callers can catch the exception. The `mvrmesh_tetgen_no_direct_exit` CTest enforces this.

If that test fails: the vendored TetGen source has been reset (e.g., re-cloned). Re-apply the `exit(1)` -> `terminatetetgen(1)` patch.

### 7.6 `mvr_to_mesh_cli -o foo.0.05` produces unexpected filename

Latent CLI quirk: the `-o` argument is parsed as `<basename>.<extension>`. `foo.0.05` is interpreted as basename `foo.0` + extension `.05` (rejected as not `.ply`).

Fix: use base names without dots. The matrix orchestration script (`run_pressure_matrix.ps1`) uses `cgal_L005` instead of `cgal_L0.05` for the same reason.

## 8. Extending the Repo

### 8.1 Adding a new mesh algorithm

Typical locations to touch:

1. `include/mvrmesh/core/subdivision.h` (or `curvature.h`, `compaction.h`) - add the function declaration
2. `src/core/subdivision.cpp` (or matching `.cpp`) - add the implementation
3. `include/mvrmesh/core/types.h` - add a `SurfaceMode` enum value if the algorithm is a new pipeline mode
4. `include/mvrmesh/config/pipeline_config.h` - add a per-mode config sub-struct and field in `PipelineConfig`
5. `src/config/pipeline_config.cpp` - add validation rules in `validate()`, mode name in `parse_surface_mode`/`surface_mode_name`
6. `src/config/config_loader.cpp` - add YAML section loader and CLI flags for the new mode
7. `src/core/pipeline.cpp` - route the new mode through `build_surface`
8. `verification/core/smoke_tests.cpp` - add a unit test
9. `cmake/MvrmeshTests.cmake` - add CLI smoke coverage
10. `README.md` - update Section 4 Algorithm Reference
11. `scripts/run_pressure_matrix.ps1` - optionally add a row to the `$candidates` array (use a basename with no dots; see Section 7.6)

### 8.2 Adding a new FEM pressure dimension

Four locations to touch:

1. `include/mvrmesh/pressure/pressure_metrics.h` - extend `PressureMetrics` struct with the new field
2. `src/pressure/pressure_metrics.cpp` - populate the field in `compute_metrics`, add to `write_single_json` and `write_matrix_md`
3. `verification/cmake/run_check_fem_pressure_single.cmake` - add the new key to the `foreach(key ...)` substring check
4. `README.md` - update Section 6 FEM Pressure Model with the formula + worked example

### 8.3 Files that must NOT be modified

- `legacy/mvr_to_mesh.py` - kept untouched as the project's "anti-bloat mirror". Its existence reminds maintainers that the core functionality (read .mvr -> mesh -> write .ply) was originally a few hundred Python lines. New features must justify their complexity against this baseline.
- The workspace-vendored TetGen 1.6 source under `../third_party/tetgen-1.6.0/` should not be modified; the absence of direct `exit(1)` calls is enforced by the `mvrmesh_tetgen_no_direct_exit` ctest.

### 8.4 Build / test invariants

Whenever modifying CLI executables or their backing modules (`config_loader.cpp`, `cli_common.cpp`, `pressure_metrics.cpp`, `pressure_config.cpp`), verify:
- `ctest --preset vs2022-x64-debug` reports `100% tests passed, 0 tests failed` (all registered tests pass)
- `dumpbin /archivemembers <build>/Debug/mvrmesh.lib` shows ZERO TetGen-related .obj files (mvrmesh library must remain CGAL-only)
- `mvr_to_mesh_cli --help` (or no args) lists only currently supported flags
