# k-shot data-scarcity curve (synthetic pre-training vs ImageNet)

- **ID:** `2026-06-21_kshot-scarcity`
- **Date:** 2026-06-21 – 2026-06-22
- **Status:** `KEEP` (recorded; not statistically established)
- **Owner:** WENHUIZ

## Purpose
Synthetic priors should matter most when real data is *very* scarce. Test directly by
allowing only k real sequences (k = 1, 2, 4, 8, 16) for fine-tuning, starting from a
synthetic-pre-trained model vs a plain ImageNet model.

## Setup (reproduce)
- **Code:** `adf29a6` (`kshot_transfer.py`).
- **Command:**
  ```
  python experiments/2026-06-21_kshot-scarcity/kshot_transfer.py   # needs GPU
  python experiments/2026-06-21_kshot-scarcity/plot_kshot.py
  ```
- 3 random seeds per (arm, k).

## Results (real-test magnitude MAE; synthetic-start / ImageNet-start)
| k | synthetic | ImageNet |
|---|---|---|
| 1 | 0.582 | 0.755 |
| 2 | 0.563 | 0.590 |
| 4 | 0.309 | 0.340 |
| 8 | 0.325 | 0.306 |
| 16 | 0.230 | 0.239 |

- **Figures:** `DataFlow/KiDKNet/outputs/kshot/report/kshot_curve.png`; report figure `fig2_kshot`.

## Verdict
**KEEP (recorded), NOT statistically established.** Synthetic start is lower only at the
smallest k (≤ 2); converges to ImageNet by k ≥ 4; the s.d. bands overlap throughout (n = 3),
and most of the k=1 advantage came from a single lucky seed. At most a small, unproven edge
in the extreme-scarcity corner. Re-run with more seeds after the measurement overhaul to
confirm or drop.

## Disposition
- **Moved here:** `kshot_transfer.py`, `plot_kshot.py`.
- **Standing record also in:** `RESEARCH_GOAL.md §7`, `report.md §4.4`.
