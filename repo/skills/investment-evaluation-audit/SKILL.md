---
name: investment-evaluation-audit
description: Use for the Investment Forecasting project when asked to inspect the WebUI and SQLite database, analyze historical market data, forecasts, backtests, advice scores, regressions, model accuracy, improvement opportunities, or product/page design defects. Triggers on requests like "评估当前预测准确度", "分析历史数据和评分", "检查页面设计缺陷", "找模型改进方向", or "audit Investment Forecasting evaluation".
---

# Investment Evaluation Audit

Use this skill only inside `/Users/wonderwall/project/Investment-Forecasting`.
It is a diagnostic workflow for evaluating prediction quality, data health,
model/backtest evidence, advice outcomes, and WebUI product defects.

## First Context

Read these files before analysis:

1. `repo/AGENTS.md`
2. `repo/PROJECT.md`
3. `repo/STATUS.md`
4. `repo/INDEX.md`
5. `repo/CODE_INDEX.md`
6. Relevant specs/tasks for the suspected area

Then inspect only the implementation surfaces needed for the audit:

- WebUI: `src/investment_forecasting/web/app.py`, `tests/test_web_app.py`
- Database/schema: `src/investment_forecasting/db.py`,
  `src/investment_forecasting/migrations/001_init.sql`
- Forecast/backtest/calibration:
  `src/investment_forecasting/quant/*.py`, related tests
- Advice/scoring: `src/investment_forecasting/advice/*.py`, related tests
- Workflow/logs: `src/investment_forecasting/workflows/daily.py`,
  `scripts/restart_web.sh`

## Evidence Sources

Default database:

```bash
DB_PATH="${DB_PATH:-data/investment_forecasting.sqlite3}"
```

Important tables:

- Coverage and raw history: `assets`, `price_daily`, `fund_info`
- Derived state: `features_daily`, `market_snapshots`, `macro_observations`
- Forecast/evaluation: `model_predictions`, `backtest_runs`,
  `backtest_results`, `advice_outcome_scores`,
  `model_calibration_reports`
- Product/advice: `daily_advice`, `user_preferences`
- Operations: `task_logs`, `data_quality_reports`

Start with row counts, date ranges, and latest records before drawing
conclusions. Use SQLite queries, MCP tools, CLI commands, and WebUI inspection
as cross-checks rather than relying on one surface.

## Suggested Data Checks

Run small, targeted SQLite queries such as:

```bash
sqlite3 "$DB_PATH" "SELECT type, COUNT(*) FROM assets GROUP BY type ORDER BY type;"
sqlite3 "$DB_PATH" "SELECT MIN(date), MAX(date), COUNT(*) FROM price_daily;"
sqlite3 "$DB_PATH" "SELECT status, COUNT(*) FROM task_logs GROUP BY status;"
sqlite3 "$DB_PATH" "SELECT model_version, horizon_days, COUNT(*), AVG(confidence) FROM model_predictions GROUP BY model_version, horizon_days;"
sqlite3 "$DB_PATH" "SELECT horizon_days, AVG(overall_score), AVG(direction_score), AVG(error_score), AVG(risk_score) FROM backtest_results GROUP BY horizon_days;"
sqlite3 "$DB_PATH" "SELECT horizon_days, AVG(score), COUNT(*) FROM advice_outcome_scores GROUP BY horizon_days;"
```

Adjust column names after checking schema with:

```bash
sqlite3 "$DB_PATH" ".schema TABLE_NAME"
```

When network or provider commands fail, retry once with the proxy variables
from `repo/AGENTS.md`.

## WebUI Inspection

Ensure the local WebUI reflects the same evidence as the database.

Start or refresh it with:

```bash
scripts/restart_web.sh
```

Inspect the operating workbench routes:

- `/` dashboard status, latest advice, data freshness, model/backtest summary
- `/timeline` run chronology and missing-stage recovery hints
- `/categories` category coverage and drill-in summaries
- `/data` selected asset history, metrics, chart, and raw technical details
- `/funds` fund ranking and metadata filters
- `/predictions` latest model outputs and priority assets
- `/backtests` score distribution and run summaries
- `/advice` advice history, assumptions, risks, and evidence links
- `/settings` active risk preference and investment horizon
- `/logs` failed/running/successful job details

If Browser tools are available, use them for screenshots, route checks,
responsive checks, and console errors. If not, use HTTP/curl smoke checks and
source inspection.

## Evaluation Lens

Score the project on evidence, not vibes:

- Data coverage: asset count, type mix, date span, gaps, freshness, provider
  failures, and quality warnings.
- Forecast accuracy: score by horizon, model version, asset type/category,
  confidence calibration, stale predictions, and regression from previous
  runs.
- Backtest integrity: rolling-window setup, no future leakage, benchmark
  comparison, score variance, and weak horizons/categories.
- Advice quality: outcome scores, alignment with risk preference, evidence
  links, assumptions, uncertainty, and prohibited-certainty language.
- Product usefulness: whether pages help the operator decide what changed,
  what is trustworthy, what failed, and what to do next.
- Design defects: navigation gaps, overexposed technical tables, unclear red/
  green semantics, missing empty/error states, mobile overflow, poor hierarchy,
  hidden evidence, or duplicated/conflicting metrics.

For each issue, include severity, evidence, likely root cause, and the smallest
valuable fix.

## Output Shape

Return a concise audit report:

1. Overall verdict and confidence.
2. Data health findings.
3. Prediction/backtest/advice accuracy findings.
4. Regression or drift risks.
5. WebUI/product/design defects.
6. Recommended next fixes, ordered by impact.
7. Suggested task/spec/roadmap updates if durable planning should change.

Use absolute file links when referencing local code. If making code or docs
changes, follow `repo/AGENTS.md` end-of-task update rules and update
`repo/INDEX.md`, `repo/STATUS.md`, task files, or specs as appropriate.

## Guardrails

- Do not claim investment certainty, guaranteed returns, or capital protection.
- Distinguish historical score from future expected performance.
- Treat backtests as evidence quality signals, not proof.
- Do not delete or overwrite production-like SQLite data during audit.
- Prefer read-only database queries unless the user explicitly asks for a data
  repair or migration.
