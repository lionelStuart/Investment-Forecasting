# Roadmap

## Milestones

### M0: Project Memory Bootstrap

- Scope: Create gstack project-system files, specs, tasks, and initial status.
- Exit Criteria: Agents can start from `AGENT.md`/`repo/AGENTS.md`, find the
  active task, and follow specs with acceptance criteria.

### M1: Local Data Foundation

- Scope: Python project skeleton, SQLite schema, migrations, repository layer,
  AKShare data ingestion, cache/retry, and data quality checks.
- Exit Criteria: A repeatable command initializes SQLite and imports a small
  tracked universe of indices, ETFs, and funds with test coverage.

### M2: Quantitative Baseline

- Scope: Feature calculation, risk metrics, baseline forecasts, rolling
  backtests, and prediction/advice scoring.
- Exit Criteria: The system can produce reproducible 5/20/60-day baseline
  forecasts and historical scores without future leakage.

### M3: AI Integration And Daily Advice

- Scope: MCP tools, daily advice generator, daily 08:00 Codex automation, and
  task logs.
- Exit Criteria: AI agents can call MCP tools, trigger advice generation, and
  retrieve stored daily advice with risk-profile variants.

### M4: WebUI Workbench

- Scope: Dashboard, data, fund, prediction, backtest, daily advice, and task log
  views.
- Exit Criteria: A user can inspect current advice, supporting data, historical
  scores, and job status in the browser.

### M5: Model Calibration Enhancements

- Scope: Multi-period historical calibration, model version comparisons, and
  optional machine-learning baselines.
- Exit Criteria: More complex models must demonstrate sample-out improvement or
  better risk control than simple baselines.

## Backlog Themes

- Tushare Pro enhancement provider.
- Macro and overseas indicators.
- Portfolio optimization and target-volatility allocation.
- Simulated portfolio tracking.
- User risk profiles and investment horizon settings.
- Model monitoring and drift detection.

