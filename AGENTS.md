# AGENTS.md - Guidance for OpenAI Codex

This `AGENTS.md` file provides instructions for OpenAI Codex and other AI agents collaborating on this repository.

---

## Critical Project Guidelines (Must Follow)

**Host constraint:** There is no permission to use `sudo` commands on the host machine.

### Mandatory Behavior Rules

1. Unless explicitly permitted, do not attempt unbounded refactoring of existing code. Prefer optimization and targeted improvement on top of the existing code foundation.

2. Follow the first-hand information principle. For anything requiring validation, report only genuine, effective verification results. Do not print misleading claims such as "validation successful" without actual evidence. Do not suppress negative results. If no real information is available, say that verification could not be obtained rather than presenting estimates as measured facts.

3. Do not output emoji expressions.

4. All user-facing responses must be in Chinese.

5. All code comments must be written in English.

6. Git operations are controlled by the user; see **Git Commit Policy** below for signature, commit cadence, and approach-racing rules. Do not push, merge, rebase, or roll back without explicit user approval.

7. The Main Agent normally delegates command execution, tests, and heavy inspection to sub-agents. Lightweight local reads for coordination are allowed only when needed to plan or delegate, and must be kept minimal.

8. Verification artifacts must be tracked in a Markdown roster before or while tests run. Record the artifact path, purpose, owner, and cleanup expectation. After the task, reconcile the roster against actual logs/results, then clean up temporary artifacts unless the user asks to preserve them.

### Git Commit Policy

- **Signature (absolute):** every commit's author and committer is ONLY `WENHUIZ <84453228+zhuangwenhui@users.noreply.github.com>`. No `Co-Authored-By`, no "Generated with Claude Code", no AI/tool footer. Messages are human-style Conventional Commits, not AI-prompt prose or a spec/plan changelog.
- **Cadence:** let small / incremental changes accumulate and wait for the user's commit decision (their office hours). Auto-commit to the current branch is authorized only for overnight, handed-off exploratory tasks, so the working branch does not race far ahead of master.
- **Racing approaches:** see Branch Management below — race each rival approach in its own worktree and merge only the winner.
- **Gap-reduction victory gate (owner ruling, 2026-08-10):** on the data-improvement line, technical-verification work may enter master or be pushed to origin ONLY after it demonstrates a verified data-side gap reduction on the task metric (gap-closed % under the frozen c2-baseline / c1-ceiling protocol). Until then all such branches remain local; proxy metrics (feature separability, visual acceptance) do not count as victory.

---

## Collaboration Protocol

### Multi-Agent Workflow

For code optimization work, use this role model when appropriate:

| Agent | Role | Trigger |
|-------|------|---------|
| **Main Agent** | Understands user commands, decomposes tasks, dispatches to sub-agents, aggregates results, and checks that delegated context remains accurate. | Always active |
| **Review Agent** | Performs code review and pre-merge review; uses applicable review skills including `python-code-format` for Python style decisions; evaluates whether code can be simplified while preserving behavior; never commits or merges without user approval. | Before merging, committing, or declaring substantial work ready |
| **Improve Agent** | Implements changes per Main Agent instructions, including feature additions, redundancy removal, conflict resolution, and scoped refactoring; hands off to Test Agent when implementation is complete. | When code modification is required |
| **Test Agent** | Validates behavior under expected usage scenarios, including model training and evaluation when relevant; passes work to Review Agent only after tests are complete and results are recorded. | After Improve Agent completes |

For ordinary tasks, the Main Agent still understands the request, decomposes the work, and assigns an appropriate number of sub-agents based on task complexity. The structure may be lighter than the optimization workflow, but the same scope, git, and verification constraints apply.

### Agent Lifecycle Rules

- Keep the sub-agent pool bounded. Only create additional sub-agents when they are strictly necessary to reduce risk, parallelize independent work, or preserve focus.
- If more than four sub-agents exist, close only short-lived idle or completed sub-agents. Long-running sub-agents require user approval before closure so their state remains traceable.
- Short-lived sub-agents may terminate after completing their assigned task.
- The Main Agent must verify sub-agent context at handoff points and checkpoints. If compression or drift changes a sub-agent's understanding of the codebase, task state, constraints, or git status, the Main Agent must re-brief that sub-agent before continuing and report material drift to the user.
- Each sub-agent handoff must include the current task scope, allowed files, git restrictions, validation expectations, and any user-specific constraints.

### Review Agent Skill Usage

The Review Agent should use installed skills when they match the review task:

- `requesting-code-review`: use for completed tasks, major features, and pre-merge review. Installed at `C:\Users\space\.codex\plugins\cache\openai-curated\superpowers\421657af\skills\requesting-code-review\SKILL.md`; includes the `code-reviewer.md` template and reports findings by Critical, Important, and Minor severity.
- `receiving-code-review`: use when addressing review feedback; first understand, verify, and evaluate each point before implementing changes.
- `github`, `gh-address-comments`, and `gh-fix-ci`: use for GitHub PR, issue, review-thread, and CI workflows.
- `python-code-format`: MUST use for Python code review, formatting, naming, docstrings, logging, resource handling, or Python 3.12 syntax choices once Codex has been restarted and the skill is available. Its reference is `references/python-code-format-research.md` inside the installed `python-code-format` skill. If the current session has not been restarted and `python-code-format` is not listed in the available skills, read the installed files directly from `C:\Users\space\.codex\skills\python-code-format` when needed and report if they are unavailable.
- `simplify`: use for behavior-preserving cleanup after recent changes when simplification is appropriate.
- `karpathy-guidelines`: use to keep changes surgical, avoid over-design, surface assumptions, and define verifiable success criteria.
- `verification-before-completion`: use before claiming that work is complete, fixed, or passing; fresh verification evidence is required.

---

## Change Execution Principles

These principles govern all code modifications and additions.

### Conservative Changes

1. New code must be minimal and purposeful. Reuse existing implementations first, and add new code only when the existing code cannot cover the requirement.

2. Refactoring is permitted only when it is scoped and defensible. It must either be directly required for the task or preserve behavior while demonstrably improving maintainability, correctness, or runtime efficiency.

3. Separate unrelated refactors from feature work and bug fixes unless the refactor is directly required to complete the requested change safely.

4. When similar functionality already exists, extend or generalize existing classes, methods, and utilities instead of duplicating logic.

### Resource-Aware Changes

1. Any modification involving compute resources, including GPU memory, RAM, I/O, concurrency, or throughput, must be tested specifically for that resource concern first, with results recorded.

2. Guard against OOM, data loss, and performance regression above all else.

3. Resource ceiling exploration is allowed only when it is configurable, rollback-capable, reproducible, and validated under controlled conditions.

### Gradual Optimization Principle

When performing performance optimization, especially architectural-level changes:

- Use control-variable methodology to isolate each optimization.
- Create separate test files or test cases for each optimization based on the original version.
- Test and validate each optimization independently before combining changes.
- Document performance metrics for each optimization.
- Combine only optimizations proven beneficial through testing.
- Never apply multiple untested optimizations simultaneously.
- Maintain traceability from baseline to final optimized version.

### Branch Management for Code Optimization

When optimizing existing code:

- First check whether a dedicated branch has been created for the optimization work.
- If no dedicated branch exists, remind the user to create one before proceeding with optimization.
- When optimizing classes, methods, or functions with the same name, edit them directly in the branch without adding suffixes such as `_optimized`.
- Do not create duplicate optimized variants such as `ClassName_optimized` alongside `ClassName`.
- Direct replacement in a separate branch keeps code management and merging cleaner.
- Branch worktrees must be created only in a sibling directory of the repository root, not on another drive or under user config/cache directories.
- Do not create branch worktrees on a different disk from the main project checkout. Cross-disk worktrees can leak absolute build, dependency, or validation paths into generated configuration and later make merge or handoff validation ambiguous.
- Before deleting a branch worktree, compare it with the main checkout, preserve any required local-only files, then remove the worktree and branch only after the user explicitly approves the git operation.
- When racing rival technical approaches (赛马), give each approach its own worktree (sibling dir, same disk) and commit only inside it; never accumulate competing approaches on one shared branch — it bloats trunk with dead-end code that must later be surgically deleted. After the race, delete the losing worktrees, absorb only the winner's useful bits into one clean change, then merge that to master, so trunk records the winner rather than every loser (cf. the ShapeReconstruction robust-pipeline -> realignment deletion churn: whole features authored into master then removed).

### Code Reuse

When optimizing code or adding features:

- Investigate existing code, classes, methods, and utility functions before writing new code.
- Extend existing classes and methods rather than creating new ones when functionality overlaps.
- Reuse established design patterns, architecture, and module organization.
- Check related modules for utilities that can be reused or extended.
- Avoid copying code; extract a reusable function or class when shared behavior is needed.
- Maintain consistency with existing style, naming conventions, and architecture.
- Document modifications to shared code when dependent behavior may be affected.

---

## Software Development Workflow Principles

- Keep changes small, self-contained, and reviewable. See Google Engineering Practices on small CLs: https://google.github.io/eng-practices/review/developer/small-cls.html
- Prefer short-lived branches and clear integration flow. See GitHub Flow: https://docs.github.com/en/get-started/using-github/github-flow and DORA trunk-based development: https://dora.dev/capabilities/trunk-based-development/
- Include or update relevant tests whenever behavior changes.
- Preserve build and test evidence before claiming success.
- Keep PR and change summaries focused on the problem, the change, validation evidence, and remaining risk.
- Use Conventional Commits style only for suggested commit messages when the user asks for one: https://www.conventionalcommits.org/en/v1.0.0/

---

## Allowed Autonomous Behavior

1. To validate potential training-process errors, agents may open another terminal to run training or validation commands for monitoring, subject to the delegation, resource, and artifact-roster rules above.

2. Agents may autonomously call installed skills that fit the current task.
