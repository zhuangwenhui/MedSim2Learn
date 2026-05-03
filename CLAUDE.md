# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace layout

`MedSim2Learn` is a multi-module workspace. Each top-level folder is an independent project with its own build system, dependencies, and (optionally) its own `CLAUDE.md` for module-specific guidance:

| Folder | Role |
|--------|------|
| `ShapeReconstruction/` | C++20 surface reconstruction (`.mvr` -> PLY) and DeformSim pre-flight diagnostics. |
| `DeformSim/` | Deformation simulation solver. |
| `Deform_post/` | Post-processing of DeformSim outputs. |
| `KiDKNet/` | Learning-based component. |
| `build/` | Out-of-tree CMake build artefacts (sibling per project, e.g. `build/ShapeReconstruction/...`). |
| `docs/`, `plans/`, `specs/` | Cross-project documentation and planning. |

When working inside a sub-project, always read that sub-project's `CLAUDE.md` (if present) for build commands, architecture, and module-specific conventions. The rules in this top-level file apply across **all** sub-projects.

## Global rules (apply to every sub-project)

These are the binding constraints distilled from `AGENTS.md`. Where this file and a sub-project's `CLAUDE.md` agree, follow both; where they conflict, the user's explicit instructions in the current conversation win.

### Communication

- All user-facing responses must be written in Chinese.
- All code comments, identifiers, and commit messages must be in English.
- Do not output emoji in chat or in code/files.

### Host and tooling

- The host has **no `sudo`**. Do not invent commands that require it.
- Git is controlled by the user. Do not stage, commit, push, merge, rebase, or roll back without explicit user approval. If asked for a commit, propose a Conventional Commits message and let the user run it.
- When the user pushes back on an action, stop and re-plan instead of retrying the same tool call.

### Change discipline

- No unbounded refactors. Prefer minimal, scoped, behavior-preserving changes layered on the existing structure. Separate refactors from feature work and bug fixes unless the refactor is strictly required.
- Reuse and extend existing classes, methods, and utilities before introducing new ones. Avoid duplicating logic across modules.
- Resource-sensitive changes (GPU memory, RAM, I/O, throughput, concurrency) must be tested for the resource concern itself, with results recorded, before being declared safe. Guard against OOM, data loss, and performance regression first.
- For performance optimization, isolate one variable at a time, validate independently, and combine only proven-beneficial changes. Never apply multiple untested optimizations together.

### Verification (first-hand evidence only)

- Never claim "validation successful", "tests pass", "fix verified", or similar without actually running the command and observing the output. If verification was not performed or was inconclusive, say so explicitly.
- Do not suppress negative results. Report failures truthfully, including stderr and non-zero exit codes.
- Track verification artefacts (log files, generated JSON, scratch builds) in a Markdown roster while or before tests run, recording path, purpose, owner, and cleanup expectation. Reconcile and clean up after the task unless the user asks to keep them.

### Sub-agent delegation (Main/Review/Improve/Test pattern)

- The Main Agent decomposes work and delegates command execution, heavy inspection, and large reads to sub-agents. Lightweight local reads for coordination are allowed.
- Re-brief sub-agents at every handoff: scope, allowed files, git restrictions, validation expectations, user-specific constraints. Report material drift to the user.
- Keep the sub-agent pool bounded. Closing long-running sub-agents requires user approval so their state remains traceable.
- Use the Review Agent (with the relevant `superpowers` skills, e.g. `requesting-code-review`, `verification-before-completion`) before declaring substantial work ready.

### Branch and worktree hygiene

- Optimization work goes on a dedicated branch; remind the user to create one if missing. Edit existing classes/functions in place on that branch — do not create `_optimized` variants.
- Branch worktrees must live in a sibling directory of the repo root, on the **same disk**. Cross-disk worktrees leak absolute paths into generated configs.
- Before deleting a worktree, diff against the main checkout, preserve any local-only files, and only remove after explicit user approval of the git operation.

## Where to find more

- `AGENTS.md` — the full, authoritative ruleset (this file is a Claude-Code-oriented summary, not a replacement).
- `<sub-project>/CLAUDE.md` — module-specific build/test commands and architecture (added per project as needed).
