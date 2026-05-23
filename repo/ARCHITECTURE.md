# Architecture

## System Summary

The MVP is a local-first Python system with SQLite persistence, structured data
services, quantitative analysis services, MCP tools for AI access, a scheduled
daily analysis workflow, and a WebUI workbench.

```text
Data sources
  -> data adapters
  -> cleaning, validation, and incremental updates
  -> SQLite persistence
  -> feature, forecast, backtest, and advice services
  -> MCP tools and scheduled daily job
  -> WebUI
```

## Boundaries

- Data adapters own vendor-specific field mapping and retry behavior.
- Persistence owns schemas, migrations, and database access.
- Quant services own indicators, forecasts, backtests, and scoring.
- Advice services own conversion of structured model outputs into risk-profile
  guidance.
- MCP tools expose JSON-oriented capabilities to AI agents.
- WebUI reads system outputs and does not invent model results.

## Invariants

- AI-generated prose must be downstream of structured data/model results.
- Forecasts must record model version, horizon, input window, confidence, and
  generated timestamp.
- Backtests must use only data available before each simulated prediction point.
- Daily advice must include aggressive, balanced, and conservative variants.
- Scheduled runs must write `task_logs` regardless of success or failure.

## Modules

### Data Sources

- Responsibility: Fetch A-share, index, ETF, public fund, macro, and sentiment
  data through provider adapters.
- Inputs: Provider APIs such as AKShare, later Tushare Pro or macro sources.
- Outputs: Normalized records ready for persistence.
- Forbidden Changes: Upper layers must not consume provider raw fields directly.

### Persistence

- Responsibility: SQLite schema, migrations, data access, and query helpers.
- Inputs: Normalized data, features, predictions, backtests, advice, logs.
- Outputs: Stable records for services, MCP, and WebUI.
- Forbidden Changes: Do not change table contracts without migration and tests.

### Quantitative Services

- Responsibility: Feature calculation, risk metrics, baseline forecasts,
  rolling backtests, and scoring.
- Inputs: Historical price/fund data and stored features.
- Outputs: Forecasts, backtest runs/results, risk metrics, scores.
- Forbidden Changes: Do not allow future leakage or unrecorded model versions.

### Advice Services

- Responsibility: Generate daily risk-aware guidance for aggressive, balanced,
  and conservative profiles.
- Inputs: Market snapshot, forecasts, backtests, risk metrics, historical scores.
- Outputs: Stored daily advice JSON and human-readable summaries.
- Forbidden Changes: Do not output advice without assumptions and risk warnings.

### MCP Service

- Responsibility: Expose structured tools for data retrieval, forecast,
  backtest, and daily advice workflows.
- Inputs: Tool arguments.
- Outputs: JSON-compatible results.
- Forbidden Changes: Do not return unstructured prose where clients need stable
  fields.

### Scheduler

- Responsibility: Trigger the daily 08:00 analysis workflow and persist logs.
- Inputs: Calendar schedule and service configuration.
- Outputs: Updated database records and task logs.
- Forbidden Changes: Do not hide failures or skip logging.

### WebUI

- Responsibility: Display dashboard, data, funds, predictions, backtests, daily
  advice, and task logs.
- Inputs: API/service/database outputs.
- Outputs: Workbench views for inspection.
- Forbidden Changes: Do not present model outputs as certainty.

## External Interfaces

- AKShare Python APIs for MVP market and fund data.
- SQLite file/database for local persistence.
- MCP server tools for AI agent integration.
- Codex automation for daily 08:00 workflow.
- Web browser for the local WebUI.

