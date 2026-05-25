# TASK-023: Target Volatility Allocation

## Status

completed

## Source

Updated `ROADMAP.md` backlog theme: portfolio optimization and
target-volatility allocation.

## Goal

Generate target-volatility allocation proposals bounded by active user
preferences and backed by stored risk metrics.

Expert committee tasks may reuse this allocation logic as one possible expert
style, but expert-specific plans must still record their own evidence, risk
checks, and virtual execution.

## Acceptance

- Allocation proposals use stored volatility/drawdown data.
- Proposals respect user max-equity and min-cash settings.
- Daily advice can reference the allocation proposal as structured evidence.

## Implementation Notes

- Added `investment_forecasting.advice.allocation` to build target-volatility
  proposals from stored `features_daily` risk metrics.
- Proposals estimate annualized volatility from `volatility_20d`, apply a
  drawdown penalty from `max_drawdown_60d`, and classify selected assets into
  equity/fixed-income/cash buckets using asset and fund metadata.
- Daily advice now embeds `target_volatility` in `allocation_json`, records the
  source feature IDs in advice evidence, and adds a short assumption note when
  the proposal is ready.
- The proposal respects active user `max_equity_pct` and `min_cash_pct`; if
  risk metrics are missing it fails closed with low/no equity exposure.
- `/advice` now shows a human-readable "目标波动率配置" panel and a
  "波动率证据" chip before the raw advice JSON.

## Verification

- `python3 -m pytest tests/test_advice.py tests/test_web_app.py`
- `python3 -m pytest`
- `investment-forecasting advice generate --db data/investment_forecasting.sqlite3 --date 20260523`
- `scripts/restart_web.sh`
