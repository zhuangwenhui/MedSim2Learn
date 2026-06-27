# CLAUDE.md

Top-level rules for the `MedSim2Learn` workspace. They apply across **all** sub-projects. Where this file and a sub-project's `CLAUDE.md` agree, follow both; where they conflict, the user's explicit instructions in the current conversation win. The full authoritative ruleset is `AGENTS.md`; this is the Claude-Code-oriented distillation.

`MedSim2Learn` is a multi-module workspace — each top-level folder is an independent project with its own build system. Do not restate the file/folder architecture here: it is covered by the graphify knowledge graphs (below) and each sub-project's own `CLAUDE.md`.

## Knowledge graphs (use before scanning)

**Read the matching `GRAPH_REPORT.md` before grep'ing or scanning source files in a sub-project** — it lists god nodes, community structure, and bridges that orient a session far faster than raw search, regardless of the session `cwd`.

| Sub-project | Report (tracked) | Raw graph (local-only) |
|---|---|---|
| ShapeReconstruction | `ShapeReconstruction/graphify-out/GRAPH_REPORT.md` | `ShapeReconstruction/graphify-out/graph.json` |
| DeformSim | `DeformSim/graphify-out/GRAPH_REPORT.md` | `DeformSim/graphify-out/graph.json` |
| Deform_post | `Deform_post/graphify-out/GRAPH_REPORT.md` | `Deform_post/graphify-out/graph.json` |

Maintain with `python -m graphify update <sub-project-path>` after non-trivial code changes; update the table when a graph is added or retired. Only `GRAPH_REPORT.md` is tracked in git: `graph.json` and the root-level `graphify-out/` update cache are machine-local (the cache even embeds absolute paths) and regenerate in seconds at zero token cost — run the update command whenever `graph.json` is missing or stale.

## Data flow

Pipeline data lives under `DataFlow/<stage>/`, never inside the source module directories. Each stage writes its own subdirectory; the next stage reads from it via config/CLI/env (no hardcoded deep paths). `DataFlow/` is git-ignored as a single unit. Read-only external corpora and toolchain deps are referenced by absolute path in `data_sources.yaml` (repo root), not copied in. `build/` is not pipeline data — keep it out of `DataFlow/`.

### DataFlow/Deform_post layout (4 tiers — keep raw separate from regenerable)

Logical sizes are inflated by hardlinks (merged dirs share inodes with the per-sequence `.pt`); the only truly expensive/irreproducible bytes are ~15 GB. Keep these tiers so a human can tell "what would hurt to lose" from "what regenerates in seconds":

- `inputs/` — hand-authored primary inputs: `annotations/` (FEM freeze+contact JSON), `cameras/` (saved camera profiles). Not cheaply regenerable; treat as source.
- `primary/` — the only expensive on-disk products: `twin_full/` (FEM `.ply` meshes + 800px renders) and `real_full/` (256px real renders + `labels.csv`; its per-sequence serialized `.pt` now lives in `preprocessed/sources/real`). **Keep them siblings in the same parent** — `main.py` derives `real_full` from `dirname(out_root)`, and `dpost/config.py` `out_root` defaults to `primary/twin_full`.
- `preprocessed/` — regenerable caches organized by DOMAIN. `sources/<domain>/` holds the per-sequence serialized `.pt` (`real/`, `synt/{twin,gen}/`); `datasets/<domain>/` holds the assembled KiDKNet `data_dir`s (`real/`, `synt/{twin,gen}/`, `mixed/`). `gen/` holds synthetic sequences outside the paired real↔twin set — algorithmic forcegen, or twin renders whose real-image pair is unusable (currently `twin_seq04`: real forces are valid but `04.mp4` is black, so its twin is parked here as augmentation, not in the paired `twin/`). `mixed/` exists only under `datasets/` (there is no per-sequence mixed source). Batches are same-volume hardlinks: `datasets/real` + the real half of `datasets/mixed` link `sources/real`; `datasets/synt/twin` + the synt half of `datasets/mixed` link `sources/synt/twin`. Superseded sets are deleted outright (they regenerate via `assemble`).
- `feature_cache/` — ConvNeXt feature caches, materialized on demand by `dknet.data.feature_cache.precompute_features`.
- `_excluded/` — data blacklist. The maintainer removes the actual invalid files; the only tracked artefact is `blacklist.txt` (one record per dropped item: `name` + `reason`), the durable audit record of what was excluded and why (e.g. seq04: source `04.mp4` is black). Do not re-add bulk bad-data copies here.

Moving a `datasets/<domain>` dir is a **three-place edit**, never a bare `mv`: (1) the KiDKNet config `data_dir`, (2) the absolute `data_dir` baked inside each split JSON (validated char-for-char — a mismatch raises), (3) feature-cache `source_data_dir`. Prefer **re-authoring the splits** with the new path (deterministic; `author_cv_splits.py` re-bakes cv5) over `mv`+hand-patching JSON. Directory renames on the same disk preserve inodes/hardlinks (zero byte movement), so a restructure = rename + re-author splits + re-point configs. CV splits authored by `KiDKNet/scripts/author_cv_splits.py` (5-fold, paired by id, leakage-guarded); `Deform_post/dpost/dataset/assemble.py` (by-sequence) + `KiDKNet/scripts/author_paired_splits.py` author the legacy fixed splits.

## Global rules (apply to every sub-project)

### Communication
- All user-facing responses in Chinese. All code comments, identifiers, and commit messages in English. No emoji anywhere.

### Host and tooling
- The host has **no `sudo`**. Do not invent commands that require it.
- When the user pushes back on an action, stop and re-plan instead of retrying the same tool call.

### Git: signature, commit cadence, racing
- **Signature (absolute).** Every commit's author and committer is ONLY `WENHUIZ <84453228+zhuangwenhui@users.noreply.github.com>`. No `Co-Authored-By`, no "Generated with Claude Code", no AI/tool footer. Messages are human-style Conventional Commits — not AI-prompt prose or a spec/plan changelog.
- **Commit cadence.** Default to letting small / incremental changes accumulate and waiting for the user's commit decision (their office hours). Auto-commit to the current branch is authorized only for overnight, handed-off exploratory tasks. This keeps the working branch from racing far ahead of master and bloating.
- **Race in isolated worktrees; merge only the winner.** When racing rival technical approaches (赛马), give each approach its own worktree (sibling dir, same disk) and commit only inside it. Never pile competing approaches onto one shared branch — it bloats trunk with dead-end code that must later be surgically deleted (cf. ShapeReconstruction's robust-pipeline -> realignment churn: whole features authored into master then removed, ~13 of 36 commits pure deletions). After the race: delete the losing worktrees, absorb only the winner's useful bits into one clean change, then merge that to master.

### Change discipline
- No unbounded refactors. Prefer minimal, scoped, behavior-preserving changes. Separate refactors from feature work and bug fixes unless strictly required.
- Reuse and extend existing classes, methods, and utilities before adding new ones. Avoid duplicating logic across modules.
- Resource-sensitive changes (GPU memory, RAM, I/O, throughput, concurrency) must be tested for the resource concern itself, with results recorded, before being declared safe. Guard against OOM, data loss, and performance regression first.
- For performance optimization, isolate one variable at a time, validate independently, and combine only proven-beneficial changes.

### Experiment lifecycle & records (no dead code; traceable results)
Experiments change code only to test an idea - don't let trials rot into dead code, and keep
results traceable after the temporary code/data is gone.
- **Ledger:** every experiment gets `experiments/<YYYY-MM-DD>_<slug>/README.md` (from
  `experiments/TEMPLATE.md`) - purpose, exact commit SHA + config, command, results (numbers +
  figure paths + W&B), verdict, disposition - committed; heavy data stays in git-ignored
  `DataFlow/`/W&B. Add a row to `experiments/INDEX.md`.
- **Code disposition is mandatory at conclusion:** KEEP -> merge + make default; LOSE -> revert/
  remove the code (the record keeps config + results); PARK -> keep gated-off **with an expiry**
  in `INDEX.md`, then confirm-or-revert. No indefinite dormant code.
- **Scripts:** one-off experiment scripts live under `experiments/<id>/`; `KiDKNet/scripts/` is
  for reusable infrastructure only.

### Verification (first-hand evidence only)
- Never claim "validation successful", "tests pass", or "fix verified" without running the command and observing output. If verification was not performed or was inconclusive, say so.
- Do not suppress negative results; report failures with stderr and non-zero exit codes.
- Track verification artefacts (logs, generated JSON, scratch builds) in a Markdown roster: path, purpose, owner, cleanup expectation. Reconcile and clean up after the task unless asked to keep them.

### Sub-agent delegation (Main/Review/Improve/Test)
- The Main Agent decomposes work and delegates command execution, heavy inspection, and large reads to sub-agents; lightweight local reads for coordination are fine.
- Re-brief sub-agents at every handoff: scope, allowed files, git restrictions, validation expectations, user constraints. Report material drift.
- Keep the sub-agent pool bounded; closing long-running sub-agents needs user approval.
- Use the Review Agent (relevant `superpowers` skills) before declaring substantial work ready.

### Branch and worktree hygiene
- Optimization work goes on a dedicated branch; remind the user to create one if missing. Edit existing classes/functions in place — no `_optimized` variants.
- Worktrees live in a sibling directory of the repo root, on the **same disk** (cross-disk worktrees leak absolute paths into generated configs).
- Before deleting a worktree, diff against the main checkout, preserve local-only files, and remove only after explicit user approval.
