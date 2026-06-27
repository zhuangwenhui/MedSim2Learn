# Loss task-weighting: learned uncertainty vs fixed lambda (RQ3)

- **ID:** `2026-06-22_loss-uncertainty-weighting`
- **Date:** 2026-06-22 – 2026-06-23
- **Status:** `PARK` — expiry **2026-09-30**
- **Owner:** WENHUIZ

## Purpose
Does a smarter loss — one that learns how much to trust each sample and auto-balances the
magnitude vs direction terms (Kendall homoscedastic uncertainty) — beat a hand-tuned fixed
ratio?

## Setup (reproduce)
- **Code:** `aa11317` (`dknet/utils/losses.py` weighting option, `force_trainer.py` loss
  parameters, `run_cv.py --loss-weighting`). **Config-gated, default `weighting='fixed'` —
  default behaviour is unchanged.**
- **Command:**
  ```
  python scripts/run_cv.py --loss-weighting uncertainty --cv-out DataFlow/KiDKNet/outputs/cv5_unc
  python experiments/2026-06-22_loss-uncertainty-weighting/plot_loss_ab.py DataFlow/KiDKNet c1,c3
  ```

## Results (real-comparable magnitude MAE, 5-fold)
| setting | fixed | learned uncertainty | change |
|---|---|---|---|
| real-only (c1) | 0.232 ± 0.073 | **0.190 ± 0.037** | mean −18%, spread −49% |
| mixed (c3) | 0.204 ± 0.054 | 0.206 ± 0.043 | mean ≈ flat, spread −20% |

- **Figures:** `DataFlow/KiDKNet/outputs/cv5_unc/report/rq3_loss_ab.png`; report figure `fig3_loss_uncertainty`.
- **W&B:** `kidknet-cv5` (unc runs).

## Verdict
**PARK.** Learned uncertainty robustly **reduces fold variance** in both regimes and lowers
the mean by 18% in the noisiest real-only regime — but the mean improvement is within one
s.d. at n = 5 (paired test not significant). The variance reduction is the robust part; the
mean win is promising but unproven.

## Disposition
- **Code:** **PARKED** — kept in trunk, config-gated, default-off (`weighting='fixed'`), so
  it adds no behaviour change. **Expiry 2026-09-30:** confirm the c1 mean win with the
  measurement overhaul (more folds/seeds, normalized targets) → promote to `KEEP`; otherwise
  **revert** the loss code.
- **Moved here:** `plot_loss_ab.py`.
- **Standing record also in:** `RESEARCH_GOAL.md §11`, `report.md §4.5`.
