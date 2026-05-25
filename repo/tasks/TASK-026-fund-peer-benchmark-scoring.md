# TASK-026: Fund Peer Benchmark Scoring

## Status

completed

## Source

Updated README target: compare against 偏股基金指数 or peer averages.

## Goal

Extend benchmark-relative scoring beyond 沪深300 to include fund peer or
偏股基金 benchmark proxies where free data is available.

## Acceptance

- Fund advice/backtests can compare against a relevant peer benchmark.
- Benchmark source and fallback behavior are explicit.
- Advice outcome scoring stores the chosen benchmark identity.

## Implementation Notes

- Added shared benchmark selection in `investment_forecasting.quant.benchmarks`.
- Fund assets first compare against an equal-weight peer average for funds in
  the same coarse bucket, such as equity/偏股, hybrid, bond, cash, index, QDII,
  or FOF.
- When a fund peer sample has fewer than two peers, the selector explicitly
  falls back to stored 沪深300 history; if that is unavailable, the benchmark is
  marked unavailable with a fallback reason.
- Backtest result `details_json` now records benchmark return, identity,
  source, benchmark asset id, peer count, and fallback reason.
- Advice outcome scoring now writes `benchmark_identity` and
  `benchmark_source` columns, while `details_json` records the aggregate
  benchmark selection details.
- Legacy SQLite databases are upgraded in `init_db` with the new advice outcome
  benchmark identity/source columns.

## Verification

- `python3 -m pytest tests/test_backtest.py tests/test_advice_scoring.py tests/test_db.py`
