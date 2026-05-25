# SPEC-003: Daily Advice Generation

## Status

draft

## Goal

Generate daily research-oriented investment guidance for aggressive, balanced,
and conservative risk profiles using stored data, forecasts, backtests, and risk
metrics.

## Non-Goals

- Do not produce direct buy/sell orders.
- Do not omit assumptions, uncertainty, or risk boundaries.
- Do not make capital protection, guaranteed return, or certain-profit claims.

## Inputs

- Market snapshot and risk state.
- Baseline forecasts and confidence scores.
- Backtest performance and historical advice scores.
- Capital-flow observations when available, treated as liquidity/crowding
  evidence rather than a standalone trading signal.
- Stored price history and feature risk metrics for target-volatility and
  correlation risk-budget evidence.
- Risk-profile policy rules.
- Active user preference: risk profile, investment horizon, equity cap, and
  cash floor.

## Outputs

- `daily_advice` rows containing date, market view, risk level, key assumptions,
  risk factors, aggressive/balanced/conservative advice, suggested allocation
  ranges, trigger conditions, source prediction IDs, and score fields.
- Matured `advice_outcome_scores` rows containing realized return, benchmark
  return/excess, and the chosen benchmark identity/source.

## Constraints

- Advice must be traceable to structured model and backtest records.
- Advice must distinguish previous trading-day data from current-day live data.
- Each risk profile must include allocation range, risk warning, and conditions
  for adding/reducing exposure.
- Active user preference constraints must be persisted and traceable in advice
  evidence when present.
- Allocation evidence must keep target-volatility and correlation risk-budget
  calculations traceable to stored features and prices.
- The natural-language summary is secondary to stored structured fields.

## Error Cases

- Forecast data is missing for a required benchmark or tracked asset.
- Backtest quality is below a configured threshold.
- Data is stale or the latest provider update failed.
- Risk profile rules produce contradictory allocation ranges.

## Acceptance

- `generate_daily_advice` can create a complete daily record from stored data.
- Advice contains aggressive, balanced, and conservative variants.
- Advice includes assumptions, confidence, risk factors, and source model links.
- Advice records capital-flow evidence IDs and a bounded capital-flow summary
  when observations are available.
- Advice applies active user horizon and allocation constraints when configured.
- Advice records target-volatility and correlation risk-budget evidence when
  enough stored risk/price history exists, with explicit insufficient-data
  statuses otherwise.
- Advice outcome scoring records which benchmark source was used, including
  fund peer averages and fallback behavior where relevant.
- Compliance guardrails reject or flag prohibited certainty language.
- Advice generation failure writes `task_logs`.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-005-daily-advice-generator.md`
