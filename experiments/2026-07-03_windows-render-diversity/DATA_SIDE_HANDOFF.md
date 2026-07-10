# Data-side improvement — Windows local-agent context

> **Audience:** an AI coding agent on the user's **Windows** machine, repo at commit **`296bcfb`**. You do the Deform_post render/geometry/appearance/force work here. This document embeds every number, invariant, gate, and touch-point you need — you do **not** need any dev-branch code to act on it.
> **Language rule (workspace-wide):** all user-facing prose in Chinese; all code, identifiers, comments, commit messages in English; no emoji.

---

## 1. TL;DR + branch / coupling verdict

**Verdict (verified first-hand, this session):** commit `296bcfb` on your Windows machine is a **linear ancestor** of the dev branch `kidknet-experiments` (`cb8fea3`). Across `296bcfb..cb8fea3`, the three data sub-projects (`Deform_post`, `ShapeReconstruction`, `DeformSim`) changed **only `.vscode/settings.json`** — the pipeline **source is byte-identical**. Every dev change is in `KiDKNet/` + `experiments/` + research docs; there are **zero** uncommitted changes in the data sub-projects.

**What this means for you:**
- **Do NOT sync the experiment branch.** Your `Deform_post` code is already the code the dev side trained against. Pulling the experiment branch buys you nothing on the data side and risks dragging in training-side churn.
- **The one and only invariant to preserve is the `.pt` output contract** (Section 4). `Deform_post` **does not import `dknet`/`KiDKNet`** (grep-confirmed) — the sole link is a **one-directional data contract**: `Deform_post` *writes* `.pt` files that `KiDKNet/dknet/data/dataset.py::ForceDataset` *reads*. It is documented in comments at the top of `dpost/dataset/assemble.py` and `dpost/realvideo.py`.
- As long as your regenerated `.pt` files satisfy that schema, the (unsynced) training side consumes them with no code change.

**One-line mission:** close the **appearance domain gap** by making the synthetic renders both *more realistic* and *more diverse*, while keeping forces tethered to the twin — then ship qualified `.pt` back to the server.

---

## 2. Why this work (the diagnosis)

Under the zero-real-label sim→real reframe, the **appearance domain gap is the load-bearing bottleneck**. Established, above-noise findings (`report.md §4.1/§4.2`, `RESEARCH_GOAL.md §7.1/§7.3`, experiment `2026-06-15_8cond-cv-and-domain-gap`):

| Evidence | Number |
|---|---|
| Synthetic-only vs real-only magnitude MAE (single-frame, c2 vs c1) | **1.357 ± 0.456** vs **0.232 ± 0.073** (~6× worse) |
| Synthetic-only vs real-only (sequence, c6 vs c5) | **1.542 ± 0.097** vs 0.234 ± 0.023 |
| Synthetic-only force **direction** error | **55–60°** (near random) |
| Linear domain classifier (frozen ConvNeXt features) | **100% separable** (chance 50%) |
| Separation ratio = centroid dist / within-domain spread | **3.7** (≫1 → clouds far apart vs their own size) |
| Within-domain feature diversity (RMS spread) | real **7.64** vs synth **1.25** → synth **~6× less diverse** |

**Interpretation:** the forces already match real (by construction — magnitude-preserving sensor→model mapping, Section 7), so this is **not** a physics gap. It is an **appearance gap**: synthetic frames are uniformly white/low-variety and a trivial probe tells them apart 100% of the time. Every real-containing regime converges to the 0.20–0.24 band; synthetic adds no accuracy *because it looks wrong and looks the same everywhere*.

**Data-side lever =** make synthetic renders (a) **look more real** (photometry/appearance) and (b) **more diverse** (viewpoint, contact location, coloring) so the frozen-feature clouds overlap and diversify. This is exactly the "render-time randomization" that was *designed but blocked on Linux* (`report.md §4.7` — no headless GL/EGL). **Windows is where it runs.**

Diagnostic to re-measure after each change: `experiments/2026-06-15_8cond-cv-and-domain-gap/analyze_domain_gap.py` (read-only, CPU, no GPU/training) — reports separation ratio, linear-probe accuracy, and per-domain RMS spread from a mixed feature cache, and writes `domain_gap.png` + `domain_gap_points.json`.

---

## 3. Hard constraints

1. **Rendering runs on Windows** (controllability + the only place with working off-screen GL). Do not attempt headless rendering on the Linux box.
2. **Preserve the two fragile render invariants** in `dpost/render.py::render_fixed_camera_sequence` (Section 5, F1) — regressing either silently produces **blank/black PNGs**.
3. **Camera reproducibility:** one **fixed** camera per sequence, deterministic from config + saved profile. If you add viewpoint diversity it must be **seeded/reproducible**, not stochastic-per-run.
4. **Frame ↔ force `SampleID` pairing is sacred:** PNG stem == PLY stem (synt) / frame-force row index (real) == `labels.csv` `SampleID` == `.pt` sample `id`. Any drop/misalignment corrupts the dataset silently.
5. **Keep the `.pt` contract stable** (Section 4). This is the only thing coupling you to the unsynced training side.
6. **Forces stay tethered to the twin.** Never fabricate detached random forces (Section 7). Every training force must be an actual real recording or a validated envelope-bounded transform of one.
7. **Isolate-then-combine.** Measure each factor's *isolated* uplift (separability drop / diversity rise / gap-closed% on real test) before stacking factors. This mirrors the workspace rule "isolate one variable at a time, validate independently, combine only proven-beneficial changes."

---

## 4. The `.pt` output contract (do NOT break)

**Producer:** `Deform_post/dpost/dataset/serialize.py::DataPreprocessor.serialize` (thin wrapper `serialize_labels_dataset(png_dir, labels_csv, out_data_dir, resize=None)`).
**Consumer:** `KiDKNet/dknet/data/dataset.py::ForceDataset` — sorts `preprocessed_batch_*.pt` by name, concatenates, reads each sample's `"image"`/`"force"`/`"id"`.

### Per-sample schema (one Python dict per frame)
```python
{
    "id":    str,            # SampleID stem (see below); == PNG stem == PLY stem == labels row
    "image": FloatTensor,    # shape (3, 256, 256), CHW, values in [0, 1]  (raw uint8 / 255.0; NO ImageNet normalization)
    "force": FloatTensor,    # shape (3,), RAW sensor Newtons [fx, fy, fz]  (NO force normalization)
}
```
Exact producer behavior (`serialize.py::_process_image`): `PIL.convert("RGB")` → optional resize → `np.float32` → HWC→CHW `permute(2,0,1)` → `div_(255.0)` iff `max>1.0`. `serialize_labels_dataset` sets `normalize_images=False` and `normalize_forces=False`, so images stay `[0,1]` and forces stay raw N. Samples are batched (`batch_size` default **2000**) and written as `preprocessed_batch_{i:04d}.pt` via `torch.save`.

### Sidecar `metadata.yaml` (same dir; required by ForceDataset)
Written by `serialize.py::_serialize_async`. Fields: `total_samples`, `batch_size`, `num_batches`, `original_image_size`, `image_size`, `normalize_images`, `normalize_forces`, `force_normalization`, `image_mean`, `image_std`, `dataset_name`, `image_dir`, `processing_time`, `preprocess_date`. `ForceDataset` fails fast if `metadata.yaml` is missing or lacks required fields.

### `labels.csv` (serializer input)
Columns exactly: `SampleID,force_x,force_y,force_z`. `_load_force_data` pairs a PNG to its force **by stem** (`os.path.splitext(fname)[0] == SampleID`); a PNG with no matching row is dropped with a warning (see F3).

### SampleID conventions (stem identity chain)
- **Synthetic twin:** `deformed_s{seed:04d}_v{frame:04d}` — `dpost/forces/real.py::sample_id`. PNG stem == PLY stem (`render.py`: `out_png = splitext(ply)[0] + ".png"`).
- **Real video:** `real_s{seq}_v{i:04d}` — `dpost/realvideo.py::extract_sequence` (frame `i` ↔ force row `i`).

**Invariant to preserve char-for-char:** `SampleID (labels row) == PNG filename stem == source PLY stem (synt) == .pt sample "id"`. Keep image `(3,256,256)` in `[0,1]` and force raw `(3,)` N. That is the whole contract.

---

## 5. Robustness / inspectability fixes first (F1 / F2 / F3)

Do these **before** diversity work — they make silent data corruption loud, so later A/Bs are trustworthy. All are small, behavior-preserving guards.

### F1 — Render: fail loud on blank frames (protect the two fragile invariants)
**Anchor:** `Deform_post/dpost/render.py::render_fixed_camera_sequence`.
Two invariants there are load-bearing and easy to break during appearance/viewpoint edits:
1. **`vis.add_geometry(mesh, reset_bounding_box=(i == 0))`** — the bbox reset happens **only on frame 0** to seed the visualizer's z-near/z-far clip range. Without it the offscreen frame is **blank**; with it on every frame the camera re-centers.
2. **Baseline-camera merge:** read `ctr.convert_to_pinhole_camera_parameters()`, overwrite its `.intrinsic`/`.extrinsic`, then `convert_from_pinhole_camera_parameters(baseline, allow_arbitrary=True)`. Passing a **disk-loaded** `PinholeCameraParameters` straight into `convert_from` yields a **blank** frame even when bit-identical.

**Fix:** after `capture_screen_float_buffer`, assert the frame is non-blank, e.g. `assert float(buf.std()) > 1e-4, f"blank render at {stem} — camera invariant regressed"`. (The pattern already exists in `dpost/annotate.py::render_geoms`, which *returns* `buf.std()`.) This turns a silent black-PNG corruption into an immediate failure — the same class of bug that quarantined `twin_seq04` (its `04.mp4` is black; see `_excluded/blacklist.txt`).
**Acceptance:** run `main.py render` on one known-good sequence; every frame passes; deliberately break invariant (1) and confirm it now raises instead of writing black PNGs.

### F2 — Real extract: don't silently truncate misaligned frame/force pairs
**Anchor:** `Deform_post/dpost/realvideo.py::extract_sequence`.
Currently a `frame_count != force_rows` mismatch only prints a `[warn]` and pairs the first `min(n_frames, len(forces))`. A silent truncation can shift the frame↔force alignment for a whole sequence.
**Fix:** record the mismatch in a per-sequence sidecar (e.g. `alignment.json`: `n_frames`, `n_forces`, `paired`, `dropped`) and add a `strict=False` flag that raises when the gap exceeds a small tolerance. Do **not** change the default pairing math.
**Acceptance:** feed a deliberately short CSV; confirm the sidecar records the drop and `strict=True` raises.

### F3 — Serialize: assert full PNG↔force coverage (protect index ranges)
**Anchor:** `Deform_post/dpost/dataset/serialize.py::_serialize_async` (compare `matched_total` vs `len(image_files)`).
Unmatched PNGs are dropped with a warning; because `assemble.py` uses `metadata.total_samples` as the **authoritative** count and builds global index ranges from it, a silent drop shifts every downstream split index.
**Fix:** emit a one-line coverage report (`matched N / M PNGs, dropped K`) and add an opt-in assertion `matched_total == len(image_files)` (or a manifest of dropped stems) so a corrupted labels/PNG set can't quietly ship.
**Acceptance:** run serialize with one PNG missing its label row; confirm the coverage line and (opt-in) assertion fire.

---

## 6. Render / geometry diversity tracks (C1 / C2 / C3)

All three are **config-gated, default OFF**, seeded/reproducible, and evaluated the same way. Config lives in `Deform_post/dpost/config.py` (`RecipeConfig` / `CameraConfig` / `SerializeConfig`); `_apply_section` **rejects unknown keys**, so add any new knob as a dataclass field first.

**Shared acceptance protocol (isolate-then-combine):** for each track in isolation → regenerate a synt/mixed dataset → rebuild the mixed feature cache → run `analyze_domain_gap.py` and record (a) **linear-probe separability drop** (target: below 100% → ideally toward 50%), (b) **synth RMS diversity rise** (target: 1.25 → toward real's 7.64), (c) **gap-closed%** = how far c2/c6 magMAE moves from ~1.4–1.5 toward the real band (0.20–0.24) on the **real test slice**. Only combine tracks whose isolated uplift is positive.

### C1 — Appearance / coloring (highest expected payoff)
**Anchor:** `Deform_post/dpost/render.py::render_fixed_camera_sequence` — today `background=(1.0,1.0,1.0)` (white), `light_on=True`, `mesh_show_back_face=True`, **no material color / texture**. This uniform white render is the direct cause of the ~6× diversity deficit.
**Approach (config-gated, default OFF):** add an `appearance` config block; per-sample randomize background color/gradient, organ base color + optional texture, and light intensity/direction — **pixels only, labels untouched** (label-safe, exactly the property that made photometric aug safe in `report.md §4.6`). Seed from `sim.seed` + frame index for reproducibility.
**Why here, not training-time:** photometric *training* augmentation was tried and reverted (`experiments/…photometric-augmentation`, **LOSE**, `report.md §4.6`): mild stabilizer, no accuracy gain — consistent with "the obstacle is the render, not under-regularization." Fix the *source* renders instead.

### C2 — Viewpoint diversity
**Anchors:** `Deform_post/dpost/config.py::CameraConfig` (mode `auto`/`profile`/`absolute`; auto `eye_dir=(-0.47,-0.81,0.34)`, `up=(0,0,1)`, `standoff_mm=70`, `fov_deg=60`, `800×800`) and `dpost/camera/auto.py::build_camera_params` (+ `camera/geometry.py::look_at_extrinsic`, `intrinsic_matrix`). Today it is a **single fixed oblique laparoscope per sequence**.
**Approach (config-gated, default OFF):** add seeded per-sample jitter of azimuth/elevation/standoff **around the contact point** (the look-at target stays the contact — see the `up` degeneracy note in `CameraConfig` docstring: keep `up=+z`). Preserve reproducibility (jitter derived from a seed), and keep the F1 non-blank guard active.
**Note:** `render_fixed_camera_sequence` re-applies one extrinsic per sequence; for per-frame viewpoints you either pre-render per-view PLY sets or extend the loop to accept a per-frame camera list — keep both fragile invariants intact.

### C3 — Contact-point diversity
**Anchor:** `Deform_post/dpost/annotate.py::build_annotation` → `select_contacts` → `poisson_disk_centers` (over the `accessible_zone`). Today `--num-centers` Poisson-disk seeds on the accessible convex zone, deterministic from `rng_seed` (default 42).
**Approach (config-gated, default OFF):** increase `num_centers` and/or sweep `rng_seed` to sample more distinct contact locations (each center → one independent single-contact FEM sample), optionally relaxing zone params (`--zone-normal-deg`, `--zone-concave-max`, etc.) to broaden coverage without touching frozen/hilum exclusions. This diversifies *geometry of deformation*, complementary to C1/C2's pixel diversity.
**Acceptance:** same protocol; watch that added contacts don't violate the freeze/zone gates (`annotate.py` already asserts non-empty zone and centers-not-frozen).

---

## 7. Force-prior gate (embed it)

**Rule (non-negotiable):** every training force is either a **real sensor recording** or a **validated, envelope-bounded transform of one**. Never a free/detached random draw. This is the *tether-to-twin* rule.

### The mapping is magnitude-preserving (forces already match real)
`Deform_post/dpost/forces/real.py::sensor_to_model_rotation` builds an orthonormal, proper-rotation `R` (columns `[press=-n | t1 | t2]`) with self-checks (`R.T@R=I`, `det=+1`, `R@x=-n`). `map_forces` applies `F_model = R @ F_sensor`, so **`|F_model| == |F_sensor|`** and the label stays the raw sensor Newtons. This is *why the diagnosis is "appearance, not physics."*

### The envelope gate already exists, committed, standalone
The empirical envelope logic is `Deform_post/dpost/forces/gen.py::validate_resample` (torch/numpy-free; pure numpy). Synthesis (`resample_trajectory`) draws only bounded transforms of a real source:
`F_new(t) = scale · R_jitter @ F_src(warp(t))`, with committed bounds
`scale_range=(0.8,1.2)`, `warp_range=(0.9,1.1)`, `jitter_deg=5.0`, validated by
`roundtrip_rel_tol=0.05`, `peak_tol=1.001`, `step_tol=2.0`. Material/rate context: `young_mpa=0.03`, `poisson=0.49`, `fps=30`.

**Empirical envelope numbers are per-recording, not a fixed constant.** The absolute Newton bounds (peak `|F|`, max per-frame step, `|F|` histogram) are computed from each real CSV via `forces/real.py::load_real_forces` → `(N,3)` raw N. Compute the corpus-wide envelope with:
```python
import numpy as np, glob
from dpost.forces.real import load_real_forces
peaks, steps = [], []
for c in glob.glob(r"D:/Data Processpor/Origin_data/force_data/*.csv"):
    F = load_real_forces(c); mag = np.linalg.norm(F, axis=1)
    peaks.append(mag.max()); steps.append(np.abs(np.diff(F, axis=0)).max())
print("corpus peak |F| max:", max(peaks), "  max per-frame step:", max(steps))
```

### `is_plausible()` acceptance gate (copyable; thin wrapper over the committed logic)
```python
import numpy as np

# Committed tolerances (Deform_post/dpost/forces/gen.py::validate_resample)
PEAK_TOL, STEP_TOL = 1.001, 2.0          # peak-magnitude / smoothness slack
SCALE_RANGE, WARP_RANGE = (0.8, 1.2), (0.9, 1.1)

def force_envelope(F_real):
    """Empirical envelope of ONE real recording F_real (M,3) raw Newtons."""
    F = np.asarray(F_real, float).reshape(-1, 3)
    mag = np.linalg.norm(F, axis=1)
    step = float(np.abs(np.diff(F, axis=0)).max()) if len(F) > 1 else 0.0
    bins = np.linspace(0.0, max(float(mag.max()), 1e-12), 33)
    hist = np.histogram(mag, bins=bins, density=True)[0]
    return {"peak_mag": float(mag.max()), "max_step": step, "bins": bins, "hist": hist}

def is_plausible(F_cand, F_real, scale, warp, hist_l1_max=0.5):
    """(ok, reasons, stats) — is F_cand inside F_real's scaled/warped envelope?

    TETHER RULE: F_cand MUST be a transform of an actual real F_real, with
    scale in SCALE_RANGE and warp in WARP_RANGE — never a detached random draw.
    Mirrors gen.validate_resample's peak + smoothness + |F|-histogram checks.
    """
    assert SCALE_RANGE[0] <= scale <= SCALE_RANGE[1], "scale outside real envelope"
    assert WARP_RANGE[0]  <= warp  <= WARP_RANGE[1],  "warp outside real envelope"
    F = np.asarray(F_cand, float).reshape(-1, 3)
    env = force_envelope(F_real)
    mag = np.linalg.norm(F, axis=1)
    reasons = []

    peak_bound = scale * env["peak_mag"] * PEAK_TOL
    if float(mag.max()) > peak_bound:
        reasons.append(f"peak |F| {mag.max():.4g} > envelope {peak_bound:.4g}")

    if len(F) > 1 and env["max_step"] > 0:
        step = float(np.abs(np.diff(F, axis=0)).max())
        step_bound = STEP_TOL * (scale / warp) * env["max_step"]
        if step > step_bound:
            reasons.append(f"per-frame step {step:.4g} > bound {step_bound:.4g}")

    h_c = np.histogram(mag / max(scale, 1e-9), bins=env["bins"], density=True)[0]
    width = env["bins"][1] - env["bins"][0]
    hist_l1 = float(np.abs(env["hist"] - h_c).sum() * width)
    if hist_l1 > hist_l1_max:
        reasons.append(f"|F| hist L1 {hist_l1:.3f} > {hist_l1_max}")

    return (not reasons), reasons, {"peak_bound": peak_bound, "hist_l1": hist_l1}
```
If you generate variants at scale, prefer calling the committed generator `gen.py::generate_variants(source_csv, out_dir, count, ...)` directly — it writes each `<stem>_rK.csv` plus a `<stem>_rK.gen.json` provenance record (drawn params + validation stats) and **raises** on any envelope violation. The `is_plausible()` wrapper above is for gating forces produced by any other path.

> **Standalone tool note:** at `296bcfb` there is **no** separate `force_envelope.py`; the authoritative envelope/validation code is `dpost/forces/gen.py` (pure numpy). If dev later hands you a `force_envelope.py`, it is a lift of this same logic and can be copied in — but you don't need it; `gen.py` + the wrapper above are sufficient.

### Literature / negative-result rationale
- **Primary negative (first-hand, this project):** free/mismatched synthetic forces do **not** transfer — c2/c6 collapse to magMAE **1.357 / 1.542** with **55–60°** (near-random) direction. That is the empirical basis for the tether rule.
- **Corroboration (carry-over from the dev diagnosis — *confirm the exact citation against the dev run-notes before quoting it in any writeup*):** prior work on tissue-interaction force priors (Otsuka et al. line of work) reports that force labels must stay tied to the actual contact geometry / recorded envelope rather than sampled from unconditioned distributions; unconditioned/uniform-box force sampling degrades direction transfer. Treat the bibliographic details as **to-verify** — do not fabricate them.

---

## 8. "Qualified data" definition + upload-back-to-server protocol

### A `.pt` batch is *qualified* (ship-ready) only if ALL hold
1. **Schema exact:** every sample `{id:str, image:(3,256,256) float in [0,1], force:(3,) raw N}`; sidecar `metadata.yaml` present with a correct `total_samples`. (Section 4.)
2. **Pairing intact:** `SampleID == PNG stem == PLY stem (synt) == labels row`; F3 coverage assertion passes (`matched == len(pngs)`, no silent drops).
3. **Renders non-blank:** F1 per-frame std guard passed (no black PNGs); F2 alignment sidecar shows no unexplained truncation.
4. **Forces tethered:** every force is a real recording or an `is_plausible()`-passing (envelope-bounded) transform; `.gen.json` provenance exists for synthesized variants.
5. **Diversity moved the needle:** for a diversity-track dataset, `analyze_domain_gap.py` shows separability **< 100%** and/or synth RMS **> 1.25** vs the white-render baseline (record the numbers in an `experiments/<date>_<slug>/README.md` per the ledger policy).

### Where it lands on the server (so the unsynced training side consumes it)
The training side reads the **assembled** KiDKNet `data_dir`s, not raw renders. Pipeline (all Windows-local up to upload):

1. **Per-sequence build:** `main.py realbuild` (real) / `render`+`serialize` or `run`/`batch` (synt) → each `seqNN/{png/, labels.csv, dataset/preprocessed_batch_0000.pt + metadata.yaml}` under `DataFlow/Deform_post/primary/{real_full,twin_full}` (keep them **siblings** — `main.py` derives `real_full` from `dirname(out_root)`; `config.py out_root` defaults to `primary/twin_full`).
2. **Assemble into a KiDKNet `data_dir`:** `Deform_post/dpost/dataset/assemble.py` (via `main.py assemble`) — discovers READY sequences, hard-links each batch as `preprocessed_batch_{i:04d}.pt`, writes `sequence_index.json` + KiDKNet-compatible `metadata.yaml`, and authors a by-sequence `dataset_split.json` (disjoint + full-coverage asserted). Output lives under `DataFlow/Deform_post/preprocessed/datasets/{real,synt/{twin,gen},mixed}` (DOMAIN-organized; the per-sequence `.pt` sources are `preprocessed/sources/<domain>/`; `datasets/*` are same-volume hardlinks of `sources/*`).
3. **DataFlow 4-tier layout** (keep raw separate from regenerable): `inputs/` (hand-authored annotations + cameras), `primary/` (the only expensive bytes: `twin_full` PLY+800px renders, `real_full` 256px+labels), `preprocessed/` (regenerable sources + assembled datasets), `feature_cache/`, `_excluded/` (blacklist only). Superseded assembled sets are deleted (they regenerate via `assemble`).
4. **Upload only the two merged datasets + code** (`KiDKNet/SERVER_DEPLOY.md`), FEM/renders stay local:
   - `DataFlow/Deform_post/preprocessed/datasets/real/` — real 256² (**31 seq / 52,522 frames**; C1/C4/C5/C8).
   - `DataFlow/Deform_post/preprocessed/datasets/mixed/` — paired real+synt (**62 seq / 105,044 frames**; C2/C3/C6/C7).
   - `rsync -aHvz` both together (`-H` dedupes the hardlinked real half of `mixed`). Target `10.232.99.48`.
5. **Regenerate splits on the server (do NOT upload them):** `python scripts/author_cv_splits.py --real-merged $REMOTE/data/real --mixed-dir $REMOTE/data/mixed --out-dir $REMOTE/data/splits/cv5` — split JSONs bake an **absolute `data_dir`** validated char-for-char, so Windows paths fail on Linux; seed 42 reproduces identical fold membership with the server path baked in.
6. **Recompute features on the server (GPU):** `python -m dknet.data.feature_cache --source $REMOTE/data/real --out $REMOTE/data/feature_cache/real_feat_convnextL --size large` (then the same for `mixed → mixed_feat_convnextL`). One cache per source, reused read-only across folds; C5–C8 fail fast if missing.

> **Moving/renaming an assembled `datasets/<domain>` dir is a three-place edit, never a bare `mv`:** (1) the KiDKNet config `data_dir`, (2) the absolute `data_dir` baked in each split JSON, (3) feature-cache `source_data_dir`. Prefer **re-authoring splits** with the new path over `mv`+hand-patching. Same-disk renames preserve inodes/hardlinks (zero byte movement).

---

## 9. What NOT to do

1. **Do not sync / merge the experiment branch (`kidknet-experiments`).** Your data-pipeline code at `296bcfb` is already byte-identical to dev; syncing only imports unrelated training-side churn.
2. **Do not change the `.pt` contract.** Keep `image (3,256,256) ∈ [0,1]`, `force (3,) raw N`, `id == PNG stem == PLY stem == labels row`, and the `metadata.yaml` sidecar. It is the single coupling to the unsynced training side.
3. **Do not "clean up" the fragile render invariants** in `render.py::render_fixed_camera_sequence` — the frame-0-only `reset_bounding_box`, and the baseline-camera merge with `allow_arbitrary=True`. Either "simplification" reintroduces silent blank/black frames.
4. **Do not detach forces from the twin envelope.** No uniform-box / random force draws; every force is a real recording or an `is_plausible()`-passing bounded transform (Section 7). Detached forces are the documented cause of the c2/c6 collapse.
5. **Do not upload splits or feature caches** — regenerate/recompute them on the server (they bake absolute paths / are deterministic). Do not upload FEM renders / PLYs / `build/`.
6. **Do not stack diversity tracks before isolating each.** Measure C1/C2/C3 separately (separability drop, RMS rise, gap-closed% on the real test slice), then combine only the proven-positive ones. Log each in `experiments/<date>_<slug>/README.md` and `experiments/INDEX.md`.
7. **Do not commit with an AI/tool footer.** Commits are human-style Conventional Commits authored solely as `WENHUIZ`; let small changes accumulate for the user's commit decision unless this is an authorized overnight hand-off.
