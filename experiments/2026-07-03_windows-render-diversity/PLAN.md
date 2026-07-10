# Windows-side execution plan — render/geometry/appearance diversity + inspectability fixes

- **ID:** `2026-07-03_windows-render-diversity`
- **Owner:** WENHUIZ · **Executor:** the Windows-side agent (user-controlled render machine)
- **Status:** plan only — nothing here has run. Server-side prep is done; this is handed off.

This plan is **self-contained**: it does not depend on the chat that produced it. It tells the
Windows agent exactly what to change, what invariants must NOT be broken, how to prove the data
is good before it leaves the machine, and how to hand qualified data back to the Linux server.

---

## 0. Why Windows, and the hard constraints (read first)

Rendering runs **only** on the user-controlled Windows machine because the render correctness
rests on fragile Open3D invariants + human visual confirmation, both of which need a real
display the user can inspect and interrupt. The Linux-container headless-GL path is **out of
scope — do not try to make rendering work in the container.**

Hold these constraints (any violation invalidates the data):
- **Inference contract is fixed:** every produced sample is still `{id, image(3,256,256), force(3)}`;
  changes here only alter the *training image* (and, for contact diversity, *which* real force is
  applied where) — never the inference I/O.
- **Force stays tethered to the real/twin envelope.** This plan does **not** invent new force
  values. Contact-point diversity re-applies *existing real forces* at additional annotated
  seeds (same magnitude/direction → same empirical envelope, new deformation location). Any
  *algorithmically generated* force trajectory (forcegen) is OUT of scope for this plan until it
  passes the acceptance gate in `experiments/2026-07-03_force-prior/` (`is_plausible()`).
- **Provenance:** every diversity choice (color/lighting seed, viewpoint, contact seed) is
  recorded per sequence in `replay_meta.json` so a human can audit what produced each dataset.

### 0.1 Fragile render invariants that MUST be preserved (do NOT "clean up")
From the legacy `sim2vfp.py` (the hand-authored controllability record) and the current
`dpost/render.py::render_fixed_camera_sequence`. These two are load-bearing; a naive rewrite
produces **blank offscreen PNGs that still pair with real forces = silent garbage**:
1. `vis.add_geometry(mesh, reset_bounding_box=(i == 0))` — reset the bbox **only on frame 0** to
   seed z-near/z-far; every later frame `reset_bounding_box=False` so geometry never re-centres
   the camera.
2. Camera is applied by **mutating the visualizer's own baseline camera object** then
   `convert_from_pinhole_camera_parameters(baseline, allow_arbitrary=True)`. Passing a
   disk-loaded `PinholeCameraParameters` straight in yields a blank frame *even when bit-identical*.
Keep `background=(1,1,1)`, `light_on=True`, `mesh_show_back_face=True`, `compute_vertex_normals()`
per load, 800x800, and `PNG stem == PLY stem == SampleID`.

---

## 1. Do the three robustness/inspectability fixes FIRST (before generating any diverse data)

These restore what the current pipeline lost vs the legacy monolith and directly answer the
"don't let me be blindsided by bad data" requirement. Each is small and preserves the I/O contract.

- **F1 — deformed-frame preview + confirm gate (the main lost inspectability).**
  Today `main.py camera pick` only previews the static mesh. Add: render ONE real *deformed*
  frame (mid-sequence PLY) through the chosen camera and show it, with a `Proceed to batch-render
  this sequence? (y/n/q)` prompt (mirror the legacy `preview_random_ply_with_camera` +
  `interactive_render_confirmation`). Wire into the render entry (`main.py _cmd_render` →
  `render.py`). Gate is skippable with an explicit `--yes` flag for unattended batch, but
  interactive is the default.
- **F2 — per-frame render error isolation + log.** `render_fixed_camera_sequence` currently has
  no per-frame try/except: one corrupt PLY aborts the whole sequence. Wrap the per-frame body in
  try/except, log `filename,error_message` to `render_errors/error_log.csv`, continue, and return
  the ok/failed counts (as legacy `Renderer.render` did).
- **F3 — hard count reconciliation at serialize.** Before writing `.pt`, assert
  `#PLY == #PNG == #label-rows` for the sequence; refuse (raise) on mismatch instead of silently
  dropping unpaired frames. (The real-video path `realvideo.extract_sequence` already warns+truncates;
  give the synthetic path an equivalent *hard* check.)

**Acceptance for section 1:** re-run one existing twin sequence (e.g. seq01) end to end; byte-parity
with its current `.pt` must hold (F1/F2/F3 must not change correct output), and F2/F3 must trigger
on a deliberately corrupted PLY / dropped label.

---

## 2. Track C — geometry/appearance diversity factors (isolate, measure, then combine)

Add a config-gated `DiversityConfig` to `dpost/config.py` + `configs/kidney_twin.yaml` (+ its
`_validate`); **default OFF so current behaviour is unchanged.** Run each factor **in isolation
first**, regenerate the twin set, re-serialize, and measure that factor's isolated effect before
combining. Every factor keeps 1:1 force pairing.

### C1 — appearance / coloring (cheapest appearance lever)
- **Where:** `render.py::render_fixed_camera_sequence`, right after `compute_vertex_normals()`.
- **What:** start simple and measure the uplift of *just* this: `mesh.paint_uniform_color(...)`
  or per-vertex colors (kidney-like albedo), plus `opt.background_color` away from pure white,
  plus optional numpy post-process (brightness/contrast/gamma/vignette/mild noise) on the captured
  buffer. Randomize per-sequence or per-frame with a **recorded seed**.
- **Note:** vertex color works in the legacy GL `Visualizer`. Full PBR/texture/randomized-lighting
  needs an `OffscreenRenderer` swap — still Windows, but a bigger change; only do it if flat
  coloring's isolated uplift justifies it.

### C2 — rendering viewpoint diversity
- **Where:** `dpost/camera/auto.py::build_camera_params` (today a single fixed `eye_dir`).
- **What:** sweep azimuth / elevation / standoff around the organ; the existing
  `look_at_extrinsic` / `intrinsic_matrix` math already supports arbitrary eyes. Add a viewpoint
  suffix to `SampleID` so the 1:1 force pairing is preserved across viewpoints.
- **Keep** the per-sequence camera saved to `camera.json` + logged in `replay_meta.json`.

### C3 — contact-point diversity (envelope-safe; re-applies REAL forces)
- **Where:** `dpost/replay.py::prep` — today uses `ann["contacts"][0]["seed"]` (first contact only),
  but `annotate.select_contacts --num-centers 30` already authors ~30 candidate seeds.
- **What:** loop over `contacts[k]["seed"]`, each producing its own `forces_model.csv` /
  `camera.json` / `labels.csv` / deformed PLYs / renders. **The force label stays the real sensor
  force**, so the force distribution is unchanged (stays inside the empirical envelope by
  construction) — only the deformation *location* varies. This is the highest-diversity, lowest-risk
  factor.

**Acceptance for each C factor (isolate-then-combine):**
1. Regenerate → re-serialize → copy the new `.pt` to the server (section 4) → server runs
   `KiDKNet/scripts` feature recompute + `analyze_domain_gap.py`: the **separability must drop**
   from the current 100% / separation-ratio 3.7 / synth-diversity-RMS 1.25 (real 7.64).
2. Report each factor's isolated effect before combining. Only combine factors that individually
   help (CLAUDE.md: isolate one variable at a time, combine only proven-beneficial changes).

---

## 3. Track D — unpaired image translation (later, after Track C sets the DR ceiling)
Out of scope for the first hand-off. When reached: CUT/FastCUT → diffusion+ControlNet conditioned
on render depth/normal to lock geometry; **translate training synthetic frames offline**, keep
inference as raw-image→force. Needs Windows render (for conditioning maps) + a GPU for the
translator. Do not start until Track C's isolated numbers are in.

---

## 4. "Qualified data" definition + hand-off protocol to the server

**A produced dataset is QUALIFIED for upload only if ALL hold:**
- [ ] F1 preview was confirmed (a human saw a real deformed frame through the chosen camera).
- [ ] F2 error log is empty OR every failure is understood and acceptable; F3 count reconciliation passed.
- [ ] No blank/near-constant frames (spot-check montage from the `artifacts` QA stage; the two
      fragile invariants in §0.1 are intact).
- [ ] For any force that is NOT a verbatim real replay: it passed
      `experiments/2026-07-03_force-prior/force_envelope.py::is_plausible()` against
      `force_envelope_real.json`. (Track C1/C2/C3 replay real forces → trivially pass; this line is
      the guard for future forcegen.)
- [ ] `replay_meta.json` records the diversity settings (seeds/viewpoints/contacts) for provenance.

**Upload (Windows → server):** send only the regenerable *serialized* products, not the 13 GB/seq
800px raws:
- the new `preprocessed/sources/synt/<domain>/<seq>/*.pt` (256px serialized) + `metadata.yaml`,
- `replay_meta.json`, `camera.json`, `labels.csv`, and any `render_errors/error_log.csv`,
- a short `MANIFEST.txt`: what factor(s) were on, seeds, sample counts, QA sign-off.
Server destination: `DataFlow/Deform_post/preprocessed/sources/synt/<domain>/` then assemble into
`datasets/<domain>` via `dpost/dataset/assemble.py` + re-author splits with
`KiDKNet/scripts/author_cv_splits.py` (do NOT bare-`mv`; re-author so the baked absolute
`data_dir` in every split JSON is correct — see root CLAUDE.md DataFlow rules).

## 5. What the server does on receipt (then we decide on experiments)
1. Assemble + author splits (above).
2. Recompute ConvNeXt feature cache (no `feature_cache/` on the server yet) — GPU, deterministic.
3. Re-run `analyze_domain_gap.py`: confirm separability / separation-ratio / diversity moved.
4. Only then (per the owner) run Track B UDA experiments on the new + existing features.

---

## Appendix — exact touch-points (current tree)
- Render: `Deform_post/dpost/render.py::render_fixed_camera_sequence` (F1/F2, C1)
- Camera: `Deform_post/dpost/camera/{__init__.py::resolve_camera, auto.py::build_camera_params}` (C2)
- Replay/prep: `Deform_post/dpost/replay.py::prep` (C3), `_self_test` (keep force-label asserts)
- Serialize: `Deform_post/dpost/dataset/serialize.py` (F3)
- Config: `Deform_post/dpost/config.py` + `Deform_post/configs/kidney_twin.yaml` (+ `_validate`)
- Annotations: `Deform_post/dpost/annotate.py::select_contacts` (already authors ~30 seeds for C3)
- Force gate: `experiments/2026-07-03_force-prior/force_envelope.py` (+ `force_envelope_real.json`)
- Domain-gap check: `KiDKNet/scripts/analyze_domain_gap.py` (server side)
