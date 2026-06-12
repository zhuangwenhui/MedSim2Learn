# CLAUDE.md

Top-level rules for the `MedSim2Learn` workspace. They apply across **all** sub-projects. Where this file and a sub-project's `CLAUDE.md` agree, follow both; where they conflict, the user's explicit instructions in the current conversation win. The full authoritative ruleset is `AGENTS.md`; this is the Claude-Code-oriented distillation.

`MedSim2Learn` is a multi-module workspace — each top-level folder is an independent project with its own build system. Do not restate the file/folder architecture here: it is covered by the graphify knowledge graphs (below) and each sub-project's own `CLAUDE.md`.

## Knowledge graphs (use before scanning)

**Read the matching `GRAPH_REPORT.md` before grep'ing or scanning source files in a sub-project** — it lists god nodes, community structure, and bridges that orient a session far faster than raw search, regardless of the session `cwd`.

| Sub-project | Report | Raw graph |
|---|---|---|
| ShapeReconstruction | `ShapeReconstruction/graphify-out/GRAPH_REPORT.md` | `ShapeReconstruction/graphify-out/graph.json` |
| DeformSim | `DeformSim/graphify-out/GRAPH_REPORT.md` | `DeformSim/graphify-out/graph.json` |

Maintain with `python -m graphify update <sub-project-path>` after non-trivial code changes; update the table when a graph is added or retired.

## Data flow

Pipeline data lives under `DataFlow/<stage>/`, never inside the source module directories. Each stage writes its own subdirectory; the next stage reads from it via config/CLI/env (no hardcoded deep paths). `DataFlow/` is git-ignored as a single unit. Read-only external corpora and toolchain deps are referenced by absolute path in `data_sources.yaml` (repo root), not copied in. `build/` is not pipeline data — keep it out of `DataFlow/`.

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
