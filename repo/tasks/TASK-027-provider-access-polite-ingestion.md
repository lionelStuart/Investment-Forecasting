# TASK-027: Provider Access Polite Ingestion

## Status

pending

## Source

User requirement from 2026-05-23: using residential broadband to access
AKShare-backed public data may carry temporary ban or anti-bot risk, especially
for large, repeated, or concurrent downloads.

## Goal

Make provider ingestion polite and residential-network friendly by default, so
future data expansion minimizes ban/limit risk while preserving reliable local
research workflows.

## Required Context

- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/data/ingestion.py`
- `src/investment_forecasting/workflows/daily.py`
- `repo/tasks/TASK-015-data-quality-retry-cache.md`
- `repo/tasks/TASK-025-provider-expansion-tushare.md`

## Modify Scope

- Provider rate-limit configuration.
- Per-request delay or jitter between provider calls.
- Backoff behavior for likely throttling, empty responses, and transient
  network failures.
- Local cache and incremental update policy.
- Task-log and data-quality metadata that records throttling/ban-risk signals.

## Forbidden

- Do not add concurrent bulk downloads for AKShare by default.
- Do not repeatedly re-download full historical datasets when local cached data
  can be incrementally updated.
- Do not treat proxy retry as a way to bypass provider limits.
- Do not require paid provider credentials for the default workflow.

## Acceptance

- Default ingestion is sequential and rate-limited with configurable minimum
  delay and optional jitter.
- Bulk universe refreshes use incremental date ranges when prior local data
  exists.
- Retry/backoff distinguishes ordinary network failures from likely provider
  throttling or anti-bot responses where observable.
- Task logs record provider, request counts, delay settings, retries, and any
  throttling/ban-risk warnings.
- Documentation warns that residential broadband is suitable for low-frequency
  personal research, but large concurrent or repeated full-history downloads can
  trigger temporary IP limits.

## Test Plan

- Unit tests for rate-limit configuration and delay/backoff decisions.
- Ingestion tests proving incremental updates avoid unnecessary full-history
  downloads.
- Simulated provider throttling/empty-response tests that produce actionable
  task-log warnings.
