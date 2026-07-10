# Force-prior: what does a "reasonable" synthetic force look like

- **ID:** `2026-07-03_force-prior`
- **Date:** 2026-07-03 – (open)
- **Status:** `in-progress` (Track A of the 2026-07-03 redirection; gates all force generation beyond the twin)
- **Owner:** WENHUIZ

## Purpose / hypothesis
Under the 2026-07-03 redirection (train synth-only, transfer to real, zero real force
labels) the synthetic **force** distribution must stay tethered to what real operation
actually produced. The digital twin replays real sensor forces, so the real-domain force
labels are a **glimpsed-but-valid empirical reference** (a sample of what exists, not the
full distribution). This experiment answers **RQ-force / H5**: what magnitude / direction /
temporal envelope must a synthetic force trajectory respect so it does not inject harmful
noise → wrong FEM deformation → wrong image→force teaching?

The current pipeline polices force **identity** (correct image↔force pairing) but never
force **plausibility** (no NaN / range / physical-sanity check). This work supplies the
missing acceptance gate.

## Setup (reproduce)
- **Code:** `experiments/2026-07-03_force-prior/force_envelope.py` (this commit).
- **Data:** `DataFlow/Deform_post/preprocessed/datasets/real` (31 seq / 52522 frames; twin
  force labels == paired real by construction, so real fully characterises the envelope).
- **Env:** `/home/wenhui/rag_parsers_venv/bin/python` (torch 2.12, numpy 2.4; matplotlib
  absent on this venv → figure step skipped, JSON emitted).
- **Command:**
  ```
  python experiments/2026-07-03_force-prior/force_envelope.py \
    --data-dir DataFlow/Deform_post/preprocessed/datasets/real --domains real \
    --contact-floor 0.5 \
    --forces-cache DataFlow/Deform_post/preprocessed/analysis/forces_real.npz \
    --out-json DataFlow/Deform_post/preprocessed/analysis/force_envelope_real.json \
    --out-fig  DataFlow/Deform_post/preprocessed/analysis/force_envelope_real.png
  ```
  (`--forces-cache` writes a ~1.3 MB `.npz` of the extracted forces on first run and reuses it
  after, so re-derivations never re-read the 42 GB `.pt` tiers.)

## Results (empirical reference envelope, raw sensor Newtons)
| quantity | value |
|---|---|
| magnitude mean / median | 0.782 / 0.310 N |
| magnitude q95 / q99 / max | 2.83 / 3.47 / 4.43 N |
| axis x mean (q99, max) | 0.689 (3.24, 4.08) N — dominant |
| axis y mean (q01, q99) | 0.052 (−0.65, 0.58) N |
| axis z mean (q01, q99) | 0.089 (−0.27, 1.36) N |
| mean unit direction (active >0.5 N) | (0.983, 0.066, 0.17) — tight +x |
| direction cone half-angle q95 (active) | 26.6° around the mean |
| contact active fraction (>0.5 N floor) | 0.37 (≈63% of frames are gentle sub-contact) |
| frame-to-frame rate q99 / max | 0.254 / 0.849 N per frame (30 fps) → smooth |

- **Artifacts:** `DataFlow/Deform_post/preprocessed/analysis/force_envelope_real.{json,log}`
  (figure pending a matplotlib-equipped env).
- **Acceptance gate:** `force_envelope.is_plausible(force_seq, envelope)` rejects a candidate
  trajectory on NaN/Inf, peak |f| above `magnitude.q99` (3.47 N), or peak frame-rate above
  `rate_per_frame.q99` (0.254 N/frame). The refined envelope adds a fourth available check —
  active-frame direction within the 26.6° q95 cone around +x — which should be wired into
  `is_plausible()` before any algorithmic force generation (a small follow-up). These are the
  numeric priors any generator must clear.

## Literature cross-check (see `LITERATURE.md`, existence-only survey)
The empirical envelope is **corroborated** by verified measurements for our exact tissue+tool class:
- Our **max 4.43 N** sits just under the **±5 N** tip sensor Otsuka et al. (*Sci. Reports* 2024,
  ex-vivo porcine kidney, sensorized forceps) used, and their surgeon-set **0.5 N "over-force"
  floor** is consistent with our low-contact mass (our median 0.31 N < 0.5 N → many frames are
  gentle/near-contact). da Vinci ex-vivo porcine per-task numbers (manipulation mean 1.5–3.3 N,
  retraction peak ~10 N, 0.5 N contact floor) bracket our q99 3.47 N from above. Damage onset is
  far higher (bowel serosa ≈330 kPa ≈ single-digit N over a grasp footprint; muscle ≥50 N).
  **Verdict: the twin/real forces are physically plausible for porcine-kidney forceps manipulation
  — using them as the reference envelope is defensible.** This directly answers "how do we know the
  synthetic force is reasonable?": it matches the only tissue-matched sensor evidence that exists.
- **Load-bearing negative:** NO public, downloadable, real intraoperative tool-tissue force-sequence
  dataset exists (JIGSAWS/ROSMA/dVRK have no force channel; SurgSync is binary contact; DaFoEs/
  Marban/Chua are phantom-bench with no confirmed open download). So the twin is genuinely our best/
  only reference — tethering to it is **necessary**, not merely cautious. Conversely, literature has
  **no** published per-frame magnitude distribution or dF/dt for kidney, so our envelope supplies
  something the field lacks (a small novelty).

**Refined acceptance gate (supersedes the raw first pass):** contact-on floor **0.5 N (absolute,
from literature)** — replaces the circular q10; soft magnitude ceiling **q99 ≈ 3.47 N (our data)**;
hard ceiling anchored to the **±5 N** sensor range; rate bound **q99 ≈ 0.25 N/frame (our data)**;
plus a **force-time-product (sustained-force) bound**, since tissue damage scales with force×time,
not peak alone. dF/dt and contact-timing bounds remain **engineering assumptions** (literature has
none for kidney) and must be labeled as such.

## Caveats — resolved
1. **Contact fraction (was circular) — FIXED.** With the absolute 0.5 N literature floor,
   `active_fraction = 0.37` (≈63% of frames are gentle sub-0.5 N contact) instead of the
   trivial q10-based 0.90.
2. **Direction cone (was noise-inflated 98.6°) — FIXED.** Restricting to active (>0.5 N) frames
   gives a tight **q95 cone half-angle of 26.6°** around mean unit (0.983, 0.066, 0.17): real
   forces are strongly +x-directed, not near-isotropic. This is now a usable directional prior.
3. **Literature confirmation — DONE** (`LITERATURE.md`): the ranges agree with the tissue-matched
   Otsuka porcine-kidney sensor (±5 N) and da Vinci per-task forces; no public reference dataset
   exists, so the twin envelope stands as the reference.

## Verdict / disposition
- **Verdict:** the envelope is now **authoritative** for magnitude, rate, and (active-frame)
  direction — caveats fixed and literature-corroborated. Contact-timing / dF/dt fine structure
  beyond the pooled quantiles remains an engineering assumption (literature has none for kidney).
- **Disposition:** the envelope + `is_plausible()` gate is the sanctioned validator for any
  force generator (`dpost/forces/gen.py`); no twin-detached force may enter the FEM without
  passing it. Promote `force_envelope.py` into reusable infra (`KiDKNet/scripts` or
  `Deform_post/dpost/forces`) only once adopted as a pipeline gate.
- **Standing record also in:** `RESEARCH_GOAL.md` §6.6 / RQ-force / H5 (added 2026-07-03).
