# TASK-055: Theme Allocation Overview

## Status

completed

## Purpose

Lift deterministic industry/theme labels from individual assets into a
portfolio-research view. Users should be able to compare theme-level coverage,
recent performance, drawdown, prediction coverage, and representative assets
without manually scanning all funds, ETFs, stocks, and predictions.

## Scope

- Add a `/themes` WebUI route and navigation entry.
- Aggregate stored assets by deterministic theme labels.
- Show each theme's asset count, prediction coverage, latest feature date,
  average 20-day return, average drawdown, and average expected return.
- Let users drill into one theme and inspect representative assets with links
  to `/data`.
- Reuse existing asset, feature, prediction, and theme-classification helpers.

## Non-Scope

- No live portfolio allocation execution.
- No new industry taxonomy table.
- No fund holdings or capital-flow ingestion.
- No advice generation changes.

## Files Changed

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ROADMAP.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-006-webui-workbench.md`

## Acceptance Criteria

- `/themes` renders on populated databases.
- Theme cards show count, prediction coverage, performance, drawdown, and
  expected-return summaries.
- Selecting a theme displays representative assets with links to asset detail.
- Tests cover route rendering and a technology-theme drill-in.

## Verification

- `python3 -m pytest tests/test_web_app.py`
- `scripts/restart_web.sh`
