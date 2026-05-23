# Status

## Current Focus

- Data coverage has been expanded and ingestion channels have been hardened.
  The first productized research-flow slice is now in place through the run
  timeline, category navigation, and fund screening presets. The expert
  committee foundation has started with a persisted three-expert roster,
  structured styles, focus weights, risk limits, allowed asset categories,
  cash buffers, review cadence, lifecycle state, and one CNY 500,000 virtual
  portfolio per active expert. Experts can now produce one evidence-backed
  daily plan per date and simulate execution into those virtual portfolios.
  Expert scorecards, lifecycle reviews, retirement lessons, and replacement
  hiring are now persisted from virtual portfolio records. The expert
  committee is inspectable in WebUI through `/experts`, including active,
  probation, retired, plans, scorecards, reviews, and lessons. Expert roster,
  planning, portfolios, scoring, reviews, and lessons are now exposed to
  MCP/Agent workflows with task logs. Next iteration should return to product
  workbench polish (`TASK-031`/`TASK-032`/`TASK-033`/`TASK-035`) or start the
  separate phone communication phase. The next newly requested phase is local Mac-to-phone
  communication through an adapter layer, with iMessage as the first outbound
  channel.

## Last Completed

- `TASK-001`: Established Python project skeleton, SQLite schema, database
  initialization command, and baseline tests.
- `TASK-002`: Added AKShare MVP ingestion for one index, one ETF, and one public
  fund with normalized rows, ETF fallback, task logs, and tests.
- `TASK-003`: Added reproducible feature/risk metric calculation from stored
  prices with `features_v1` persistence, missing-gap validation, task logs, and
  tests.
- `TASK-004`: Added `baseline_mean_v1` forecasts, rolling backtests, score
  persistence, CLI commands, and future-leakage tests.
- `TASK-005`: Added daily advice generation from stored predictions/backtests,
  three risk-profile variants, allocation triggers, evidence links, compliance
  guardrails, task logs, CLI command, and tests.
- `TASK-006`: Added MCP-compatible tool schemas and JSON-callable tool
  implementations for asset, history, metrics, snapshot, forecast, backtest,
  and daily advice workflows.
- `TASK-007`: Added deterministic daily workflow command, success/failure task
  logs, dry-run tests, and active Codex automation for daily 08:00.
- `TASK-008`: Added local WebUI workbench with dashboard, data, funds,
  predictions, backtests, advice, and task-log pages, plus browser verification.
- `TASK-009`: Added baseline candidate calibration reports comparing
  `baseline_mean_v1` and `momentum_last_return_v1` across historical windows.
- `TASK-010`: Audited README MVP requirements against implementation evidence
  and created follow-up tasks for remaining material gaps.
- `TASK-011`: Added official MCP Python SDK stdio transport over the existing
  tool registry with transport smoke tests.
- `TASK-012`: Expanded the AKShare universe to 10 representative assets across
  indices, ETFs, public funds, and one individual A-share.
- `TASK-013`: Added AKShare fund info ingestion, persistence, MCP output, and
  WebUI fund metadata for tracked public funds.
- `TASK-014`: Added stored market environment snapshots, daily workflow
  integration, MCP/WebUI output, and advice evidence links.
- `TASK-015`: Added provider retry behavior and per-asset ingestion quality
  reports with warning metadata.
- `TASK-016`: Added real 沪深300 benchmark-relative backtest scoring and
  matured daily advice outcome scoring.
- `TASK-017`: Added historical calibration corpus workflow and verified a
  2023-2025 expanded-universe calibration report.
- `TASK-018`: Added FRED macro observation ingestion, persistence, CLI command,
  and market snapshot evidence integration.
- `TASK-019`: Added daily-advice history selection and focus-asset links to
  product data pages.
- `TASK-020`: Added dashboard database status and restart-time row-count health
  output.
- `TASK-021`: Added persisted user risk preferences, CLI/WebUI settings, and
  preference-aware daily advice generation.
- `TASK-027`: Expanded default data coverage to 63 assets and hardened
  research/full ingestion controls.
- `TASK-034`: Measured the AKShare full candidate universe at 23,952 assets,
  added resumable balanced full-ingestion batches, skipped existing assets,
  isolated fund detail and feature-history failures, and expanded the default
  database to 476 assets / 153,175 price rows.
- `TASK-028`: Added a WebUI research timeline that connects advice, market
  snapshots, prediction coverage, backtest evidence, task health, source links,
  and missing-stage recovery hints.
- `TASK-029`: Added product category navigation, dashboard category drill-in,
  category summaries, and a selected-asset-first `/data` view with the raw
  asset list moved into secondary technical details.
- `TASK-030`: Upgraded `/funds` into a practical screening workflow with
  metadata/metric filters, conservative/balanced/aggressive presets,
  suitability explanations, and product-language missing metadata states.
- `TASK-036`: Added persisted expert roster architecture with the three
  default active experts, structured configuration, lifecycle state,
  idempotent initialization, CLI inspection, and tests.
- `TASK-037`: Added shared simulated portfolio accounting and created one CNY
  500,000 virtual portfolio per active expert with cash ledger, positions,
  transactions, no-trade/unfilled records, and stored-price valuation.
- `TASK-038`: Added expert daily planning and simulated execution from stored
  predictions, features, market snapshots, focus weights, risk checks, and
  portfolio cash, with idempotent one-plan-per-expert-per-day persistence.
- `TASK-039`: Added expert scorecards, lifecycle reviews, structured lessons,
  warning/probation/retirement progression, and style-diverse replacement
  hiring that restores three active experts.
- `TASK-040`: Added `/experts` WebUI for expert roster, virtual portfolios,
  current capital/cash/return/drawdown/score, latest plans, lifecycle reviews,
  retired/probation states, equity/benchmark comparison, lessons, and
  secondary technical details.
- `TASK-041`: Added expert MCP/Agent tools for roster, plans, virtual
  portfolios, scoring, scorecards/reviews, lessons, daily planning, and
  scoring execution with task logs.

## Current Constraints

- MCP stdio transport is implemented with the official Python SDK. SSE or
  streamable HTTP can be enabled later if needed.
- The core local MVP loop is implemented and verified, including live FRED
  macro ingestion after adding a portable `certifi` CA bundle.
- MVP should start with AKShare and SQLite.
- Investment advice must remain research support and must include risk and
  uncertainty.
- Residential broadband access to AKShare-backed public data should be treated
  as low-frequency personal research only; future ingestion work must minimize
  temporary ban or anti-bot risk with rate limits, jitter, incremental updates,
  and clear throttling diagnostics.

## Open Issues

- Current UI is still table/list heavy despite expanded coverage: timeline,
  category-first screening, asset-level forecast grouping, and consistent
  red/green market semantics are not yet implemented.
- Raw tables, evidence JSON, saved-setting fields, and task logs are still
  primary on several pages (`/data`, `/funds`, `/predictions`, `/backtests`,
  `/advice`, `/settings`, `/logs`) before users see decision summaries.
- Daily 08:00 scheduling must account for China market data availability: the
  morning run mainly uses previous trading-day data.
- Expert committee planning/execution work must reuse the new persisted expert
  roster plus existing advice, forecast, backtest, scoring, portfolio, daily
  workflow, MCP, and WebUI capabilities instead of creating a parallel
  investment engine.
- Phone communication must be opt-in, allowlisted, auditable, and safe.
  iMessage is the first adapter, but investment, expert, workflow, and WebUI
  logic must call a channel-neutral communication service instead of directly
  invoking Messages or AppleScript.

## Next Steps

1. `TASK-031`: Add red/green market visual semantics.
2. `TASK-032`: Add asset-level prediction cards.
3. `TASK-033`: Add dashboard daily brief and run-health summary.
4. `TASK-035`: Apply progressive disclosure to raw tables, evidence JSON,
   saved-setting fields, and operational logs across table-heavy pages.
5. `TASK-022`: Add simulated portfolio tracking after the research flow is more
   productized.
6. `TASK-042`: Add communication adapter architecture and outbound message
   persistence.
7. `TASK-043`: Implement the first iMessage outbound adapter for allowlisted
   Mac-to-phone notifications.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-041` expert Agent workflow and MCP integration.
- Judge: `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py`.
- Score: 92/100
- Reasoning: Expert committee operations are now available through structured
  MCP tools and the FastMCP stdio server. Agents can inspect experts, plans,
  virtual portfolios, scorecards, reviews, and lessons, and can trigger expert
  planning/scoring without direct SQL edits. Planning and scoring write task
  logs. Remaining expert polish is richer WebUI charts and future automation
  scheduling, not core accessibility.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-040` expert committee WebUI.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 91/100
- Reasoning: `/experts` now makes expert status inspectable without reading raw
  tables first: lifecycle state, style, current virtual capital, cash, return,
  drawdown, score, latest plan/execution, review rationale, lessons, and
  technical score/review details are all visible. Remaining expert integration
  belongs to MCP/Agent workflow exposure.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-039` expert scoring, retirement, and replacement hiring.
- Judge: `python3 -m pytest tests/test_expert_scoring.py tests/test_experts.py
  tests/test_portfolio.py tests/test_db.py` and real database `experts score`
  smoke run.
- Score: 90/100
- Reasoning: Scorecards are now reproducible from persisted virtual valuations,
  transactions, and plans. Lifecycle review requires maturity, moves weak
  experts through warn/probation before retirement, writes structured lessons,
  and creates a style-diverse replacement with a virtual portfolio to restore
  three active experts. The live database currently has immature scorecards
  because no valuation history exists yet, so no expert is punished.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-038` expert daily planning and simulated execution.
- Judge: Expert planning tests and real database CLI execution for
  `experts run-plans --date 2026-05-23`.
- Score: 90/100
- Reasoning: Each active expert can now produce at most one stored plan per
  date, with action/no-trade, target asset/amount, rationale, evidence links,
  risk checks, warnings, and execution status. Executions reuse virtual
  portfolio accounting, so buys update cash/positions and no-trade decisions
  are persisted. Remaining maturity is scoring, lifecycle review, and WebUI.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-037` expert virtual portfolio foundation.
- Judge: `python3 -m pytest tests/test_portfolio.py tests/test_db.py` and
  real database CLI bootstrap for expert portfolios.
- Score: 91/100
- Reasoning: Each active expert now has an independent CNY 500,000 virtual
  portfolio on the shared simulated-accounting path. The system can record
  filled buy/sell orders, no-trade decisions, unfilled missing-price orders,
  cash ledger entries, positions, and daily valuations from stored prices.
  Remaining value comes from `TASK-038` daily expert planning and execution.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-036` expert architecture and roster model.
- Judge: Expert spec/task audit, `python3 -m pytest tests/test_experts.py
  tests/test_db.py`, and CLI smoke initialization.
- Score: 92/100
- Reasoning: The expert committee is now grounded in persisted structured
  records instead of UI-only personas. Three active experts can be initialized
  idempotently and queried by lifecycle state. Remaining expert value depends
  on `TASK-037` virtual portfolios and later plan/execution/scoring loops.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-030` fund screening filters and presets.
- Judge: `python3 -m pytest`, WebUI `/funds` smoke check, and route/content
  review.
- Score: 93/100
- Reasoning: The fund page now supports practical screening by metadata,
  risk/return metrics, fee completeness, market state, and risk-profile
  presets. Results explain why a fund appears and whether data is incomplete,
  reducing raw-table friction. Remaining product polish is visual semantics and
  asset-level forecast presentation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-029` product category navigation.
- Judge: `python3 -m pytest`, WebUI route smoke checks, and route/content
  review.
- Score: 92/100
- Reasoning: The workbench now supports product-first browsing through
  user-facing categories, dashboard drill-in, category summaries, peer links,
  and a `/data` page that starts with selected-asset context instead of raw rows.
  Remaining category depth belongs in `TASK-030`, where fund filters and presets
  should make the category views more actionable.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-028` product timeline and run history.
- Judge: `python3 -m pytest`, WebUI route smoke check, and route/content review.
- Score: 93/100
- Reasoning: The workbench now has a dedicated research timeline and dashboard
  entry point that connect advice, market snapshots, predictions, backtests, and
  task health into date-based run history. Missing stages have explicit recovery
  hints and rows link back to source evidence pages. Remaining polish belongs to
  the next productization tasks: categories, filters, market semantics, and
  asset-level forecast cards.

## Round Evaluation

- Date: 2026-05-23
- Scope: Product progress review and next-phase planning after `TASK-021` and
  `TASK-027`.
- Judge: Browser inspection of dashboard, settings, funds, predictions, advice,
  and logs plus review of `repo/STATUS.md`, `repo/INDEX.md`, and product
  acceptance documentation.
- Score: 88/100
- Reasoning: The product now has broader data, fresher predictions, market
  snapshots, active risk preferences, and preference-aware advice. The next
  bottleneck is product experience: the UI still relies on raw tables and
  repeated lists, so the next phase should prioritize timeline, categories,
  filters, market color semantics, asset-level prediction grouping, and
  dashboard/run-health summaries before adding deeper portfolio optimization.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-027` data expansion and channel hardening.
- Judge: `python3 -m pytest`, live AKShare/FRED ingestion, row-count audit, and
  WebUI restart health output.
- Score: 94/100
- Reasoning: The default database now has materially broader coverage and all
  core derived artifacts were recomputed. `research` ingestion can continue on
  individual failures, and `full` ingestion can cap per type to avoid one asset
  class dominating a staged pull. Remaining depth comes from more provider
  diversity and portfolio-level evaluation.
6. `TASK-027`: Add polite provider access controls for residential-network-safe
   ingestion.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-021` user risk preferences.
- Judge: `python3 -m pytest`, CLI preference smoke test, and WebUI settings
  rendering.
- Score: 92/100
- Reasoning: The roadmap backlog is now translated into concrete tasks, and the
  first personalization task is implemented end to end: persistence, CLI,
  WebUI, and advice generation all use the active preference. Remaining product
  depth comes from portfolio tracking and allocation optimization.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-020` data status and service health.
- Judge: `python3 -m pytest`, `scripts/restart_web.sh`, and HTTP check of
  dashboard content.
- Score: 93/100
- Reasoning: The dashboard now shows the active database path, key row counts,
  latest data dates, and empty-database guidance. The restart script prints
  row-count health after the service is up, making DB_PATH/data mixups visible
  immediately.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-019` advice history and product links.
- Judge: `python3 -m pytest` plus HTTP smoke against local WebUI route
  `/advice`.
- Score: 94/100
- Reasoning: The WebUI now supports selecting historical advice by id, shows a
  history table, and links focus asset cards to `/data?asset_id=...` for the
  corresponding product curve/history page. Tests cover both behaviors and an
  HTTP smoke followed a real focus link to a product page.

## Round Evaluation

- Date: 2026-05-23
- Scope: Project memory bootstrap only.
- Judge: Manual self-check because no independent LLM judge tool is configured
  for this repo.
- Score: 86/100
- Reasoning: The repo now has goals, architecture, roadmap, specs, tasks,
  acceptance criteria, and write-back rules. The main remaining risk is that
  implementation commands and framework choices are intentionally deferred to
  `TASK-001`.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-001` Python skeleton and SQLite schema.
- Judge: `python3 -m pytest` plus manual inspection of the initialization
  command and schema constraints.
- Score: 90/100
- Reasoning: The repo now has install, database initialization, and test
  commands; all README/SPEC-001 core tables exist with primary keys and
  idempotent uniqueness constraints; tests cover schema creation and asset
  upsert/query. Remaining work belongs to `TASK-002`: AKShare adapters, tracked
  universe, provider failure logs, and normalized ingestion.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-002` AKShare MVP ingestion.
- Judge: `python3 -m pytest` plus live command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 91/100
- Reasoning: Ingestion now writes one index, one ETF, and one public fund into
  SQLite through normalized internal fields; duplicate writes are idempotent;
  provider failures write `task_logs`; ETF ingestion falls back from Eastmoney
  to Sina when needed. Remaining work belongs to `TASK-003`: derived features,
  risk metrics, and richer data quality checks.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-003` feature and risk metrics.
- Judge: `python3 -m pytest` plus live command
  `investment-forecasting features calculate --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 90/100
- Reasoning: Feature calculation now reads only stored SQLite prices, computes
  returns, volatility, drawdown, Sharpe, Calmar, win rate, momentum, and a
  simple market state where history permits, persists rows with `features_v1`,
  records task logs, rejects large missing-date gaps, and is idempotent. The
  remaining quant work belongs to `TASK-004`: baseline forecasts, rolling
  backtests, and score persistence.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-004` baseline forecasts, rolling backtests, and scoring.
- Judge: `python3 -m pytest` plus sample commands
  `investment-forecasting forecast run --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --horizons 5,20,60`
  and
  `investment-forecasting backtest run --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --horizons 1 --lookback-days 2`.
- Score: 89/100
- Reasoning: The system now writes latest baseline forecasts for 5/20/60 day
  horizons, records rolling backtest runs/results, stores direction/error/risk
  and overall scores, and has tests that explicitly verify no future rows enter
  prediction history. Remaining work belongs to `TASK-005`: converting
  structured forecasts and historical scores into daily advice with risk
  variants and compliance language.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-005` daily advice generator.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting advice generate --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --date 20260523`.
- Score: 90/100
- Reasoning: The system now generates a traceable `daily_advice` row from
  stored `model_predictions` and `backtest_runs`, includes aggressive,
  balanced, and conservative variants with allocation ranges and add/reduce
  triggers, records assumptions and warnings, rejects prohibited certainty
  language, and logs failures. Remaining work belongs to `TASK-006`: exposing
  these structured capabilities to AI through MCP tools.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-006` MCP-compatible tools.
- Judge: `python3 -m pytest` plus smoke commands
  `investment-forecasting mcp list-tools` and
  `investment-forecasting mcp call get_market_snapshot --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --args '{}'`.
- Score: 88/100
- Reasoning: The system now exposes all SPEC-004 MVP tool names with stable
  JSON schemas, service-backed implementations, structured success/error
  envelopes, and CLI calls that AI agents can consume. The full stdio/network
  MCP transport remains deferred to a thin wrapper over this registry. Remaining
  work belongs to `TASK-007`: daily Codex automation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-007` daily Codex automation.
- Judge: `python3 -m pytest`, smoke command
  `investment-forecasting daily run --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --date 20260523 --start-date 20240520 --end-date 20240522 --horizons 1 --lookback-days 2 --skip-ingest`,
  and Codex app automation creation result.
- Score: 90/100
- Reasoning: The system now has a deterministic `daily run` command that
  executes ingestion, feature calculation, forecasts, backtests, and advice
  generation, is safe to rerun against existing data, and records top-level
  success/failure task logs. Codex app automation
  `investment-forecasting-daily-run` is active for daily 08:00 local runs.
  Remaining work belongs to `TASK-008`: WebUI workbench.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-008` WebUI workbench.
- Judge: `python3 -m pytest`, local server smoke checks, and Playwright desktop
  and mobile screenshots.
- Score: 90/100
- Reasoning: The system now has a local workbench server with dashboard, data,
  funds, predictions, backtests, daily advice, and task-log pages. The UI
  surfaces risk, confidence, model versions, evidence, stale/missing states, and
  job failures without marketing framing. Playwright verified desktop and
  mobile rendering with no console errors or invalid layout boxes. Remaining
  work belongs to `TASK-009`: model calibration enhancements.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-009` model calibration enhancement.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting calibration run --db /tmp/investment_forecasting_calibration_smoke.sqlite3 --date 20260523 --horizons 2 --lookback-days 10`.
- Score: 88/100
- Reasoning: The system now records `model_calibration_reports` comparing
  simple candidate versions across available historical windows, includes
  out-of-sample scores, risk hit rate, return error, stability, promotion
  rationale, and an explainable promoted model version. No ML dependency was
  introduced. Further calibration quality requires a larger real historical
  universe and more market regimes.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-010` README completion audit and gap plan.
- Judge: Manual requirement-to-evidence audit plus `python3 -m pytest`.
- Score: 92/100
- Reasoning: The project now has an explicit audit mapping README requirements
  to current evidence, partial coverage, and missing work. Follow-up tasks
  `TASK-011` through `TASK-017` cover every material remaining gap identified
  by the audit. The overall README goal remains active because those gaps are
  not yet closed.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-011` MCP stdio transport.
- Judge: `python3 -m pytest` including a stdio MCP client smoke test.
- Score: 92/100
- Reasoning: The project now uses the official MCP Python SDK to expose the
  existing eight tool registry entries through stdio transport. Tests verify
  `list_tools`, a read tool, a workflow tool, and structured error payloads
  through an actual MCP client/server subprocess. Remaining README gaps now
  move to `TASK-012`: broader AKShare universe coverage.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-012` broader AKShare universe.
- Judge: `python3 -m pytest` plus live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task012_expanded_fallback.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 91/100
- Reasoning: The tracked universe now covers representative indices, ETFs,
  public funds, and an individual A-share. Live smoke wrote 30 rows across 10
  assets and tests cover universe composition, stock normalization, and stock
  fallback. Remaining README data gaps are fund metadata, macro/environment,
  quality/retry, benchmark scoring, and broader historical calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-013` fund info ingestion.
- Judge: `python3 -m pytest` plus live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task013_fund_info.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 91/100
- Reasoning: The system now populates `fund_info` for tracked public funds,
  including fund type, manager, scale, fee proxy, benchmark/strategy/objective,
  and stage-return JSON where AKShare provides it. MCP fund metrics and the
  WebUI fund page surface the metadata. Remaining README gaps move to market
  environment data, reliability/quality, benchmark scoring, and larger
  calibration windows.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-014` market environment data.
- Judge: `python3 -m pytest` plus smoke commands over the expanded universe
  from 2024-04-01 through 2024-05-22.
- Score: 91/100
- Reasoning: The system now stores and surfaces market environment proxies for
  index trend, breadth, liquidity heat, stock-bond comparison, and sentiment.
  The daily workflow calculates snapshots, MCP/WebUI expose them, and daily
  advice links to the snapshot evidence. Remaining README gaps are provider
  quality/retry/cache, benchmark/advice outcome scoring, and larger historical
  calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-015` data quality, retry, and cache metadata.
- Judge: `python3 -m pytest` plus live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task015_quality.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 90/100
- Reasoning: Provider calls now use deterministic retry, existing fallbacks
  remain available, ingestion writes per-asset data-quality reports, and
  workflow/task logs retain partial progress and actionable errors. Full
  point-in-time rollback snapshots remain future enhancement, but MVP
  inspectability and recoverability are materially improved. Remaining README
  gaps are benchmark/advice outcome scoring and larger historical calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-016` benchmark and advice outcome scoring.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting advice score-outcomes --db /tmp/investment_forecasting_task014_market.sqlite3 --horizon-days 5`.
- Score: 91/100
- Reasoning: Backtests now use real stored 沪深300 benchmark returns when
  aligned, and matured advice records can be scored without future leakage once
  outcome observations exist. Remaining README gap is larger multi-regime
  historical calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-017` historical calibration corpus.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting calibration corpus --db /tmp/investment_forecasting_task017_corpus.sqlite3 --start-date 20230101 --end-date 20251231 --date 20260523 --horizons 5,20,60 --lookback-days 60 --skip-ingest`.
- Score: 90/100
- Reasoning: The system now supports an end-to-end historical calibration
  corpus workflow and produced a real three-window 2023-2025 expanded-universe
  calibration report. Benchmark excess and drawdown control are included in
  aggregate model comparison metrics. The only remaining scope question is
  whether README's macro-data wording requires true external macro series for
  the current MVP or can be satisfied by the implemented market-proxy snapshot.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-018` external macro data provider.
- Judge: `python3 -m pytest` plus live FRED smoke command
  `investment-forecasting ingest macro --db /tmp/investment_forecasting_task018_macro.sqlite3 --start-date 20240520 --end-date 20240524 --series DGS10,T10YIE`.
- Score: 92/100
- Reasoning: The repo now has idempotent `macro_observations` persistence, a
  FRED CSV provider, CLI ingestion, market snapshot evidence integration, and
  tests covering ingestion and snapshot behavior. Live FRED validation wrote 10
  observations after the provider was updated to use `certifi` for TLS CA
  resolution. Remaining enhancements are broader Chinese macro coverage and
  richer fund-peer benchmarks.
