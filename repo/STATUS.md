# Status

## Current Focus

- README MVP goal achieved for the representative local-first slice. Remaining
  work is enhancement backlog, not a blocker for the current goal.

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

## Current Constraints

- MCP stdio transport is implemented with the official Python SDK. SSE or
  streamable HTTP can be enabled later if needed.
- The core local MVP loop is implemented and verified, including live FRED
  macro ingestion after adding a portable `certifi` CA bundle.
- MVP should start with AKShare and SQLite.
- Investment advice must remain research support and must include risk and
  uncertainty.

## Open Issues

- The MVP tracked universe is intentionally representative, not exhaustive: 4
  indices, 3 ETFs, 2 public funds, and 1 individual A-share.
- Daily 08:00 scheduling must account for China market data availability: the
  morning run mainly uses previous trading-day data.

## Next Steps

1. Optional enhancement: add Chinese macro series when a stable free provider
   is selected.
2. Optional enhancement: add fund-peer or 偏股基金指数 benchmark scoring.
3. Optional enhancement: expand the tracked universe beyond the representative
   MVP assets.

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
