# Graph Report - Deform_post  (2026-06-13)

## Corpus Check
- 25 files · ~19,416 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 304 nodes · 466 edges · 14 communities detected
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 52 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]

## God Nodes (most connected - your core abstractions)
1. `DataPreprocessor` - 19 edges
2. `main()` - 15 edges
3. `prep()` - 14 edges
4. `serialize_labels_dataset()` - 13 edges
5. `artifacts()` - 11 edges
6. `_recipe_from()` - 9 edges
7. `_cmd_camera()` - 9 edges
8. `run_sequence()` - 9 edges
9. `resolve_camera()` - 9 edges
10. `build_camera_params()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `_cmd_camera()` --calls--> `save_profile()`  [INFERRED]
  main.py → dpost/camera/profile.py
- `_recipe_from()` --calls--> `load_recipe()`  [INFERRED]
  main.py → dpost/config.py
- `_cmd_prep()` --calls--> `prep()`  [INFERRED]
  main.py → dpost/replay.py
- `_cmd_simulate()` --calls--> `run_deformsim_replay()`  [INFERRED]
  main.py → dpost/simrun/single.py
- `_cmd_artifacts()` --calls--> `artifacts()`  [INFERRED]
  main.py → dpost/artifacts.py

## Communities (14 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (44): accessible_zone(), _assemble_annotation(), _bfs_within(), build_annotation(), _build_parser(), compute_freeze(), flatness_metric(), local_thickness() (+36 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (25): DataPreprocessor, parse_resize(), Vision-force pair serialization: PNG dir + labels CSV -> .pt batches.  DataPrepr, Configure per-axis force scaling ({'x_scale','y_scale','z_scale'})., Load the single force CSV -> {SampleID: (fx, fy, fz)}., Process a single image and return the processed tensor., Force tuple -> tensor, scaled per axis when normalization is on., Save one batch via a thread pool so the event loop keeps processing. (+17 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (29): build_camera_params(), Deterministic camera placement around a contact point., Fixed oblique laparoscope PinholeCameraParameters centered on `center`.      The, intrinsic_matrix(), look_at_extrinsic(), Camera math: look-at extrinsics and pinhole intrinsics for Open3D., World->camera 4x4 extrinsic (open3d convention: camera looks down +z,     image, Camera placement for sequence rendering.  Every renderer in this package consume (+21 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (29): _cmd_artifacts(), artifacts(), compute_maxu(), _find_sim_ply_dir(), _label_tile(), _load_labels(), _montage(), _montage_pngs() (+21 more)

### Community 4 - "Community 4"
Cohesion: 0.1
Nodes (27): contact_normal(), Mesh loading and per-vertex contact queries shared across the pipeline., Return (world_coords, outward_unit_normal) at the contact seed vertex., _delete_files(), prep(), Per-sequence replay pipeline: prep and end-to-end orchestration.  prep turns one, Record run progress so the batch driver can attribute failures to a stage., One sequence end to end: prep -> sim -> render -> serialize (-> artifacts). (+19 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (20): pick_camera(), Interactive viewpoint picking (windowed Open3D preview).  The picker opens the m, Open an interactive preview and return the user's final camera.      The returne, _build_parser(), _cmd_assemble(), _cmd_batch(), _cmd_camera(), _cmd_forcegen() (+12 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (22): assemble(), assign_sequences_to_splits(), build_split_payload(), discover_ready_sequences(), main(), _materialise_batch(), _normalise_seq_token(), parse_args() (+14 more)

### Community 7 - "Community 7"
Cohesion: 0.13
Nodes (15): _apply_section(), BatchConfig, load_recipe(), MaterialConfig, Experiment recipe: defaults, YAML loading, and validation.  A recipe collects ev, Return a path field with {workspace}/{dataflow} expanded., Overlay a YAML mapping onto a dataclass instance, rejecting unknown keys., Load a recipe YAML over the defaults; None returns pure defaults. (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (16): generate_variants(), Real-referenced force trajectory synthesis.  The original repository sampled tra, Write `count` validated variants of `source_csv` into out_dir.      Outputs per, Placeholder for the distribution-fitting mode.      Intended approach when neede, Generator invariants on a press-like synthetic waveform; raises on failure., Rodrigues rotation matrix about `axis` (need not be unit)., Linear-interpolate an (N, 3) trajectory onto n_new evenly spaced frames., One synthetic variant of `F_src`; returns (F_new, params).      params records t (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.14
Nodes (14): expand_seq_list(), Batch driver: run many sequences with throttled process-level parallelism.  Each, Run every sequence in `seq_list`; returns (n_ok, n_fail, batch_log_path)., expand_seq_list contract; raises AssertionError on failure., Expand seq tokens and inclusive 'NN..MM' ranges, preserving zero-padding.      C, Run one sequence subprocess; return its result row dict., run_batch(), _run_one() (+6 more)

### Community 11 - "Community 11"
Cohesion: 0.5
Nodes (3): expand(), Workspace-anchored path resolution.  The MedSim2Learn workspace keeps data under, Expand {workspace}/{dataflow} placeholders and normalize separators.

### Community 12 - "Community 12"
Cohesion: 0.5
Nodes (3): default_worker_count(), Host-runtime heuristics.  The pipeline's parallelism unit is the SEQUENCE (whole, Logical cores minus a reserve for the OS/render thread, at least 1.

## Knowledge Gaps
- **131 isolated node(s):** `Deform_post command-line entry point.  Single front door for the kidney digital-`, `Load the recipe named by --config (or the default when it exists).`, `Kidney pose snapshot + DeformSim annotation generator.  Loads a canonical (lying`, `Fraction of faces whose normal aligns with +z (top) and -z (bottom).`, `Axis-aligned bounding box (min, max) enclosing all geometries.` (+126 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_sequence()` connect `Community 4` to `Community 9`, `Community 5`, `Community 1`?**
  _High betweenness centrality (0.198) - this node is a cross-community bridge._
- **Why does `prep()` connect `Community 4` to `Community 2`, `Community 3`, `Community 5`?**
  _High betweenness centrality (0.183) - this node is a cross-community bridge._
- **Why does `serialize_labels_dataset()` connect `Community 1` to `Community 4`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `prep()` (e.g. with `_cmd_prep()` and `load_mesh()`) actually correct?**
  _`prep()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `serialize_labels_dataset()` (e.g. with `_cmd_serialize()` and `run_sequence()`) actually correct?**
  _`serialize_labels_dataset()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Deform_post command-line entry point.  Single front door for the kidney digital-`, `Load the recipe named by --config (or the default when it exists).`, `Kidney pose snapshot + DeformSim annotation generator.  Loads a canonical (lying` to the rest of the system?**
  _131 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._