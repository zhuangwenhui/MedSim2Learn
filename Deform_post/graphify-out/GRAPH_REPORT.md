# Graph Report - Deform_post  (2026-08-10)

## Corpus Check
- 27 files · ~24,375 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 386 nodes · 613 edges · 16 communities detected
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 71 edges (avg confidence: 0.8)
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
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]

## God Nodes (most connected - your core abstractions)
1. `DataPreprocessor` - 21 edges
2. `serialize_labels_dataset()` - 20 edges
3. `main()` - 15 edges
4. `prep()` - 14 edges
5. `_install_fake_o3d()` - 12 edges
6. `artifacts()` - 11 edges
7. `_recipe_from()` - 10 edges
8. `render_fixed_camera_sequence()` - 10 edges
9. `run_sequence()` - 10 edges
10. `_cmd_camera()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `_recipe_from()` --calls--> `load_recipe()`  [INFERRED]
  main.py → dpost/config.py
- `_cmd_prep()` --calls--> `prep()`  [INFERRED]
  main.py → dpost/replay.py
- `_cmd_artifacts()` --calls--> `artifacts()`  [INFERRED]
  main.py → dpost/artifacts.py
- `_cmd_forcegen()` --calls--> `generate_variants()`  [INFERRED]
  main.py → dpost/forces/gen.py
- `_cmd_camera()` --calls--> `load_mesh()`  [INFERRED]
  main.py → dpost/meshio.py

## Communities (16 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (31): DataPreprocessor, parse_resize(), Vision-force pair serialization: PNG dir + labels CSV -> .pt batches.  DataPre, Configure image resizing options., Configure image normalization (mean/std default to ImageNet)., Configure per-axis force scaling ({'x_scale','y_scale','z_scale'})., Opt in to the F3 coverage assertion (matched PNGs == total PNGs).          Whe, Load the force CSV -> {SampleID: (fx, fy, fz)}.          Prefers the explicit (+23 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (37): _cmd_render(), _append_render_error(), _assert_not_blank(), interactive_render_confirmation(), Headless fixed-camera sequence rendering (PLY -> PNG).  Two render invariants, Render ONE deformed PLY through the fixed camera to a preview PNG (F1).      S, Ask whether to proceed with the batch render after the F1 preview.      Mirror, Raise on a blank captured buffer (the F1 guard); returns the pixel std. (+29 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (44): accessible_zone(), _assemble_annotation(), _bfs_within(), build_annotation(), _build_parser(), compute_freeze(), flatness_metric(), local_thickness() (+36 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (33): build_camera_params(), Deterministic camera placement around a contact point., Fixed oblique laparoscope PinholeCameraParameters centered on `center`.      T, intrinsic_matrix(), look_at_extrinsic(), Camera math: look-at extrinsics and pinhole intrinsics for Open3D., World->camera 4x4 extrinsic (open3d convention: camera looks down +z,     image, Camera placement for sequence rendering.  Every renderer in this package consu (+25 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (35): contact_normal(), Return (world_coords, outward_unit_normal) at the contact seed vertex., prep(), prep round-trip on a synthetic mesh; raises AssertionError on failure., Build forces_model.csv / labels.csv / camera.json / replay_meta.json.      If, _self_test(), generate_variants(), Real-referenced force trajectory synthesis.  The original repository sampled t (+27 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (26): _build_parser(), _cmd_assemble(), _cmd_batch(), _cmd_forcegen(), _cmd_prep(), _cmd_realbuild(), _cmd_simulate(), main() (+18 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (30): _cmd_artifacts(), artifacts(), compute_maxu(), _find_sim_ply_dir(), _label_tile(), _load_labels(), _montage(), _montage_pngs() (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (25): assemble(), assign_sequences_to_splits(), build_split_payload(), discover_ready_sequences(), main(), _materialise_batch(), _normalise_seq_token(), parse_args() (+17 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (16): _apply_section(), BatchConfig, load_recipe(), MaterialConfig, Experiment recipe: defaults, YAML loading, and validation.  A recipe collects, Return a path field with {workspace}/{dataflow} expanded., Overlay a YAML mapping onto a dataclass instance, rejecting unknown keys., Load a recipe YAML over the defaults; None returns pure defaults. (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (15): build_from_pngs(), build_sequence(), circular_square_crop(), extract_sequence(), load_forces(), Real laparoscopic video -> image-force .pt dataset (synt-compatible contract)., Extract + serialize one real sequence to ``out_seq_dir`` (png/labels/dataset)., Re-process already-rendered PNGs to the shared size + circular-FOV spec. (+7 more)

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (14): _cmd_run(), _delete_files(), Per-sequence replay pipeline: prep and end-to-end orchestration.  prep turns o, Record run progress so the batch driver can attribute failures to a stage., Hard count reconciliation before serialize (the F3 synthetic-path guard)., One sequence end to end: prep -> sim -> render -> serialize (-> artifacts)., Delete files with `suffix` under root; returns the count removed., reconcile_sequence_counts() (+6 more)

### Community 13 - "Community 13"
Cohesion: 0.5
Nodes (3): expand(), Workspace-anchored path resolution.  The MedSim2Learn workspace keeps data und, Expand {workspace}/{dataflow} placeholders and normalize separators.

### Community 14 - "Community 14"
Cohesion: 0.5
Nodes (3): default_worker_count(), Host-runtime heuristics.  The pipeline's parallelism unit is the SEQUENCE (who, Logical cores minus a reserve for the OS/render thread, at least 1.

## Knowledge Gaps
- **151 isolated node(s):** `Deform_post command-line entry point.  Single front door for the kidney digita`, `Load the recipe named by --config (or the default when it exists).`, `Kidney pose snapshot + DeformSim annotation generator.  Loads a canonical (lyi`, `Fraction of faces whose normal aligns with +z (top) and -z (bottom).`, `Axis-aligned bounding box (min, max) enclosing all geometries.` (+146 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `serialize_labels_dataset()` connect `Community 0` to `Community 9`, `Community 10`?**
  _High betweenness centrality (0.223) - this node is a cross-community bridge._
- **Why does `run_sequence()` connect `Community 10` to `Community 0`, `Community 1`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.215) - this node is a cross-community bridge._
- **Why does `prep()` connect `Community 4` to `Community 10`, `Community 3`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `serialize_labels_dataset()` (e.g. with `_cmd_serialize()` and `build_sequence()`) actually correct?**
  _`serialize_labels_dataset()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `prep()` (e.g. with `_cmd_prep()` and `load_mesh()`) actually correct?**
  _`prep()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Deform_post command-line entry point.  Single front door for the kidney digita`, `Load the recipe named by --config (or the default when it exists).`, `Kidney pose snapshot + DeformSim annotation generator.  Loads a canonical (lyi` to the rest of the system?**
  _151 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._