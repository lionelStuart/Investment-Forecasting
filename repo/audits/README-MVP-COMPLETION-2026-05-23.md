# README MVP Completion Audit

Date: 2026-05-23

## Summary

The repository now has a working local-first MVP loop: SQLite schema,
AKShare-backed representative-universe ingestion, reproducible features,
baseline forecasts, rolling backtests, daily advice, official MCP stdio
transport, daily workflow automation, WebUI workbench, FRED macro ingestion,
market environment snapshots, benchmark/advice scoring, and multi-window model
calibration reports.

The README MVP is functionally implemented for a representative local-first
slice. FRED macro ingestion is unit-tested and live-verified after adding a
portable TLS CA bundle.

## Requirement Evidence Matrix

| README requirement | Current evidence | Status |
| --- | --- | --- |
| 数据可获取 | `investment-forecasting ingest mvp` now ingests a representative AKShare universe: 4 indices, 3 ETFs, 2 public funds, and 1 individual A-share. Live smoke wrote 30 rows across 10 assets. | Satisfied for representative MVP universe |
| 数据可持久化 | SQLite schema and idempotent upserts for core tables; tests cover schema, asset/price/features/predictions/backtests/advice/calibration writes. | Satisfied for current slice |
| 指标可复现 | `features_v1` calculates returns, volatility, drawdown, Sharpe, Calmar, win rate, momentum, and market state from stored prices only. | Satisfied for current slice |
| 模型可回测 | `baseline_mean_v1` rolling backtests persist runs/results and tests guard against future leakage. | Satisfied for baseline slice |
| 建议可解释 | `daily_advice_v1` records assumptions, risk warnings, profile variants, allocation ranges, triggers, evidence IDs, and compliance checks. | Satisfied for current slice |
| 每日任务可自动运行 | `investment-forecasting daily run` exists; Codex automation `investment-forecasting-daily-run` is active for daily 08:00 local runs. | Satisfied |
| 用户可通过 WebUI 查看结果 | `investment-forecasting web run` serves dashboard, data, funds, predictions, backtests, advice, and logs; Playwright desktop/mobile smoke passed. | Satisfied for current slice |
| 暴露 MCP 接口 | Eight MCP-compatible JSON tools exist with schemas, structured errors, and official Python SDK stdio transport via `investment-forecasting-mcp` / `investment-forecasting mcp serve`. | Satisfied for stdio MVP |
| A 股、指数、ETF、公募基金、宏观、情绪 | Current universe covers representative A-share, index, ETF, and public fund assets. `ingest macro` persists free FRED macro observations; market snapshots persist breadth/liquidity/sentiment proxies. | Satisfied for representative MVP |
| 基金基础信息/类型/费率/经理/规模 | `fund_info` ingestion populates tracked public funds with type, company, manager, custodian, scale, fee proxy, benchmark, strategy/objective, and stage-return JSON when AKShare fields are available. Live smoke populated two funds. | Satisfied for tracked public funds |
| 市场环境：宽度、成交热度、风格轮动、股债性价比 | `market_snapshots` stores index trend, breadth, liquidity heat, stock-bond proxy, sentiment, and details JSON. Latest stored FRED macro observations are included in snapshot evidence when present. Daily advice, MCP snapshot, and dashboard surface the snapshot. | Satisfied for MVP |
| 预测目标：跑赢沪深300/偏股基金指数/同类平均 | Backtests now calculate real benchmark excess against stored 沪深300 when aligned benchmark prices exist. Fund peer/偏股基金 benchmark remains future enhancement. | Mostly satisfied for MVP benchmark |
| 建议评分：方向、收益误差、风险识别、跑赢基准、回撤控制、可执行性 | Backtests score direction, return error, risk hit, benchmark excess, drawdown control, advice score, and overall score. Matured daily advice can be scored into `advice_outcome_scores` and updates `daily_advice` score fields. | Satisfied for MVP |
| 多段样本校准 | Historical corpus command populated a 2023-01-03 to 2025-12-31 expanded-universe sample and produced a three-window calibration report with promotion rationale. | Satisfied for MVP |
| 数据更新可重试、可检查、可回滚 | Provider calls use deterministic retry; ETF/stock fallback exists; ingestion writes per-asset `data_quality_reports` with warnings and metadata; daily workflow logs partial progress. Full rollback snapshots are still future work. | Mostly satisfied for MVP |
| 不输出保本/稳赚/确定性收益 | Compliance guard tests reject prohibited certainty language. | Satisfied |

## Material Follow-Up Tasks

1. Future enhancement: add Chinese macro or fund-peer benchmarks if a stable
   free provider is selected.

## Completion Decision

The README MVP is functionally implemented for a representative local-first
slice. Remaining work is enhancement scope rather than a blocker for the MVP
described in README.
