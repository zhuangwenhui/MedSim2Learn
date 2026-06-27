# Transfer-recipe race (which fine-tuning recipe for synth→real)

- **ID:** `2026-06-15_transfer-recipe-race`
- **Date:** 2026-06-15 – 2026-06-16
- **Status:** `DONE` (tied — no winner)
- **Owner:** WENHUIZ

## Purpose
If we pre-train on synthetic then fine-tune on real, which fine-tuning recipe wins?
Compared five recipes, all initialised from the same synthetic-pre-trained weights.

## Setup (reproduce)
- **Code:** `8b5081d`, run in an **isolated git worktree** `xfer-race` (now removed).
- **Configs:** `c4ft` full-FT, `c4dl` discriminative-LR, `c4sg` surgical (last few layers),
  `c4fz` frozen-backbone, vs `c4` linear-probe-then-fine-tune — variant configs lived only
  in the (now-deleted) worktree; the recipe definitions are recorded in this README and the
  `report_cv.py` DESCRIPTORS table.
- **Command:** `python scripts/run_cv.py` with the c4* configs → `report_cv.py` race section.

## Results (real-comparable magnitude MAE, 5-fold, mean ± sd)
| recipe | magMAE | angle |
|---|---|---|
| c1 scratch (baseline) | 0.232 ± 0.073 | 24° |
| c4 LP-FT | 0.209 ± 0.035 | 26° |
| c4ft full-FT | 0.216 ± 0.032 | 26° |
| c4dl disc-LR | 0.211 ± 0.039 | 25° |
| c4sg surgical | **0.207 ± 0.029** | 27° |
| c4fz frozen-head | 0.208 ± 0.033 | 26° |

- **Figures:** `DataFlow/KiDKNet/outputs/cv5/report/report_race_*.png`.
- **W&B:** `kidknet-xferrace`.

## Verdict
**DONE — all five recipes tie.** Spread 0.009 ≪ fold sd ~0.03; only marginally better than
scratch and within noise. The fine-tuning recipe is **not** a bottleneck; the only real
benefit of transfer over scratch is slightly more stable runs.

## Disposition
- **Code:** no winner to merge. The isolated worktree + `xfer-race` branch were removed on
  2026-06-27 (their only local-only content were the 4 variant configs + a `run_cv` tweak).
- **Standing record also in:** `RESEARCH_GOAL.md §7.2`, `report.md §4.3`.
