# Track B: unsupervised domain adaptation (synth-only → real, no real labels)

- **ID:** `2026-07-03_trackb-uda`
- **Date:** 2026-07-03 – (open)
- **Status:** metric role **KEEP** (fossilised, §4e); training-loss role **NULL** (§4d full 5-fold, t=−0.70) → **PARK** (gated OFF, expiry 2026-10-31, §5). DANN not wired.
- **Owner:** WENHUIZ

## Purpose
Close the c2→c1 gap (synth-only zero-shot 1.357 → oracle 0.232 magMAE) by adapting a
synthetic-trained force regressor to real using ONLY unlabeled real images (no real force
labels). Inference stays image→3D force. Methods: Deep CORAL (feature alignment, first),
DANN (gradient-reversal adversarial). Config-gated, default OFF, byte-identical when off —
mirroring the existing `weighting='uncertainty'` pattern in `dknet/utils/losses.py`.

This plan was produced by an adversarial verification pass (4 verifiers vs the real code);
it **supersedes** an earlier unverified draft that had 10 concrete errors (recorded in §5).

## 1. Applicability matrix (verified)
| Method | c1–c4 single-frame (ConvNeXt fine-tuned) | c5–c8 sequence (ConvNeXt frozen, feature-cache) |
|---|---|---|
| Deep CORAL | **Applies** — align the 1536-d `model.backbone(x)` feature | **No-op for learning** — input is already the cached, out-of-graph feature; needs a trainable temporal-head tap (out of scope for Increment 2) |
| DANN (GRL) | **Applies** — same feature; target features MUST carry grad | Same limitation as CORAL |
| Tent (test-time BN) | **Not applicable** — ConvNeXt is LayerNorm; the only BatchNorm is in the c1–c4 regression head (not a legitimate Tent target) | **Not applicable** — zero BatchNorm in the temporal head |

**Scope for the first real experiment: CORAL on c1–c4.** Tent is dropped (no BN to adapt);
DANN follows CORAL.

## 2. Verified integration points (Increment 2 — needs greenlight)
Pattern to mirror (uncertainty weighting): conditional param registration `losses.py:244–250`;
validation gate `:210–215`; optimizer fold `force_trainer.py:423–424`; checkpoint `:951`;
metrics `isinstance` guard `metrics.py:150`; CLI/config plumbing `run_cv.py:109,133–137,276,354–355`.

- **Do NOT subclass `MagnitudeAngleLoss`** — it is called `loss_fn(outputs, targets)` (2-arg,
  positional, `force_trainer.py:768,785`) and never sees features; a subclass owning a module/
  buffer breaks byte-identity (`:423–424`, `:951`, `metrics.py:150`). Keep UDA as separate
  modules applied in the trainer (this is what `dknet/utils/uda.py` provides).
- **Deep CORAL normalisation** = `‖C_s−C_t‖²_F / (4·d·d)`, d=1536 (NOT `/(4d)`).
- **Feature reuse:** `ForceNet.forward` is `head(backbone(x))` (`force_net.py:69`); needs a
  behaviour-preserving `return_features` path so the supervised loss and CORAL share ONE
  encoder forward (else the encoder runs twice/step). No `forward_features` exists today.
- **Trainer loop:** second cycling target iterator beside `force_trainer.py:724`; add the UDA
  term to `loss` **inside autocast, before `/grad_accum` and `backward`** (AMP 767→768,
  non-AMP 784→785). Branch on `self.is_sequence_model` (`:322`) to skip encoder-UDA for c5–c8.
- **DANN target features must carry grad** (no `torch.no_grad()` — that breaks the reversal).
- **Loader:** gated `get_target_domain_loader` against `datasets/mixed` (the `real_/synt_`
  prefixes exist only there; `datasets/real` has bare `seqNN` ids).
- **Splits must be re-authored on this host** regardless — every split JSON bakes an absolute
  `data_dir` validated char-for-char (`splitter.py:337–345`); current splits bake `/workspace/...`.

## 3. THE PROTOCOL DECISION — DECIDED 2026-07-03: **Option B (inductive)**
The owner chose the inductive, defensible-transfer protocol. Realisation (chosen because it
costs zero coverage): **per-fold**, the adaptation target = the fold's real sequences that are
NOT in that fold's `test_sequences` (their images, unlabeled); score on the held-out real
`test_sequences`. Every real sequence is the scored test set in exactly one fold and an
unlabeled adaptation target in the other four → no leakage, no lost coverage.

Implementation: re-author `author_cv_splits.py` to emit, per fold, an `adapt_sequences` list =
`{all real seqs} \ {this fold's real test seqs}`; a unit test asserts `adapt_sequences ∩
test_sequences == ∅`. The target loader reads `adapt_sequences` (unlabeled images) from
`datasets/mixed` (bare-`seqNN` ids in `datasets/real` lack the `real_/synt_` prefix).

*(Rejected: Option A transductive — adapt on the scored test frames; cheaper but only a
transductive number. Not used. And never default the target loader to `test_indices` filtered
by `real_` — that silently produces a transductive number presented as inductive.)*

## 4. Phased test plan
- **Phase 0 (GPU-free unit tests) — DONE for the primitives** (`tests/test_uda_primitives.py`,
  11/11 pass): CORAL scalar/zero/normalisation-`/(4d²)`-regression-guard/covariance/dim-mismatch/
  grad-flow; GRL identity-forward + `−λ`-backward + 2-tuple-with-None; DomainClassifier shape.
- **Phase 1 (single-fold smoke — NOT run; experiments deferred):** c1 with `coral_weight>0`,
  few steps; assert loss decreases, no OOM (second loader ~doubles image throughput), and that
  a UDA-off run is bit-identical in loss to the pre-change baseline.
- **Phase 2 (CV):** after the smoke test and the §3 decision; log weights + adapt-pool provenance
  to W&B.

## 4b. Run 1 — first-pass CORAL vs baseline (LAUNCHED 2026-07-03, in progress)
- **Code (all on `kidknet-experiments`, uncommitted):** `dknet/utils/uda.py` (primitives);
  `models/force_net.py` `forward(return_features=)`; `data/loader.py` `get_target_domain_loader`;
  `trainers/force_trainer.py` `_forward_loss` + CORAL in `train_epoch` (default OFF, byte-identical);
  `scripts/train.py` attaches the target loader; `scripts/run_cv.py` `--coral-weight` flag.
- **Env fixes:** installed matplotlib/wandb/grad-cam into `rag_parsers_venv`; ConvNeXt-L ImageNet
  weights auto-downloaded; **wandb offline** (no host key in this non-interactive session — `wandb sync` later).
- **Infra workaround:** `DataFlow/KiDKNet` is `root:root` (no sudo) → all run artifacts + re-authored
  splits under **`DataFlow/kidknet_host/`** (chown `DataFlow/KiDKNet` to restore the canonical layout).
- **Design (validated on GPU):** c2 (synth train / real test) + CORAL aligning the 1536-d ConvNeXt
  feature to the **unlabeled real twins of the fold's non-test sequences** (Option B; fold0: 40699
  frames / 24 seqs, disjoint from the 7 test seqs). Smoke confirmed "UDA CORAL active", no OOM.
- **This pass:** folds {0,1,2}, epochs **25** (first-pass, not the 50-epoch protocol), batch 64,
  `coral_weight=1.0` (UNTUNED), baseline vs CORAL at matched settings, 3 GPUs, `file_descriptor`
  sharing (RAM-bound, ~123 GB). Outputs: `DataFlow/kidknet_host/outputs/cv5_{baseline,coral}/c2/`.
- **Metric:** real-test magMAE per fold → gap-closed % = (baseline − coral)/(baseline − 0.232 oracle).
- **Aggregate when done:** `run_cv --skip-existing --folds 0,1,2` per cv-out → `cross_fold_summary.json`
  `real_only_slice`. **Caveats to resolve before any claim:** 25-epoch first pass; coral_weight untuned
  (sweep next); 3 folds (extend to 5); wandb offline (sync).

## 4c. Run 1 RESULTS (2026-07-04) — first pass, n=2 (SUPERSEDED by §4d full 5-fold)
Real-test magMAE (raw N), c2 baseline vs c2+CORAL(w=1.0), 25 epochs, wandb online
(`kidknet-trackb-uda`). **fold2 was OOM-killed** (`train rc=-9`; 3× ~41 GB unpinned caches
spiked RAM) → n=2 folds. Kept for history; the conclusion is the full 5-fold in §4d.

| fold | baseline magMAE (ang) | CORAL magMAE (ang) | Δ magMAE | gap-closed% |
|---|---|---|---|---|
| 0 | 1.481 (54.3°) | 1.174 (64.7°) | **+0.306** | +24.5% |
| 1 | 1.273 (45.8°) | 1.399 (49.8°) | **−0.126** | −12.1% |
| **mean (n=2)** | **1.377±0.104** | **1.287±0.112** | +0.090 | **+7.9%** |
| angle | 50.1° | 57.3° | — | **−7.2° (worse)** |

**Honest verdict — inconclusive / within noise.** The two folds disagree in sign; the mean
magnitude improvement (+0.09) is smaller than the fold-to-fold spread (±0.10); and CORAL makes
the *angle* worse (+7.2°). This is consistent with "CORAL@w=1.0 has no reliable effect at this
measurement fidelity" — the H0 measurement-noise problem (3-seq val, folds disagree) still bites.
Baseline reproduces the known synth→real gap (mean 1.377 vs historical c2 1.357 / 55.4°), so the
pipeline is sound; the *effect* is just not established. Caveats compound: n=2 (fold2 OOM),
25 epochs (not 50), `coral_weight=1.0` untuned.

## 4d. Run 2 RESULTS (2026-07-10) — FULL 5-FOLD, NULL RESULT (CORAL as a training loss)
Real-test magMAE (raw N), c2 baseline vs c2+CORAL(w=1.0), 25 epochs, wandb online. OOM fixed
via `use_mmap` (page-cache sharing, ~2 GB RSS/proc). All 5 folds completed.

| fold | baseline magMAE (ang) | CORAL magMAE (ang) | Δ magMAE | gap-closed% |
|---|---|---|---|---|
| 0 | 1.481 (54.3°) | 1.174 (64.7°) | **+0.306** | +24.5% |
| 1 | 1.273 (45.8°) | 1.399 (49.8°) | **−0.126** | −12.1% |
| 2 | 1.055 (54.6°) | 1.744 (54.6°) | **−0.689** | −83.7% |
| 3 | 0.614 (48.0°) | 1.663 (49.3°) | **−1.048** | −274% |
| 4 | 1.710 (48.7°) | 1.109 (64.1°) | **+0.601** | +40.7% |
| **mean (n=5)** | **1.227±0.375** | **1.418±0.253** | **−0.191±0.610** | **−19.2%** |
| angle | 50.3° | 56.5° | — | **−6.2° (worse)** |

**Honest verdict — NULL / slightly negative, not significant.** CORAL@w=1.0 does NOT close the
gap: mean magMAE gets *worse* (1.227→1.418), only **2/5 folds** improve, angle worsens 6.2°, and
the paired t-test is **t=−0.70 (n=5), not significant**. The huge baseline fold spread (±0.375,
range 0.614–1.710) confirms **H0 measurement noise dominates** any CORAL effect at this fidelity —
consistent with the §4c n=2 pass and the earlier loss/augmentation A/B "within-noise" results.
*Caveat:* coral folds 2,3,4 evaluated from the epoch-≈24 `best_model` (last epoch dropped when
mmap I/O thrashing under 3 concurrent jobs slowed training); baseline + coral 0,1 ran the full 25.
The comparison uses the best-val checkpoint on both sides, and val had plateaued, so this does not
change the verdict. W&B: `zwhdiscovery-kyoto-university/kidknet-trackb-uda`.

**Conclusion for the training-loss role: do NOT keep tuning `coral_weight`.** The measurement
cannot resolve an effect this small. The higher-leverage move is data-side appearance work (see
`../2026-07-03_windows-render-diversity/`), then re-measure the gap with the tool in §4e.

## 4e. FOSSILISED TOOL — CORAL as a synth→real gap METRIC (KEEP, 2026-07-10)
The training-loss experiment is null, but the quantity CORAL minimises — the Frobenius distance
between source/target feature covariances — is a good *measurement* of how far two feature
distributions sit apart. We retain that as a diagnostic to score data-side work.

- **Code (KEEP, additive):** `dknet/utils/uda.py::coral_distance` (detached float) +
  `domain_gap_report` (CORAL distance + within-domain sampling-noise floor + `gap_ratio` +
  first-order `mean_l2` + diversity `rms_ratio`); driver `scripts/eval_domain_gap.py` (frozen
  ConvNeXt-L + ImageNet norm; single merged-dir-by-prefix or two-dir modes). Unit tests 16/16
  (`tests/test_uda_primitives.py`, incl. `test_coral_is_blind_to_pure_mean_shift`).
- **Literature backing:** `CORAL_LITERATURE.md` (21 URL-verified papers). CORAL distance = the
  covariance-only sibling of FID (so we also report `mean_l2`); the closest published precedents
  for "second-order feature distance as a shift diagnostic" are Fréchet Domain Distance (digital
  pathology, arXiv:2405.09934) and a CARLA→real-LiDAR CORAL diagnostic (arXiv:2202.02666); no
  prior CORAL-on-surgical-images was found (existence-checked).
- **BASELINE MEASUREMENT (2026-07-10)** on the paired `datasets/mixed` (52 522 real ↔ 52 522
  twin frames, same sequences → isolates appearance), full result in `gap_baseline_mixed.json`:

  | quantity | value | reading |
  |---|---|---|
  | CORAL distance (synth→real) | **4.19e-5** | headline gap on frozen ConvNeXt-L features |
  | within-domain floor (mean) | 1.55e-8 | sampling noise (random-half split) |
  | **gap_ratio** | **2706** | synth↔real are ~2700× further apart than sampling noise → large, real gap |
  | mean_l2 (first-order) | 16.48 | large mean shift too (CORAL-blind; hence reported) |
  | rms_ratio (synth/real diversity) | **0.157** | synth features ~6.4× LESS diverse — independently reproduces the earlier "~6× less diverse" appearance-gap diagnosis |

  This is the number data-side appearance work must move: success = `coral_distance`↓,
  `gap_ratio`↓, `rms_ratio`→1. Re-run: `python scripts/eval_domain_gap.py --data-dir
  <mixed> --synth-prefix deformed_ --real-prefix real_ --backbone large`.

## 5. Increment status & disposition
Two roles, split disposition after the §4d null result:

- **CORAL as a gap METRIC — KEEP (adopted).** `dknet/utils/uda.py::coral_distance` /
  `domain_gap_report` + `scripts/eval_domain_gap.py` + tests (16/16). Additive, no default
  behaviour change. This is the retained tool (§4e); baseline measured; `CORAL_LITERATURE.md`
  backs it. → promote to trunk on the owner's commit.
- **CORAL as a training LOSS — PARK (decided 2026-07-10, expiry 2026-10-31).** The wiring
  (`force_trainer.py` `_forward_loss` + `train_epoch` CORAL term; `train.py` target-loader attach;
  `run_cv.py --coral-weight`; `loader.py::get_target_domain_loader`) stays **gated OFF and
  byte-identical when off**. §4d shows it does not help at current fidelity, so it is parked, not
  adopted. **Confirm-or-revert by 2026-10-31:** retry only if a measurement overhaul + data-side
  appearance work make an effect this small resolvable; otherwise LOSE (revert the trainer/loader/
  CLI wiring; the `coral_loss` primitive stays for the metric). *No indefinite dormant code.*
- **DANN (GRL + `DomainClassifier`):** never wired; primitives + tests only. Same measurement
  ceiling applies → deprioritised behind the data-side work.
- **Increment-1 primitives** (`coral_loss`, GRL, `DomainClassifier`) remain the shared, tested
  base under both roles.
- **Draft errors corrected by verification (kept for the record):** `.backbone` is `None` for
  c5–c8; CORAL on cached features is a no-op; Tent-BN inapplicable (LayerNorm); CORAL
  `/(4d)`→`/(4d²)`; loss subclass breaks byte-identity; target-under-`no_grad` breaks DANN;
  `test_indices` target = leakage; `deformed_`/`real_` are the per-sample id prefixes in
  `datasets/mixed` (the `synt_` in `sequence_index.json` is a sequence-key alias);
  `forward_features` doesn't exist; loss is 2-arg.
