# CORAL literature — backing for CORAL distance as a synth→real gap metric

- **Compiled:** 2026-07-10
- **Purpose:** back the decision to *fossilise CORAL as an evaluation metric* (not a training
  loss) for quantifying the gap between our FEM-rendered synthetic images and real surgical
  images, on frozen ConvNeXt features. Tool: `KiDKNet/scripts/eval_domain_gap.py` +
  `dknet/utils/uda.py::coral_distance`/`domain_gap_report`.
- **Provenance:** 4-angle web sweep (foundational / gap-metric / sim2real / variants), 21
  distinct papers, **every title, author list, venue and URL verified first-hand via
  WebSearch + WebFetch** against the primary source (arXiv / AAAI OJS / ACL / Springer /
  IEEE). Where a paper could not be verified to a clean primary URL it was omitted (see
  §6). This is an *existence-checked* survey — no citation here is from memory.

> **Why we keep CORAL at all.** The Track B experiment (`README.md` §4c) showed CORAL as a
> *training loss* does not reliably close the gap at our current measurement fidelity (null
> result: mean magMAE 1.42 vs baseline 1.23, paired t=−0.70, 2/5 folds better). But the
> quantity CORAL minimises — the Frobenius distance between source/target feature
> covariances — is a perfectly good *measurement* of how far two feature distributions sit
> apart. That measurement is what we retain, to score data-side appearance work.

---

## 1. The exact quantity we compute (definition)

CORAL = **COR**relation **AL**ignment: align the **second-order statistics (feature
covariances)** of two domains. Deep CORAL gives the exact normalised form we reuse:

> **L_CORAL = (1 / (4 d²)) · ‖C_S − C_T‖²_F**,  d = feature dim, ‖·‖²_F = squared Frobenius
> norm, C = centred sample covariance  C = (1/(n−1))·(DᵀD − (1/n)(1ᵀD)ᵀ(1ᵀD)).

Our `coral_loss`/`coral_distance` implement exactly this (the `/(4·d·d)` normalisation is
unit-tested, `tests/test_uda_primitives.py`). The original (shallow) CORAL realises the same
objective in closed form by whitening the source with C_S^{−1/2} then re-colouring with
C_T^{1/2}. As a **metric** the 1/(4d²) constant is a fixed rescaling — it does not change
relative synth-vs-real comparisons, so numbers are comparable across runs as long as the
feature extractor is fixed.

| # | Paper | Authors | Venue / Year | URL |
|---|---|---|---|---|
| 1 | Return of Frustratingly Easy Domain Adaptation (original CORAL) | Sun, Feng, Saenko | AAAI 2016 | https://ojs.aaai.org/index.php/AAAI/article/view/10306 (arXiv:1511.05547) |
| 2 | **Deep CORAL: Correlation Alignment for Deep Domain Adaptation** | Sun, Saenko | ECCV 2016 Workshops (TASK-CV), LNCS 9915 | https://arxiv.org/abs/1607.01719 |
| 3 | Correlation Alignment for Unsupervised Domain Adaptation (unified book chapter) | Sun, Feng, Saenko | Springer 2017 (Csurka, ed.) | https://arxiv.org/abs/1612.01939 |

**Predecessors CORAL is built against** (second-order / subspace alignment):

| # | Paper | Authors | Venue / Year | URL |
|---|---|---|---|---|
| 4 | Unsupervised Visual Domain Adaptation Using Subspace Alignment | Fernando, Habrard, Sebban, Tuytelaars | ICCV 2013 | https://doi.org/10.1109/ICCV.2013.368 |
| 5 | Geodesic Flow Kernel for Unsupervised Domain Adaptation (GFK; + a rank-of-domain adaptability metric) | Gong, Shi, Sha, Grauman | CVPR 2012 | https://doi.org/10.1109/CVPR.2012.6247911 |

CORAL positions itself as the extension from **subspace-only** alignment (SA aligns the
covariance eigen-basis; GFK interpolates subspaces on a Grassmann manifold) to **full
covariance** alignment. GFK also prefigures the very idea of a *quantitative domain-gap
number*.

---

## 2. CORAL / second-order distance as a MEASUREMENT (the core justification)

This is the angle that matters for us: treating a covariance/second-order discrepancy as a
**diagnostic measurement** of domain shift, and correlating it with transfer performance —
not as a training objective.

| # | Paper | Authors | Venue / Year | URL | Role |
|---|---|---|---|---|---|
| 6 | Central Moment Discrepancy (CMD) | Zellinger et al. | ICLR 2017 | https://arxiv.org/abs/1702.08811 | proven **metric** (loss too) |
| 7 | FID (Fréchet Inception Distance), via the TTUR/GAN paper | Heusel, Ramsauer, Unterthiner, Nessler, Hochreiter | NeurIPS 2017 | https://arxiv.org/abs/1706.08500 | pure **eval metric** |
| 8 | A theory of learning from different domains (H-divergence, **Proxy A-distance**) | Ben-David, Blitzer, Crammer, Kulesza, Pereira, Vaughan | Machine Learning 2010 | https://link.springer.com/article/10.1007/s10994-009-5152-4 | classifier-based **gap metric** |
| 9 | Domain Divergences: A Survey and Empirical Analysis | Kashyap, Hazarika, Kan, Zimmermann | NAACL 2021 | https://aclanthology.org/2021.naacl-main.147/ | which divergences predict transfer |
| 10 | Detecting Domain Shift ... using **Fréchet Domain Distance** (digital pathology) | Pocevičiūtė, Eilertsen, Garvin, Lundström | 2024 (MICCAI-affil. workshop / arXiv) | https://arxiv.org/abs/2405.09934 | **closest precedent** |
| 11 | Fréchet Radiomic Distance (FRD): comparing medical imaging datasets | Konz, Osuala, Verma, et al. | Medical Image Analysis 2026 | https://arxiv.org/abs/2412.01496 | medical dataset-gap metric |

**How CORAL distance relates to these (carry into any writeup):**

- **CORAL ⊂ FID.** FID = Fréchet/Wasserstein-2 distance between Gaussians fitted to deep
  features = a **mean term** + a **covariance term** (with a covariance-sqrt cross term).
  CORAL distance is essentially the **covariance-only sibling of FID** — it drops the mean
  term. Consequence for us: report a **first-order mean distance alongside CORAL** so we can
  separate a mean-shift from a covariance-shift. (Our `domain_gap_report` returns `mean_l2`
  precisely for this.)
- **CMD / HoMM ⊃ CORAL.** CMD and higher-order moment matching generalise past 2nd order to
  arbitrary central moments. Two feature sets with *identical covariance but different
  skew/kurtosis* score CORAL-gap = 0 — a known blind spot (§4).
- **Proxy A-distance** (train a classifier to tell source from target; distance =
  2(1−2ε)) is the classic *classifier-based* gap metric and the theoretical justification
  for treating "how separable are the domains" as an upper bound on transfer error. Our
  earlier diagnosis ("synth vs real 100% linearly separable, separation ratio 3.7") is
  exactly a proxy-A-distance-style observation; the CORAL distance is its second-order,
  learning-free analogue.
- **Fréchet Domain Distance (Pocevičiūtė 2024)** is the **closest published analogue to our
  plan**: an unsupervised second-order Fréchet distance over frozen features, used *only as
  a diagnostic*, shown to correlate (~0.70) with model performance degradation — in medical
  imaging (histopathology). This is the strongest existence-backing that "second-order
  feature distance as a shift measurement" is an accepted, working idea.

---

## 3. Sim→real and medical applications of CORAL / second-order alignment

| # | Paper | Authors | Venue / Year | URL |
|---|---|---|---|---|
| 12 | Synthetic→Real Adaptation with **Generative Correlation Alignment Networks** (DGCAN; CAD/render→real) | Peng, Saenko | WACV 2018 (arXiv 2017) | https://arxiv.org/abs/1701.05524 |
| 13 | Sim-to-Reality DA for 3D annotation on pointclouds **with CORAL** (CARLA→real LiDAR; tracks covariance distance as a diagnostic) | Zhang, Kiran, Gauthier, Mazouz, Steger | IMPROVE 2022 | https://arxiv.org/abs/2202.02666 |
| 14 | CORAL-Correlation Consistency Network — Left Atrium **MRI** segmentation | Li, Huang, Wu, Yang, Fan, Zhu, Su | IEEE BIBM 2024 | https://arxiv.org/abs/2410.15916 |
| 15 | Domain Adaptation Techniques for Natural and **Medical** Image Classification (benchmarks Deep CORAL on 8 medical datasets) | Chaddad, Wu, Kateb, Desrosiers | arXiv 2025 | https://arxiv.org/abs/2508.20537 |
| 16 | Deep Visual Domain Adaptation: A Survey (places CORAL in the discrepancy/moment-matching taxonomy) | Wang, Deng | Neurocomputing 2018 | https://arxiv.org/abs/1802.03601 |

- #13 is directly on-point: a **sim→real** pipeline that both uses CORAL and treats the
  **source–target covariance distance as an observable diagnostic** — the same evaluative
  role we assign it.
- #12 frames the **rendered/CAD → real** gap explicitly as second-order feature-statistic
  mismatch — the closest structural parallel to FEM-render → real.

**Honest absence (existence-only, reported as absence):** the sweep found **no paper
applying CORAL to surgical / endoscopic images.** Surgical sim-to-real DA that *was* found
(e.g. Endo-Sim2Real teacher–student instrument segmentation, arXiv:2103.01593; GAN-based
endoscopy depth adaptation) uses consistency or adversarial alignment, **not** CORAL /
second-order covariance matching. Nearest medical CORAL uses are MRI segmentation (#14) and
radiology/derm classification (#15). **So CORAL-distance-on-frozen-ConvNeXt as a gap metric
for surgical images is novel-in-domain** — #10/#13 back the *construct*, but not the exact
protocol.

---

## 4. Variants, critiques, and limitations we must respect when reading the number

| # | Paper | Authors | Venue / Year | URL | What it warns / offers |
|---|---|---|---|---|---|
| 17 | Correlation Alignment by **Riemannian** Metric | Morerio, Murino | arXiv 2017 | https://arxiv.org/abs/1705.08180 | covariances live on the SPD manifold; Euclidean Frobenius is not affine-invariant |
| 18 | Deep DA by Geodesic Distance Minimization (**Log-CORAL**) | Wang, Li, Dai, Van Gool | ICCV 2017 Workshops | https://arxiv.org/abs/1707.09842 | cheap manifold-aware alt: Frobenius **after matrix log** |
| 19 | **HoMM**: Higher-order Moment Matching | Chen et al. | AAAI 2020 | https://arxiv.org/abs/1912.11976 | proves **2nd-order HoMM == CORAL**; order≥3 catches non-Gaussian structure |
| 20 | **CORAL++** (speaker recognition) | Li, Zhang, Chen | ICASSP 2022 | https://arxiv.org/abs/2202.01092 | empirical covariances are noisy → covariance regularisation/shrinkage helps |
| 21 | **Conditional Bures** Metric | Luo, Ren | CVPR 2021 | https://arxiv.org/abs/2108.00302 | Bures/Wasserstein alt; flags CORAL's weakness under class/label-proportion shift |

**Four limitations of a bare CORAL number, and our mitigations:**

1. **Second-order only.** CORAL is invariant to the feature **mean** and blind to skew/
   kurtosis (#19 makes the hierarchy precise: MMD=1st, CORAL=2nd, HoMM=k-th). → We report
   `mean_l2` (first-order) next to `coral_distance`; a future higher-order/CMD cross-check
   is cheap on the same cached features. *(This limitation is unit-tested:
   `test_coral_is_blind_to_pure_mean_shift`.)*
2. **Frobenius on a curved manifold.** Euclidean Frobenius between covariances is not
   affine-invariant and can mis-rank gaps for ill-conditioned covariances (#17). →
   Log-CORAL (#18, Frobenius-after-matrix-log) is a drop-in robustness check on the same
   covariances if a ranking ever looks suspect.
3. **Covariance-estimate variance at small n.** Empirical covariances are high-variance for
   small samples (#20). → We compute over a **large, equal number of frames per domain**
   (all 52 522 real / 52 522 synth in `datasets/mixed`, n ≫ d=1536) and report a
   **within-domain sampling-noise floor** (random-half split) so the cross-domain number is
   read *relative to noise* (`gap_ratio`), not in absolute terms. Ledoit–Wolf shrinkage is
   a future option if we ever measure on small batches.
4. **Marginal-only / label-shift confound.** CORAL aligns only marginal feature statistics,
   so a smaller number does not guarantee a smaller *task-relevant* gap if the synth and
   real corpora have different scene/contact-point/force mixes (#21). → Measure on the
   **paired real↔twin `mixed` set** (same sequences, same contact points, appearance is the
   main thing that differs) so the covariance gap isolates the **appearance** shift we
   actually target with data-side work.

**ConvNeXt caveat (#11):** ImageNet-pretrained backbones may be suboptimal feature
extractors for medical/surgical images, which affects the *absolute* interpretation of any
Fréchet/CORAL distance. This does not break relative comparisons under a **fixed** frozen
ConvNeXt, but it means the number is "gap in ImageNet-ConvNeXt feature space", not "gap in
an oracle surgical representation" — state this when reporting.

---

## 5. What this justifies in our tool (design decisions ← literature)

- **Metric = the covariance Frobenius distance** (#1–#3), computed as a measurement (#6–#11
  establish second-order distances are a legitimate, working shift diagnostic; #10/#13 are
  direct precedents).
- **Frozen, fixed feature extractor** so numbers are comparable across runs (rescaling
  constant is fixed; #11 caveat noted).
- **Report `mean_l2` beside CORAL** because CORAL is the covariance-only sibling of FID
  (#7) and is mean-blind (#19).
- **Report a within-domain floor + `gap_ratio`** — echoes the proxy-A-distance / FDD
  methodology of "distance only means something relative to a reference and vs transfer"
  (#8, #9, #10), and mitigates covariance-estimate variance (#20).
- **Measure on the paired real↔twin set** to isolate appearance and dodge the label-shift
  confound (#21).
- **Robustness checks kept in reserve** (Log-CORAL #18, higher-order/CMD #19/#6, FID #7)
  if a ranking is ever contested — computable on the same cached features.

**Novelty honesty:** frozen-ConvNeXt-CORAL as an *evaluation metric* on *surgical* images is
not directly precedented; the construct is well-backed (#10 pathology FDD, #13 sim→real
CORAL diagnostic), the exact protocol is ours.

---

## 6. Verification note & omissions

- All 21 papers above verified first-hand (WebSearch + WebFetch of the primary landing
  page); the `1/(4d²)` CORAL-loss form and the sample-covariance estimator were confirmed
  **verbatim** from arXiv:1607.01719 and arXiv:1612.01939.
- **Omitted for lack of a clean primary URL** (reported, not cited): a "Style-Based Metric
  for Quantifying the Synthetic-to-Real Gap in Autonomous Driving Image Datasets"
  (ResearchGate only, authors/venue unverifiable first-hand). Off-angle and excluded:
  "Feature-Weighted MMD-CORAL for ... Power Transformer Fault Diagnosis" (arXiv:2505.14896)
  and similar — they use MMD+CORAL as a *training loss*, not a measurement.
- Minor metadata: Deep CORAL's canonical venue is the ECCV 2016 TASK-CV workshop (LNCS
  9915); the Proxy-A-distance concept also appears in Ben-David et al. NeurIPS 2007
  ("Analysis of representations for domain adaptation") — the 2010 Machine Learning journal
  version is cited as the fuller reference.
