# TASK-079: Model Promotion And Demotion Governance

## Status

completed

## Purpose

Prevent model sprawl and premature promotion by adding explicit governance for
when a model can influence Jarvis primary conclusions, remain contextual, or be
demoted.

## Scope

- Define persisted or documented model states:
  - baseline;
  - candidate;
  - contextual;
  - promoted;
  - degraded;
  - retired.
- Add promotion checks using validation metrics:
  - beats baseline across windows;
  - positive/stable Rank IC;
  - positive bucket spread;
  - acceptable drawdown/downside behavior;
  - asset-type and same-category visibility;
  - not degraded;
  - evidence IDs present.
- Add demotion checks for stale, degraded, or unstable performance.
- Surface model status in 证据 and Jarvis evidence summaries.

## Non-Scope

- No automatic production deployment of new models without product review.
- No ensemble promotion unless candidate evidence is stable.
- No new UI primary entry.

## Files Likely To Change

- `src/investment_forecasting/quant/monitoring.py`
- `src/investment_forecasting/quant/calibration.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/web/app.py`
- `src/investment_forecasting/mcp/tools.py`
- `repo/STATUS.md`
- `repo/CODE_INDEX.md`
- `tests/test_monitoring.py`
- `tests/test_calibration.py`
- `tests/test_web_app.py`
- `tests/test_mcp_tools.py`

## Implementation Checklist

- Reuse existing model monitoring reports where possible.
- Add model-state summary helper.
- Add a product-review stop: promoted model changes require explicit status
  update and evidence summary.

## Acceptance Criteria

- No model can be marked promoted without stored validation evidence.
- Jarvis can distinguish promoted, candidate, contextual, degraded, and retired
  models.
- The phase ends with a documented decision on which model remains primary.

## Test Plan

- `python3 -m pytest tests/test_monitoring.py tests/test_calibration.py tests/test_web_app.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-078`

## Completion Notes

- Added explicit model governance states:
  `baseline`, `candidate`, `contextual`, `promoted`, `degraded`, and
  `retired`.
- Calibration now writes a `governance` block into `metrics_json`, evaluates
  promotion gates against `baseline_mean_v1`, and keeps `baseline_mean_v1` as
  primary unless a candidate passes quantitative gates and product review.
- Monitoring now writes a per-model governance summary into
  `model_monitoring_reports.metrics_json`, including governance state,
  Jarvis-primary eligibility, promotion blockers, demotion reasons, and product
  review requirement.
- MCP market snapshot exposes `model_governance` so agents can see primary
  decision and model states.
- `/backtests` / 证据 model-health cards now show governance state and whether
  each model can influence Jarvis primary conclusions.
- Phase decision: `baseline_mean_v1` remains the primary model. Current local
  monitoring marks `momentum_reversal_v1` and `risk_adjusted_factor_v1` as
  `degraded`, so they remain contextual/watch-only evidence.

## Verification

- `python3 -m pytest tests/test_monitoring.py tests/test_calibration.py tests/test_web_app.py tests/test_mcp_tools.py -q`
- `python3 -m py_compile src/investment_forecasting/quant/calibration.py src/investment_forecasting/quant/monitoring.py src/investment_forecasting/mcp/tools.py src/investment_forecasting/web/app.py`
- Local SQLite monitoring refresh:
  `investment-forecasting monitoring run --db data/investment_forecasting.sqlite3 --date 20260524`
  produced states `{baseline_mean_v1: baseline, momentum_reversal_v1:
  degraded, risk_adjusted_factor_v1: degraded}`.
