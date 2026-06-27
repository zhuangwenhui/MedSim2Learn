# 8-condition cross-validation + appearance domain-gap

- **ID:** `2026-06-15_8cond-cv-and-domain-gap`
- **Date:** 2026-06-14 – 2026-06-16
- **Status:** `KEEP`
- **Owner:** WENHUIZ

## Purpose
Establish a real-comparable baseline for every training regime (8 conditions, c1–c8)
and decide whether the synthetic→real failure is a *physics* problem or an *appearance*
(looks-different) problem — they need completely different fixes.

## Setup (reproduce)
- **Code:** framework `c952e64`, tracking/report `8b5081d`.
- **Configs:** `KiDKNet/configs/c1…c8_*.yaml` (5-fold CV, leakage-guarded splits).
- **Commands:**
  ```
  python scripts/run_cv.py --cv-out DataFlow/KiDKNet/outputs/cv5 [--wandb]
  python scripts/report_cv.py --cv-out DataFlow/KiDKNet/outputs/cv5
  python experiments/2026-06-15_8cond-cv-and-domain-gap/analyze_domain_gap.py
  ```

## Results (real-comparable magnitude MAE / direction error, mean ± fold-sd)
| cond | setup | magMAE | angle |
|---|---|---|---|
| c1 | real-only (single) | 0.232 ± 0.073 | 24° |
| c2 | synthetic-only (single) | **1.357 ± 0.456** | 55° |
| c3 | mixed (single) | 0.204 ± 0.054 | 25° |
| c4 | transfer (single) | 0.209 ± 0.035 | 26° |
| c5 | real-only (seq) | 0.234 ± 0.023 | 28° |
| c6 | synthetic-only (seq) | **1.542 ± 0.097** | 60° |
| c7 | mixed (seq) | 0.222 ± 0.040 | 28° |
| c8 | transfer (seq) | 0.240 ± 0.037 | 29° |

Domain-gap diagnosis: a trivial classifier separates real vs synthetic features **100%**
(chance 50%); synthetic features are **several-fold less varied** than real.

- **Figures:** `DataFlow/KiDKNet/outputs/cv5/report/report_cv_*.png`,
  `DataFlow/Deform_post/feature_cache/domain_gap.png`; report figure `fig1_domain_gap`.
- **W&B:** `kidknet-cv5`.

## Verdict
**KEEP.** Synthetic-only fails ~6× (appearance gap, not physics — forces already match
real). Every real-containing regime converges to 0.20–0.24; synthetic adds no measurable
accuracy beyond real data at this scale. This is the project's main standing finding.

## Disposition
- **Code:** the CV framework (`run_cv.py`, `author_cv_splits.py`, `report_cv.py`) is trunk
  infrastructure and stays in `KiDKNet/scripts/`.
- **Moved here:** `analyze_domain_gap.py`, `plot_goal_state.py` (experiment-specific).
- **Standing record also in:** `RESEARCH_GOAL.md §7.1/§7.3`, `report.md §4.1/§4.2`.
