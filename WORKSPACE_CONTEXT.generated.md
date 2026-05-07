# cardsense-extractor Workspace Context

> DO NOT EDIT. Generated from `fleet-command/workspace/workspace.manifest.json`.

## Summary

- Workspace: `cardsense-workspace`
- Source of truth: `fleet-command`
- Repo role: `data-pipeline`
- Purpose: Promotion extraction, normalization, import, and sync pipeline

## Read First

- `README.md`
- `VIBE_SPEC.md`
- `skills/cardsense-bank-promo-review/SKILL.md`
- `extractor/promotion_rules.py`
- `jobs/refresh_and_deploy.py`

## Verification

- `verify`
  - `uv run pytest`
  - `uv run python jobs/refresh_and_deploy.py --help`

## Workspace Policies

- Python package management: Use uv for Python dependency management and Python command execution across the workspace.
- Browser verification: Use installed Google Chrome via gstack/browser for browser smoke tests; only fall back to another browser when Chrome is unavailable and report the fallback.
- Git and PR closeout: Do implementation work on a task branch, verify before commit, commit by repo, push the branch, and create or update the PR when remote access is available.
- Development CLI checks: Use cardsense-dev-checks during development for targeted tests, curl API smoke checks, Chrome/gstack browser checks, gh PR/CI inspection, and read-only deployment inspection.

## Completion Reminder

- Before finishing work, follow the completion flow in `fleet-command/AGENTS.md`.
- Organize branches by work type using `feat/fix/chore/wip`.
- For one cross-repo task, keep the same slug across repos.
- Python work uses `uv` for dependency management and execution.
- Run verification first.
- Run cardsense-workspace-completion before ending every CardSense workspace task; use fleet-dashboard-closeout for dashboard-specific details.
- Use cardsense-dev-checks during development for frequent CLI/API test and confirmation flows.
- Use uv for Python commands and Chrome via gstack/browser for browser checks.
- Confirm the task branch, commit verified changes, push, and create or update the PR when remote access is available.
- Update fleet-command when workflow, architecture, or workspace rules changed.
- Re-render workspace assets when the manifest or generated context changed.
- Organize branches by repo + branch type + shared slug.
- Batch commit by repo.
- Batch push by repo.

## Workspace Notes

- Read generated repo context before scanning long status documents.
- Use fleet-command as the control plane for cross-repo workflow and conventions.
