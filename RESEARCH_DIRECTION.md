# Research direction — sim2real FEM-augmented force prediction (2026-06-16)

> **⚠ 生效覆盖(2026-07-03 re-scope):** 项目已重定标为 **zero-real-label sim→real domain
> adaptation**(只用合成 FEM 数据训练、训练集零真实力标签,再迁移到真实)。**`RESEARCH_GOAL.md`
> §11 的 2026-07-03 条目覆盖本文档中所有"合成增强"(augmentation)框架与渲染环境(Linux
> headless-GL block)的措辞**——凡本文与该条目冲突处以该条目为准:c2=baseline/c1=ceiling、
> 主指标 gap-closed %、推理 I/O 固定为图像进→3D 力向量出、所有渲染在 Windows 机上执行(可检视)、
> 外观只是可组合因子之一(另有视角/接触点多样性 + 力真实性)。本文以下诊断的**事实**仍有效,
> 但**框架措辞**以 `RESEARCH_GOAL.md` §11 为准。

Working note (uncommitted). Synthesis of the 8-condition x 5-fold CV results + a
grounded read of the synthetic data-generation pipeline. Question answered:
**improve the model, improve the data, or both — and in what order?**

## Bottom line

It is a **DATA / domain-coverage** problem, specifically an **appearance (pixel)**
gap — **not** a model/architecture problem. But the measurement protocol is
currently too noisy to read any small effect, so **fix the instrument first**.
Architecture work is premature and low-value right now.

Your instinct ("more + more diverse data") is **half right**: more *visually
diverse* synthetic data is the lever — but reframe "probe the model's **capacity**
ceiling" as "raise the **domain-coverage** ceiling". The model already has excess
capacity (it overfits the real data); capacity is not the binding constraint.

## Results (real-comparable magnitude MAE, raw units, mean +/- std over 5 folds)

| cond | setup | magMAE | angle err |
|---|---|---|---|
| c1 | real, scratch (single) | 0.232 +/- 0.073 | 23.9 deg |
| c2 | synt->real, zero-shot (single) | **1.357 +/- 0.456** | 55.4 deg |
| c3 | mixed, real_only (single) | 0.204 +/- 0.054 | 24.9 deg |
| c4 | transfer LP-FT (single) | 0.209 +/- 0.035 | 26.1 deg |
| c5 | real, scratch (sequence) | 0.234 +/- 0.023 | 28.3 deg |
| c6 | synt->real, zero-shot (sequence) | **1.542 +/- 0.097** | 59.7 deg |
| c7 | mixed, real_only (sequence) | 0.222 +/- 0.040 | 28.1 deg |
| c8 | transfer (sequence) | 0.240 +/- 0.037 | 29.0 deg |

(charts: `DataFlow/KiDKNet/outputs/cv5/report/`)

## What the results say vs the hypothesis

1. **Large, robust synth->real domain gap (the only signal outside the noise).**
   Zero-shot synt models are ~6x worse on real magnitude (c2 vs c1: t~5.5; c6 vs
   c5: t~29) with ~55-60 deg angle error (direction nearly useless). This
   **falsifies assumption (1) "FEM-synth ~= real".**
2. **Transfer does not (measurably) beat scratch.** c4 vs c1 = -0.023, c8 vs c5 =
   +0.006 — both *inside* the fold std. The goal's claim ("synth pretrain ->
   better real prediction") is **unproven and currently unmeasurable**, not
   disproven.
3. **Model is capacity-RICH, not capacity-limited.** 197M ConvNeXt-L overfits ~22
   real training sequences. Two very different architectures (end-to-end
   ConvNeXt-L vs frozen-feature TCN) give the **same** real score (0.234 vs 0.232)
   **and the same sim-to-real cliff** (1.542 vs 1.357) -> the bottleneck is not in
   the architecture family.
4. **Measurement is too noisy to trust small effects.** Validation = 3 sequences
   per fold -> best-epoch selection swings (folds saved epochs 1/6/10/25); c1 fold
   std +/-0.073 (~31% of mean) exceeds every inter-condition difference. So all the
   c1/c3/c4 near-ties are statistically indistinguishable.

## Why the gap is APPEARANCE, not physics (data-pipeline grounding)

The synthetic set is a **1:1 digital-twin replay** of the 31 real sequences, not a
large randomized synthesizer:

- **Forces = the real sensor forces**, rotated into the mesh frame
  (`Deform_post/dpost/forces/real.py`, magnitude-preserving). So the **force
  distribution matches real by construction** — force mismatch is NOT the cause.
- **Geometry-only render.** `DeformSim/.../object.cpp WritePLY` emits vertices +
  faces with **no color/texture/normals**; `Deform_post/dpost/render.py` renders
  with a **white background, default light, no material/texture**, a single fixed
  laparoscope camera. Result: a flat-shaded **grey untextured kidney silhouette on
  white**.
- **Real frames** are textured, bloody, specular, vignetted endoscope video. The
  only shared appearance feature is the circular FOV mask.
- **Near-zero diversity / augmentation:** one mesh, one material (E=30kPa), one
  annotation, deterministic camera; training has **no image augmentation** beyond
  ImageNet normalization (`KiDKNet/dknet/data/transforms.py`). The only existing
  diversity is force-trajectory jitter (already not the bottleneck).

So assumption (1) fails on **pixels**, which is **fixable in the pipeline** — not a
fundamental physics gap.

## Prioritized plan (sequenced, NOT "all at once")

**(0) PREREQUISITE — fix the measurement instrument (cheap, ~days).** Without this,
no model/data comparison is trustworthy (noise > every effect except the gap):
- enlarge / stabilize validation (3-seq val is the #1 noise source) or use
  test-only CV without best-epoch cherry-picking; EMA / fixed-epoch selection.
- add **real-image augmentation** (currently none) to curb the immediate overfit.
- normalize/align the raw force targets; re-baseline c1-c8.

**(1) CORE LEVER — close the appearance domain gap on the DATA side.** Ranked,
all doable in this pipeline:
1. **Render-time domain randomization (cheapest, highest leverage):** organ
   albedo texture/material on the PLY, randomized lighting, real-tissue
   backgrounds instead of white, specular + vignette — localized change in
   `render.py`.
2. **Photometric training augmentation** (color jitter / blur / noise / gamma) in
   `transforms.py`.
3. **Real-image-guided appearance / texture transfer** (medium cost, high value):
   the paired real<->twin frames share contact + force + ~camera, so paste/style-
   transfer real texture onto the rendered silhouette while keeping the FEM label.
4. **Truly diverse synthetic** = new VISUAL/scene domains (lighting, texture,
   camera, deformation regimes, multiple meshes) — NOT more force-jitter of the
   same 31 twins. This is where "more + more diverse data" is legitimate.

**(2) Two cheap decisive experiments BEFORE investing (hours, reuse caches):**
- **k-shot learning curve:** synt-pretrain + finetune on k in {1,2,4,8,16} real
  sequences vs ImageNet-scratch. This is the *actual* test of "synthetic as a
  prior for scarce real" — the current full-data grid never tested the
  data-scarcity regime the goal is about. (script: `scripts/kshot_transfer.py`)
- **Domain-gap quantifier:** ConvNeXt feature distance + a linear real-vs-synt
  domain classifier on the existing feature caches; ~100% separability = large
  visual gap. (script: `scripts/analyze_domain_gap.py`)

**(3) DEFER architecture.** Two dissimilar architectures already give the same
real score and the same sim-to-real cliff -> not the binding constraint. Revisit
only after (0) is clean and the gap is characterized.

The running 4-variant transfer-recipe race (c4ft/c4dl/c4sg/c4fz) is fine to
finish, but it optimizes the *finetune recipe at full real data* — it can
approach but not beat the domain-coverage ceiling.

## Appearance-gap closing strategy (added 2026-06-16, agreed)

Key reframe: we do NOT need a kidney-texture dataset -- the appearance source is
our own 31 real laparoscopic sequences. Methods that learn appearance from those
images close the gap without any external texture asset. Three tiers, by leverage/cost:

- **T1. Render-domain randomization** (procedural, ZERO external data, do FIRST):
  in `Deform_post/dpost/render.py` break the grey-silhouette-on-white shortcut --
  procedural organ material (subsurface scatter, specular, vascular/noise texture
  or vertex colour), randomized lighting (dir/intensity/colour), randomized
  background (sampled tissue / noise instead of white), vignette. Domain
  randomization works by VARIETY, not photorealism.
- **T2. Unpaired sim->real translation trained on OUR real frames** (the real
  appearance-closer): CUT (preferred) / CycleGAN / diffusion render->real on
  {rendered silhouettes} <-> {real frames}; or paired pix2pix using the
  roughly-aligned real<->twin pairs (verify alignment first). Classical neural
  style/texture transfer is the cheap no-train fallback.
- **T3. External organ-appearance datasets** (only if T1+T2 plateau; for extra
  texture/background/lighting diversity, NOT force labels; verify licenses):
  DSAD (Dresden Surgical Anatomy Dataset -- laparoscopic abdominal organs incl.
  some kidney/adrenal views, closest public kidney appearance), SCARED/EndoVis
  (porcine abdomen, kidney-region tissue + depth), Cholec80/CholecT45/CholecSeg8k
  (laparoscopic organ surface/blood/specular), HyperKvasir/Kvasir-SEG (GI mucosa),
  LapGyn4/GLENDA (lap gynecology). Pure partial-nephrectomy public video is scarce;
  use the above as a texture/background/lighting pool for T1.

Ordering & dependency: T1 first (cheap, no data). Run it only AFTER the
measurement-protocol fixes (val size, augmentation, force normalization) so the
effect is measurable, and confirm with the k-shot curve that closing appearance
recovers real performance before investing in T2 GAN training. Architecture stays
last. Gap motivating this (scripts/analyze_domain_gap.py, 2026-06-16): linear-probe
real-vs-synth separability 100%, separation ratio 3.7, synth ~6x less feature-diverse.

## One-line reframe

The direction is not dead — the diagnosis was off-target. Assumption (1) fails on
**pixels** (fixable); assumption (2) "enough diverse synthetic data" was **never
actually tested** (only 31 twins exist). Fix the measurement, close the appearance
gap with render-domain-randomization / real-texture transfer, generate *visually*
diverse synthetic, and validate with a k-shot curve. Architecture last.

## Appearance-closing roadmap (agreed 2026-06-16)

Reframe that resolves "we have no kidney texture data": the appearance source IS
the 31 real laparoscopic sequences we already have. The right methods LEARN real
appearance from those frames -- no external kidney-texture library required.
Confirmed mechanism: `scripts/analyze_domain_gap.py` shows a linear probe
separates real vs synth ConvNeXt features at 100% (chance 50%), separation ratio
3.7, synth ~6x less diverse (fig: `DataFlow/Deform_post/feature_cache/domain_gap.png`).

Three method tiers (by leverage / cost):
- **Tier 1 -- our own real data (no external resource):** unpaired sim->real
  translation (CUT / CycleGAN / diffusion) trained on {rendered silhouettes} <->
  {real frames}; or paired pix2pix using the roughly-aligned real<->twin pairs
  (same contact/force/~camera); or classical neural style/texture transfer. This
  is the real appearance-closer.
- **Tier 2 -- render-domain randomization (procedural, ZERO data) -- DO FIRST:**
  in `Deform_post/dpost/render.py`, break the grey-on-white shortcut: procedural
  organ material / vertex color on the PLY, randomized lighting (dir/intensity/
  color), randomized backgrounds (noise or sampled tissue), specular + vignette.
  Domain randomization works by VARIETY, not photorealism.
- **Tier 3 -- external organ-appearance datasets (texture/background/lighting
  pool only; licenses apply):** DSAD (Dresden Surgical Anatomy -- closest public
  KIDNEY views), SCARED/EndoVis (porcine abdomen, kidney-region), Cholec80 /
  CholecT45 / CholecSeg8k, HyperKvasir / Kvasir-SEG, LapGyn4 / GLENDA. Use as a
  secondary diversity booster only if Tier 1+2 plateau.

Sequenced execution:
0. PREREQUISITE -- measurement fixes (val size, augmentation, force normalization).
1. CHARACTERIZE -- `analyze_domain_gap.py` (DONE: 100% separable) + `kshot_transfer.py`
   (READY; needs GPU after the race) to confirm the scarce-real upside before heavy work.
2. CORE -- Tier 2 render-domain randomization (minimal `render.py` change) FIRST,
   then re-render the twin set, re-extract features, re-run `analyze_domain_gap.py`
   to verify the gap (separability / separation ratio) shrinks.
3. Tier 1 unpaired translation on our own real frames (CUT first).
4. Tier 3 external data only if needed.
Architecture stays LAST. The running transfer-recipe race tunes the finetune
recipe, not the data gap.

Immediate next code action (on user go): a minimal `render.py` domain-randomization
pass (random lighting + background + procedural material/vertex-color + vignette),
gated behind a config flag, then a gap-shrink check via the existing scripts.

## Route status ledger (2026-08-14 append)

Frozen protocol: c2 baseline 1.3572 / c1 ceiling 0.2316, gap-closed %, 5-fold
paired CV, synthetic-only model selection, real test with sensor Newtons.

| Route | Verdict | Evidence |
|---|---|---|
| DR-C1 appearance randomization | **有效 +39.6%** (master canonical recipe) | DR-C2 manifest + fold3 seedcheck |
| C1+C3 combined (+contact diversity) | **有效 +60.6%**, 5/5 (branch `c1c3-combined`) | C1C3 manifest; C3 marginal alone: 不可判定 |
| FDA spectral alignment (direction 1) | **淘汰 (2026-08-14)**: isolation −39.1% (0/5, harmful); stacking 57.9% < 60.6% (undecidable, negative point estimate) | `Deform_post/research/data_improve/2026-08-13-fda-*.md`; evidence tar `D:/MedSim2Learn-archive/fda-20260814-evidence.tar.gz`; code archived on local branch `codex/dataimprove-fda` |

FDA lesson: the gap does not live in low-frequency amplitude statistics; DC/
brightness transplantation destroys real brightness-force cues and per-frame
reference draws add appearance flicker. Learned, texture-capable translation
(this document's Tier-1 CUT anticipation) is the next probe — direction 2 of
the three-direction ruling, design manifest `2026-08-14-cut-design-manifest.md`.

## Route status ledger (2026-08-16 append)

| Route | Verdict | Evidence |
|---|---|---|
| CUT unpaired translation (direction 2, image-space) | **淘汰 (2026-08-15)**: structure hallucination + scene-grammar memorization (seq15 cross-sequence probe); owner ruled all image-space frame-authoring routes out -- learned components may author TEXTURES only | `2026-08-14-cut-design-manifest.md` section 5; evidence tar `D:/MedSim2Learn-archive/cut-20260815-evidence.tar.gz` |
| T-B-G textured mesh route (base-colour canvas + generated vessels, UV onto mesh, classical render) | **有效 +56.7%**, 5/5 folds (p=1/32) -- strongest single isolation effect; victory gate passed, merged to master (`15b7a60`) | `2026-08-15-tb-pilot-receipt-and-design.md` sections 4b-4e; pool/renders archived under `D:/MedSim2Learn-archive/tbg-*`; server `datasets/mixed_tex_v1` |
| DINOv2 sentinel fold (pre-registered representation probe) | Frozen vitb14 + 3-layer head, fold0 magnitude MAE 0.8846 vs full ConvNeXt 0.8653 on the same data/fold (gap 0.019) -- representation axis carries most of the task signal | server `outputs/sentinel_dinov2_tex_fold0/sentinel_report.json` (features + predictions cached) |

Texture lesson: the sim-real gap on this line is dominated by surface
appearance statistics that a REAL-base-colour canvas plus prompt-guided matte
vessel painting can supply; glare-contaminated fine-tunes (LoRA on wet-specular
crops) paint lighting into material and are unusable for albedo-style texture
authoring. Stacking round A (texture x C1 render-time lighting jitter) unlocked
by the >=10% economy rule and owner-ordered 2026-08-16.
