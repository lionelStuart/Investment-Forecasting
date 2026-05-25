# TASK-088: Provider Rate Limit, Backoff, And Request Budgets

## Status

completed

## Purpose

Protect AKShare/Tushare and other provider interfaces from hourly scheduled
load by centralizing delay, jitter, request caps, error classification, and
backoff state.

## Scope

- Add provider policy config for concurrency, min delay, jitter, hourly/daily
  request caps, and retry limits.
- Persist provider backoff state and failure counters.
- Detect likely throttling, repeated empty suspicious responses, network
  failures, and permission failures.
- Defer due jobs when provider backoff is active.
- Include provider request counts and defer reasons in scheduler runs and task
  logs.

## Non-Scope

- No proxy rotation or anti-bot bypass.
- No aggressive retry loops.
- No hidden provider calls outside the scheduler policy.

## Files Likely To Change

- `src/investment_forecasting/scheduler/`
- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/providers/tushare_provider.py`
- `src/investment_forecasting/data/ingestion.py`
- `tests/test_scheduler.py`
- `tests/test_akshare_ingestion.py`
- `tests/test_tushare_provider.py`

## Acceptance Criteria

- Provider policy enforces delay/jitter and request caps in tests.
- A likely throttling response moves provider into backoff.
- Jobs due during backoff are deferred and logged, not retried aggressively.
- Full refresh commands are explicitly manual and not scheduled by default.

## Test Plan

- `python3 -m pytest tests/test_scheduler.py tests/test_akshare_ingestion.py tests/test_tushare_provider.py -q`

## Depends On

- `TASK-087`

## Implementation Notes

- Added provider policies for request caps, hourly/daily budgets, min delay,
  jitter, and backoff windows in scheduler job definitions.
- Added central scheduler checks that defer provider-backed jobs while backoff
  is active or request budgets are exhausted.
- Added `record_provider_failure` to classify likely throttling/network/proxy
  failures and persist exponential backoff state in `provider_rate_limits`.
- Scheduler runs and task logs include provider request counts and defer
  reasons.
- Tests cover throttling backoff, deferred due jobs, and budget/backoff status
  visibility.
