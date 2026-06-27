<!-- Copy this file to experiments/<YYYY-MM-DD>_<slug>/README.md and fill it in.
     Heavy data/figures stay in the git-ignored DataFlow tree or W&B; THIS record
     (commit SHA + config + numbers + verdict) is committed so the experiment is
     traceable even after the temporary code/data is gone. -->

# <Experiment title>

- **ID:** `<YYYY-MM-DD>_<slug>`
- **Date:** <start> – <end>
- **Status:** `KEEP` | `PARK` | `LOSE` | `DONE`   <!-- see lifecycle policy in AGENTS.md -->
- **Owner:** WENHUIZ

## Purpose / hypothesis
What question this run answers and why.

## Setup (reproduce)
- **Code:** commit `<sha>` (branch/worktree `<name>` if isolated)
- **Config(s):** `<paths or copied into ./configs/>`
- **Command(s):**
  ```
  <exact command>
  ```

## Results
| metric | value |
|---|---|
| … | … |
- **Figures:** `<DataFlow path(s)>` and/or `experiments/<id>/figures/`
- **W&B:** `<project / run id>`

## Verdict
KEEP / PARK / LOSE — one-paragraph honest reading (effect size vs noise; n; caveats).

## Disposition
- **Code:** merged to trunk / reverted in `<commit>` / parked (gated off, default behaviour unchanged).
- **PARK expiry:** `<date>` — confirm or revert by then. *(PARK only)*
- **Standing record also in:** `RESEARCH_GOAL.md §…`, `report.md §…`.
