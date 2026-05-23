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

### M6: Productized Research Experience

- Scope: Timeline, daily brief, product category navigation, category-aware
  screening, red/green market semantics, asset-level prediction cards, and
  grouped run-health summaries.
- Exit Criteria: A user can follow the daily research flow from brief to
  timeline to product categories to evidence without scanning raw tables first.

### M7: Expert Committee Virtual Investing

- Scope: Three parallel virtual experts with distinct investment styles,
  initial capital, daily plans, simulated execution, portfolio valuation,
  scorecards, retirement reviews, lessons, replacement hiring, WebUI inspection,
  CLI/MCP operations, and task logs.
- Exit Criteria: A user can compare three active experts' plans, positions,
  returns, risk, scores, failures, lessons, and replacement decisions using
  persisted virtual portfolios and stored evidence.

### M8: Local Phone Communication

- Scope: Adapter-based local-to-phone communication from the Mac workbench,
  starting with iMessage outbound notifications, setup verification, delivery
  policies, message logs, daily/expert templates, WebUI/CLI inspection, and a
  future inbound-command safety design.
- Exit Criteria: The Mac can send opt-in, allowlisted, auditable iMessage
  notifications for daily research and expert events without coupling
  investment logic to a specific channel or breaking workflows when delivery
  fails.

## Backlog Themes

- Tushare Pro enhancement provider.
- Macro and overseas indicators.
- Portfolio optimization and target-volatility allocation.
- Simulated portfolio tracking.
- Expert committee virtual investing with expert styles, virtual execution,
  scoring, retirement, lessons, and replacement hiring.
- Local Mac to phone communication adapters, starting with iMessage.
- User risk profiles and investment horizon settings.
- Model monitoring and drift detection.
- Productized WebUI flow: timeline, category-first screening, red/green market
  semantics, and asset-level forecast cards.
- Provider access politeness: rate limits, jitter, incremental updates, and
  throttling diagnostics so residential broadband ingestion avoids unnecessary
  temporary ban or anti-bot risk.

## Development Goals From Current Roadmap

1. Personalization: persist active user risk preference and investment horizon,
   then apply them to daily advice and WebUI controls.
2. Productized Research Flow: add timeline, daily brief, product categories,
   fund filters, red/green market semantics, and asset-level prediction cards
   so expanded data becomes usable before adding more advanced portfolio logic.
3. Portfolio Tracking: store simulated portfolios, positions, transactions, and
   daily portfolio value so recommendations can be evaluated as a portfolio.
4. Allocation Engine: add target-volatility and risk-budget allocation proposals
   that remain bounded by user preference constraints.
5. Model Monitoring: track score drift, stale data, and model-version health
   across rolling windows.
6. Provider Expansion: add Tushare Pro and richer Chinese macro/fund-peer
   benchmarks when stable credentials/providers are available.
7. Polite Ingestion: make AKShare/default provider access sequential,
   rate-limited, cache-aware, and incremental before expanding download volume.
8. Expert Committee: build the persisted expert roster, virtual portfolios,
   daily plans, scoring/retirement/hiring loop, and WebUI/MCP inspection after
   the core productized research flow and portfolio simulation foundation are
   stable.
9. Local Phone Communication: add a channel-neutral communication service,
   iMessage adapter, safe message templates, WebUI/CLI setup inspection, and
   future inbound-command design.
