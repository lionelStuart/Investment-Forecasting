# SPEC-014: YTD Model Accuracy And Confidence Replay Audit

## Status

draft

## Goal

Build a reproducible year-to-date forecast replay corpus for the current year,
score matured historical predictions against already stored price data, and use
the diagnostics to propose concrete model tuning directions.

The immediate product need is to answer: "If the current model family had made
daily predictions throughout this year, where did it work, where did it fail,
and what should we tune next?"

## Current Evidence

Local database inspection on 2026-05-25 shows:

- `price_daily` covers 2024-01-02 through 2026-05-22.
- `model_predictions` contains latest/partial prediction rows, not a complete
  2026 daily prediction ledger.
- `backtest_results` already stores rolling historical results, but they are
  not organized as a current-year replay audit with product-facing tuning
  conclusions.

Therefore this feature should create a separate replay/evaluation surface
instead of overwriting production `model_predictions`.

## Product Principle

This is a model audit and tuning loop, not a promise of higher returns.

This phase is scoped to the prediction model layer only. It does not evaluate,
change, or score expert committee predictions, expert virtual actions, Jarvis
daily conclusions, Jarvis confidence gates, investment advice, or portfolio
performance.

Outputs must emphasize:

- model version comparison;
- horizon reliability;
- asset-type and theme reliability;
- market-regime sensitivity;
- direction/rank quality;
- calibration and confidence quality;
- failure clusters;
- recommended tuning experiments;
- whether each model/horizon/scope is validated, underconfident,
  overconfident, degraded, or insufficient-sample.

## Scope

- Replay each available trading day in the current year from local stored
  history only.
- Generate simulated predictions for configured model versions and horizons
  using only information available on each prediction date.
- Score only matured predictions where the future outcome date exists in
  `price_daily`.
- Keep immature predictions as pending coverage, not failed predictions.
- Compare `baseline_mean_v1`, `momentum_reversal_v1`, and
  `risk_adjusted_factor_v1` under the same replay rules.
- Persist replay run metadata, per-prediction replay rows, scored outcomes, and
  aggregate diagnostics.
- Produce a tuning report that ranks concrete next experiments.
- Expose replay and report results through CLI first.

## Non-Goals

- No provider download. The first replay must use already stored data.
- No full-history provider refresh.
- No direct model promotion.
- No new black-box model as part of the replay MVP.
- No expert committee evaluation.
- No Jarvis prediction, Jarvis brief, or Jarvis confidence-gate evaluation.
- No investment advice evaluation.
- No MCP/WebUI surface in the first scoped implementation.
- No live trading or portfolio execution changes.

## Replay Window

For the current date 2026-05-25, the default replay should be:

- `start_date`: 2026-01-01 or the first stored trading day after it.
- `end_date`: latest stored trading day, currently 2026-05-22.
- `as_of_date`: command/report date, e.g. 2026-05-25.
- `horizons`: 5, 20, 60 trading observations by default.
- `lookback_days`: 60 by default.
- `maturity_policy`: score only rows whose outcome observation exists.

The implementation should also accept explicit `--start-date`, `--end-date`,
`--year`, `--horizons`, `--lookback-days`, `--model-versions`, and `--asset-scope`
arguments so later audits can replay different periods.

## Data Contract

MVP persistence may use new tables or a clearly separated replay namespace. The
recommended durable shape is:

- `model_replay_runs`
  - `id`
  - `run_date`
  - `year`
  - `start_date`
  - `end_date`
  - `as_of_date`
  - `asset_scope`
  - `model_versions`
  - `horizons`
  - `lookback_days`
  - `parameters_json`
  - `metrics_json`
  - `tuning_recommendations_json`
  - `created_at`
- `model_replay_predictions`
  - `id`
  - `run_id`
  - `asset_id`
  - `prediction_date`
  - `horizon_days`
  - `model_version`
  - `predicted_return`
  - `up_probability`
  - `downside_risk`
  - `confidence`
  - `input_window_start`
  - `input_window_end`
  - `outcome_date`
  - `actual_return`
  - `benchmark_return`
  - `score_status`
  - `prediction_score`
  - `risk_score`
  - `overall_score`
  - `details_json`

The replay rows must not replace current `model_predictions`. Production
predictions remain the latest operational signal; replay predictions are
historical audit evidence.

## Metrics

The replay audit should report:

- coverage:
  - assets included;
  - prediction days generated;
  - matured rows;
  - pending rows by horizon;
  - skipped rows and reasons.
- scoring:
  - direction accuracy;
  - mean absolute return error;
  - risk hit rate;
  - benchmark excess;
  - prediction/risk/overall score.
- ranking:
  - IC;
  - Rank IC;
  - top-bottom bucket spread.
- slices:
  - horizon;
  - model version;
  - asset type;
  - same-category/theme;
  - month;
  - market regime when available.
- calibration:
  - predicted up-probability bucket vs realized positive rate;
  - confidence bucket vs realized error;
  - overconfidence flags.
- failure clusters:
  - high-confidence wrong direction;
  - negative Rank IC periods;
  - negative bucket spread periods;
  - downside-risk misses;
  - asset groups with persistent underperformance.

## Tuning Recommendations

The report should convert diagnostics into ranked, testable tuning directions:

- If 5-day horizon has negative Rank IC, reduce short-horizon weight or make it
  a low-confidence model signal until a candidate improves it.
- If 20/60-day labels are unstable, increase embargo/gap and evaluate fewer
  overlapping labels.
- If up-probability is overconfident, add probability calibration before using
  probability as a model confidence output.
- If one asset type or theme performs materially worse, add scoped degradation
  gates instead of degrading all model output.
- If `momentum_reversal_v1` only works in some regimes, keep it contextual and
  define regime-specific activation experiments.
- If `risk_adjusted_factor_v1` improves drawdown but hurts rank quality, treat
  it as a risk-adjusted confidence overlay candidate, not a general return
  predictor.
- If baseline beats candidates, keep model defaults unchanged and tune
  confidence/ranking evidence before trying a new model family.

Every recommendation must include:

- triggering evidence metric;
- affected horizon/model/scope;
- suggested experiment;
- expected verification metric;
- stop condition.

## CLI

Planned CLI:

- `investment-forecasting model-validation replay-ytd --db ... --year 2026 --horizons 5,20,60 --model-versions baseline_mean_v1,momentum_reversal_v1,risk_adjusted_factor_v1`
- `investment-forecasting model-validation report --db ... --run-id latest`
- `investment-forecasting model-validation tuning-plan --db ... --run-id latest`

MCP and WebUI exposure are intentionally deferred until the model-layer report
is accepted.

## Acceptance Criteria

- A command can replay 2026 year-to-date daily predictions from stored local
  data without network calls.
- Replayed predictions are persisted separately from production
  `model_predictions`.
- Scoring uses only matured outcome windows and marks immature rows as pending.
- Report compares all configured model versions by horizon and asset group.
- Report includes at least five ranked tuning recommendations with evidence
  metrics and stop conditions.
- CLI can retrieve the latest replay summary and tuning plan.
- Tests prove there is no future leakage and no production prediction overwrite.
- Tests prove this phase does not invoke expert, Jarvis, advice, MCP, WebUI, or
  provider-ingestion paths.

## Related Tasks

- `TASK-090`: YTD forecast replay corpus.
- `TASK-091`: Replay scoring and diagnostic metrics.
- `TASK-092`: Model tuning recommendation report.
