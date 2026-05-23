# TASK-033: Dashboard Brief And Run Health

## Status

pending

## Source

`repo/audits/PRODUCT-EXPERIENCE-ACCEPTANCE.md` next phase target: dashboard
daily brief and operational health.

## Goal

Add a dashboard daily brief and grouped run-health summary so users can quickly
understand today's stance and whether the system is reliable.

## Acceptance

- Before implementation, inspect existing dashboard, advice summary, risk
  preference, task logs, and restart health output. Reuse existing status and
  formatting helpers where practical.
- Dashboard includes a daily brief with stance, three reasons, and one watch
  condition.
- Brief uses Chinese product language instead of raw internal labels where
  practical.
- Run-health summary groups ingest, features, market snapshot, forecast,
  backtest, advice, and monitoring stages when data exists.
- Failed or missing stages show impact and recovery hints.
- Existing risk preference settings remain visible and continue to constrain
  advice.
- `ARCHITECTURE.md` and `CODE_INDEX.md` are updated if dashboard view-model,
  run-health ownership, or reusable product-experience helpers are introduced.
- Tests and WebUI restart/smoke check validate the dashboard brief and run
  health section.
