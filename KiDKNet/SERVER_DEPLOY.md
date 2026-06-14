# KiDKNet server deployment (local build -> 10.232.99.48 train/eval)

Workflow: build/adapt the framework locally, push **code + the two merged
datasets** to the lab Linux server, **regenerate splits + precompute features
there**, run the 8-condition cross-validation, then pull back **checkpoints +
eval reports + cross-fold summaries**. FEM simulation (DeformSim /
ShapeReconstruction / raw PLY+render intermediates) stays local and is never
uploaded.

Use rsync from Git-Bash or WSL on Windows (resumable). Fill in `SERVER` /
`REMOTE` once:

```bash
SERVER=<user>@10.232.99.48          # e.g. zhuang@10.232.99.48
REMOTE=~/medsim                     # remote base dir
```

## What goes up / what stays

| Path (local) | Upload? | Why |
|---|---|---|
| `KiDKNet/` (minus `outputs/`, `__pycache__`, `.vscode`) | YES (every code change) | the framework |
| `DataFlow/Deform_post/preprocessed/datasets/real/` | YES (once) | real 256² dataset (31 seq / 52,522 frames) — C1/C4/C5/C8 |
| `DataFlow/Deform_post/preprocessed/datasets/mixed/` | YES (once) | paired real+synt (62 seq / 105,044 frames) — C2/C3/C6/C7 |
| `DataFlow/KiDKNet/splits/cv5/` | NO — **regenerate on server** | split JSONs bake an absolute Windows `data_dir`, validated char-for-char |
| `DataFlow/Deform_post/feature_cache/` | NO — **built on server** | frozen-ConvNeXt features; precompute once per source |
| `DataFlow/Deform_post/{twin_full, real_full, primary, _excluded}` | NO | raw renders/sims + quarantine — local only |
| `build/`, `DeformSim/`, `ShapeReconstruction/`, `*.ply` | NO | FEM toolchain — local only |

Push the two merged dirs together with `rsync -aHvz`: the real frames that
`datasets/mixed` hardlinks into `datasets/real` are then transferred once, not
twice.

## Steps

| # | Goal | Command (local Git-Bash/WSL unless noted) |
|---|---|---|
| 0 | Remote dirs | `ssh $SERVER "mkdir -p $REMOTE/KiDKNet $REMOTE/data $REMOTE/outputs"` |
| 1 | Push code (every change) | `rsync -avz --delete --exclude __pycache__ --exclude .vscode --exclude outputs KiDKNet/ $SERVER:$REMOTE/KiDKNet/` |
| 2 | Push data (once; resumable; `-H` dedupes hardlinks) | `rsync -aHvz --progress DataFlow/Deform_post/preprocessed/datasets/real DataFlow/Deform_post/preprocessed/datasets/mixed $SERVER:$REMOTE/data/` |
| 3 | Build env (once; on server) | `cd $REMOTE/KiDKNet && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt` (match the server CUDA to a compatible torch build) |
| 4 | Regenerate splits with server paths (on server) | `python scripts/author_cv_splits.py --real-merged $REMOTE/data/real --mixed-dir $REMOTE/data/mixed --out-dir $REMOTE/data/splits/cv5` — seed 42 reproduces the identical fold membership with the server `data_dir` baked in |
| 5 | Precompute features for C5-C8 (on server, GPU) | `python -m dknet.data.feature_cache --source $REMOTE/data/real --out $REMOTE/data/feature_cache/real_feat_convnextL --size large` then the same for `datasets/mixed -> mixed_feat_convnextL` |
| 6 | Point base configs at server paths | edit `configs/c1..c8` (or a `configs/server/` copy): `data.data_dir` (merged dir for C1-4, the matching `feature_cache/*_feat_convnextL` for C5-8), `general.output_dir`, `general.result_dir`. The driver overrides `data.split_file` + the per-fold output dir automatically — do **not** hand-edit those. |
| 7 | Dry-run the plan (on server) | `python scripts/run_cv.py --splits-dir $REMOTE/data/splits/cv5 --cv-out $REMOTE/outputs/cv5 --config-dir configs --dry-run` (expect "0 problem(s)") |
| 8 | Run CV (on server; `tmux`/`nohup`) | `python scripts/run_cv.py --splits-dir $REMOTE/data/splits/cv5 --cv-out $REMOTE/outputs/cv5 --config-dir configs --skip-existing` |
| 9 | Pull results | `rsync -avz $SERVER:$REMOTE/outputs/cv5/ ./DataFlow/KiDKNet/outputs_server/cv5/` (per-fold checkpoints, eval reports, and `<cond>/cross_fold_summary.json`) |

`run_cv.py` accepts `--conditions c1,c2,...` and `--folds 0,1,...` to run a
subset; with no subset it runs all 8 conditions over all 5 folds in dependency
order.

## How the run realizes the locked decisions

- **#3 shared 5-fold** — every condition runs over the SAME `cv5` fold partition.
  Per (condition, fold) the driver deep-copies the base config and overrides only
  `data.split_file` -> `fold{f}/{real_split,c2_synt2real_split,c3_mixed_split}.json`
  (C1/C4/C5/C8 -> real, C2/C6 -> c2, C3/C7 -> c3) and the fold-scoped output dir.
- **#5 init pinning** — C4/C8 run AFTER C2/C6 within each fold; their
  `training.transfer.init_from_checkpoint` is auto-pinned to the SAME fold's
  C2/C6 `checkpoints/best_model.pth` (never a cross-fold checkpoint). Include the
  init source in the run (`--conditions c2,c4` is the minimum for a C4 fold), or
  run all conditions so the driver resolves the dependency.
- **#4 domain slices** — evaluating C3/C7 (mixed test) emits `real_only` /
  `synt_only` / pooled metric blocks in `evaluation_report.json`; only the
  `real_only` slice is commensurable with the real-only-tested C1/C2/C4.
- The driver aggregates each condition's folds into
  `<cond>/cross_fold_summary.json` (pooled + `real_only_slice`, each as
  mean ± SD across folds). This is the headline number per condition.

## Notes

- **Splits are regenerated on the server (step 4), not uploaded** — the split
  JSON validates its baked absolute `data_dir` char-for-char, so Windows paths
  would fail on Linux. `author_cv_splits.py` is deterministic (seed 42), so the
  regenerated folds have identical sequence membership.
- **Feature caches are built on the server (step 5)** — one cache per source,
  reused read-only across all 5 folds. This is leak-safe: a frame's feature is a
  deterministic frozen-ConvNeXt forward under fixed ImageNet normalization (see
  `dknet/data/feature_cache.py`). C5-C8 fail fast if the cache is missing.
- **The sweep is resumable** even though a single training has no resume:
  `--skip-existing` skips any (cond,fold) that already has a completed experiment
  + eval report, so a crash only loses the in-flight fold. Always run under
  `tmux`/`nohup`.
- **Do NOT run `--mode split`** — splits are authored by `author_cv_splits.py`
  (CV) / Deform_post `assemble` (fixed); the built-in splitter would overwrite
  them with a leaky random holdout.
- **LOSO is deferred** until 5-fold feasibility is confirmed. When ready,
  regenerate with `python scripts/author_cv_splits.py ... --folds 31 --val-count 2`
  and rerun the driver against the new `cv31` dir.
