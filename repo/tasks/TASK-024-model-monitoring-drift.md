# TASK-024: Model Monitoring And Drift

## Status

completed

## Source

Updated `ROADMAP.md` backlog theme: model monitoring and drift detection.

## Goal

Track model score drift, stale inputs, and model-version health over rolling
windows.

## Acceptance

- Monitoring reports summarize prediction score, risk score, benchmark excess,
  and data staleness by model version.
- WebUI surfaces degraded model health.
- Daily workflow writes monitoring task logs.

## Implementation Notes

- Added `model_monitoring_reports` persistence for per-date/per-model health
  status, latest prediction/backtest dates, staleness, prediction score, risk
  score, benchmark excess, overall score, score drift, metrics, and warnings.
- Added `investment_forecasting.quant.monitoring` with
  `run_model_monitoring_report`, which summarizes latest backtest metrics by
  model version, compares against prior runs for score drift, and flags stale
  predictions/backtests or degraded scores.
- Added `investment-forecasting monitoring run --db ... --date ...`.
- Daily workflow now runs model monitoring after advice/outcome scoring and
  records `model_monitoring` task logs.
- `/backtests` now shows the latest monitoring cards before raw backtest rows,
  including degraded/warning states and staleness warnings.

## Verification

- `python3 -m pytest tests/test_monitoring.py tests/test_daily_workflow.py tests/test_web_app.py tests/test_db.py`
- `python3 -m pytest`
- `investment-forecasting monitoring run --db data/investment_forecasting.sqlite3 --date 20260523`
- `scripts/restart_web.sh`
