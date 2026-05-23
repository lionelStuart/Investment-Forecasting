# TASK-008: WebUI Workbench

## Status

completed

## Source

`SPEC-006`

## Goal

Build a workbench-style WebUI for inspecting data, predictions, backtests, daily
advice, and task logs.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-006-webui-workbench.md`
- `ARCHITECTURE.md`

## Modify Scope

- WebUI source files.
- Backend/API endpoints if needed.
- UI tests or browser QA scripts.
- Project memory write-back files.

## Forbidden

- Do not create a marketing landing page.
- Do not hide stale data or task failures.
- Do not present forecasts as certainty.

## Acceptance

- Dashboard shows market state, risk level, and today's advice summary.
- Data/fund pages show asset histories, metrics, and rankings where available.
- Prediction page shows probability, expected return, downside risk, confidence,
  model version, and date.
- Backtest page shows score history, return, max drawdown, and benchmark
  comparison.
- Task log page shows status, errors, and duration.
- Browser verification confirms the UI renders without layout-breaking overlap
  on desktop and mobile widths.

## Test Plan

- Run frontend/backend tests.
- Start the local dev server.
- Use browser QA screenshots for desktop and mobile.
- Verify empty-data and failed-job states.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added local WebUI command:
  `investment-forecasting web run --db ... --host 127.0.0.1 --port 8765`.
- Added workbench pages for dashboard, data, funds, predictions, backtests,
  daily advice, and task logs.
- Dashboard shows market state, risk level, prediction date, expected return,
  downside risk, confidence, latest job status, asset coverage, and latest
  advice summary.
- Data/funds pages show asset histories and feature/risk metrics.
- Prediction and backtest pages show model versions, probabilities, returns,
  downside risk, confidence, scores, and sample windows.
- Daily advice page preserves aggressive, balanced, and conservative variants,
  assumptions, risk warnings, and evidence.
- Task logs page shows status, errors, durations, and messages.
- Added server-render tests for empty and populated databases.
- Validation passed with `python3 -m pytest`.
- Browser verification used Playwright against `http://127.0.0.1:8765/` at
  desktop and mobile widths. Screenshots were written to
  `/tmp/if-webui-desktop.png` and `/tmp/if-webui-mobile.png`; both rendered
  without console errors or invalid layout boxes.

## Follow-Ups

- Add charts and filtering once core inspection flows are stable.
