# Experiment ledger (index)

One row per experiment. Heavy data/figures live in the git-ignored `DataFlow/` tree
or in W&B; the per-experiment `README.md` linked below is **committed** so each run
stays traceable (commit SHA + config + numbers + verdict) even after the temporary
code or data is gone. Lifecycle policy: see `AGENTS.md` / `CLAUDE.md`.

| date | id | purpose | status | record |
|---|---|---|---|---|
| 2026-06-15 | 8cond-cv-and-domain-gap | real-comparable baseline for 8 training regimes + appearance-gap diagnosis | **KEEP** | [README](2026-06-15_8cond-cv-and-domain-gap/README.md) |
| 2026-06-15 | transfer-recipe-race | which fine-tuning recipe is best for synth→real transfer (5 recipes) | **DONE** (tied) | [README](2026-06-15_transfer-recipe-race/README.md) |
| 2026-06-21 | kshot-scarcity | synthetic pre-training vs ImageNet at k real sequences | **KEEP** | [README](2026-06-21_kshot-scarcity/README.md) |
| 2026-06-22 | loss-uncertainty-weighting | learned uncertainty vs fixed loss weighting | **PARK** (expiry 2026-09-30) | [README](2026-06-22_loss-uncertainty-weighting/README.md) |
| 2026-06-21 | photometric-augmentation | does label-safe photometric augmentation help | **LOSE** (reverted) | code removed; finding kept in `report.md §4.6`, config in commit `c3ed62f` |

**Status legend:** `KEEP` = adopted into trunk · `PARK` = kept config-gated/off with an
expiry to confirm-or-revert · `LOSE` = reverted (code removed, finding retained) ·
`DONE` = completed one-off, no further action.
