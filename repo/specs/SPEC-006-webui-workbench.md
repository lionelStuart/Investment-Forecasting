# SPEC-006: WebUI Workbench

## Status

draft

## Goal

Provide a local workbench UI for inspecting market state, data, funds,
predictions, backtests, daily advice, scores, risks, and task logs.

## Non-Goals

- Do not build a marketing landing page.
- Do not hide risk warnings behind decorative presentation.
- Do not allow UI-only model edits that are not stored or audited.

## Inputs

- Stored database records and service/API responses.
- Daily advice, prediction, backtest, and task-log outputs.

## Outputs

- Pages:
  - Dashboard
  - Data
  - Funds
  - Predictions
  - Backtests
  - Daily Advice
  - Task Logs

## Constraints

- UI should be dense, inspectable, and workbench-oriented.
- Visual claims must show supporting fields: date, source, model version,
  confidence, risk, and historical score.
- Advice display must preserve the aggressive/balanced/conservative distinction.
- Tables and charts should make stale or failed data visible.

## Error Cases

- Database has no records yet.
- Latest scheduled run failed.
- Backtest or prediction data is missing for selected asset.
- Browser cannot reach the local service.

## Acceptance

- User can see today's market state and advice summary on the dashboard.
- User can inspect historical price/NAV data and feature/risk metrics.
- User can inspect forecasts with probability, expected return, downside risk,
  and confidence.
- User can inspect backtest performance, max drawdown, benchmark comparison, and
  scores.
- User can inspect daily task logs and failure reasons.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-008-webui-workbench.md`

