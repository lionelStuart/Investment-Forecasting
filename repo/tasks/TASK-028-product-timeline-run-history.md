# TASK-028: Product Timeline And Run History

## Status

completed

## Source

`repo/audits/PRODUCT-EXPERIENCE-ACCEPTANCE.md` next phase target: productized
research flow.

## Goal

Add a user-facing timeline that connects daily advice, market snapshots,
prediction runs, backtest scores, and task health into a continuous research
history.

## Acceptance

- Before implementation, inspect existing WebUI, daily workflow, task log,
  advice, market snapshot, and backtest capabilities; document the planned data
  flow in the task notes.
- WebUI exposes a timeline entry point from dashboard or navigation.
- Timeline shows at least the latest three advice/run dates when data exists.
- Each timeline row includes date, advice status, market snapshot state,
  prediction/backtest evidence, task health, and major changes from the
  previous run.
- Timeline rows link to the relevant advice, prediction, backtest, asset, or
  log details.
- Missing stages are shown as product states with impact and recovery hints,
  not silent blanks.
- `ARCHITECTURE.md` and `CODE_INDEX.md` are updated if new routes, view models,
  helpers, or data-flow ownership are introduced.
- Tests and a WebUI restart/smoke check validate the route or dashboard module.

## Implementation Notes

Data flow:

- Timeline dates are derived from stored `daily_advice`, `market_snapshots`,
  `model_predictions`, `backtest_runs`, and `task_logs`.
- Each date is rendered as a WebUI view model with advice status, market
  snapshot state, prediction coverage, backtest evidence, task-log health, and
  a change summary versus the previous timeline date.
- Missing advice, market, prediction, backtest, or task-log stages are shown as
  explicit product states with recovery hints instead of blank cells.
- Timeline rows link back to `/advice`, `/predictions`, `/backtests`, and
  `/logs` so the user can inspect source evidence.

Changed files:

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

Verification:

- `python3 -m pytest` passed with 66 tests.
- WebUI route `/timeline` was smoke checked after restart.
