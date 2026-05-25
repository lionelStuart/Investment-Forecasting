# SPEC-011: Model Reliability Upgrade

## Status

draft

## Goal

Upgrade the model layer from single baseline point-return prediction to
auditable multi-model reliability: cross-sectional ranking, financial-grade
validation, calibrated probabilities, model evidence packets, expert
multi-model review, and Jarvis model-risk gates.

The product goal is not to promise stronger directional prediction. The goal
is to help Jarvis know which signals are usable, weak, stale, degraded, or
watch-only.

## Product Principle

Jarvis should become more selective, not more aggressive.

The daily product language should prefer:

- relative ranking;
- calibrated probability;
- risk-adjusted score;
- validation status;
- usable horizon;
- watch-only downgrade reasons;
- model disagreement explanation.

It should avoid making large expected-return values the primary user-facing
signal.

## Required Outputs

The model layer should eventually produce, per asset/horizon/model:

- `expected_return` retained as secondary evidence;
- `up_probability` calibrated where possible;
- `rank_score`;
- `same_category_rank`;
- `risk_adjusted_score`;
- `validation_status`;
- `recent_rank_ic`;
- `bucket_spread`;
- `confidence`;
- `degraded_reason`;
- linked evidence IDs.

## Validation Requirements

Validation must report more than direction hit rate:

- IC and Rank IC;
- top-bucket minus bottom-bucket return spread;
- same-category performance;
- horizon-level performance for 5/20/60 days;
- asset-type performance for stocks, ETFs, funds, and indexes;
- benchmark excess return;
- drawdown and downside-risk behavior;
- volatility and turnover where relevant;
- probability calibration quality;
- market-regime performance.

For overlapping 20/60-day labels, validation must use a gap, purge, or embargo
policy so future outcome windows do not leak into training or evaluation.

## Candidate Model Requirements

Candidate models should be introduced in order:

1. `momentum_reversal_v1`
2. `risk_adjusted_factor_v1`
3. `tree_ranker_v1` only after ranking validation is in place
4. `probability_calibrator_v1`
5. `ensemble_v1` only after stable out-of-sample evidence beats baseline

`baseline_mean_v1` remains the minimum floor and comparison baseline.

## Promotion Gates

A candidate model can influence Jarvis primary daily conclusions only if:

- it beats `baseline_mean_v1` across multiple walk-forward windows;
- Rank IC is positive and reasonably stable for the relevant horizon;
- top-bucket minus bottom-bucket spread is positive after conservative costs or
  assumptions;
- drawdown/downside risk does not materially worsen versus baseline;
- performance is visible by asset type and same-category peer group;
- model monitoring is not `degraded`;
- output is linked to persisted evidence IDs;
- Jarvis gates do not downgrade the signal to watch-only.

If a candidate only works in one market regime, asset type, or horizon, it may
be used only as scoped contextual evidence.

## Expert Review Requirements

Experts are style-biased reviewers of model evidence, not voting machines that
can bypass model health checks.

Each expert should consume a standard model evidence packet:

- model version;
- horizon days;
- expected return;
- up probability;
- rank score;
- risk-adjusted score;
- validation status;
- recent Rank IC;
- degraded reason;
- evidence IDs.

Experts may weight evidence differently by style, but degraded signals can only
support watch, hedge, or patience language.

## Jarvis Requirements

Jarvis acts as a model risk officer:

- degraded model signals become watch-only;
- horizons with negative Rank IC are excluded from primary conclusions;
- insufficient sample asset types avoid strong ranking language;
- immature expert performance remains context, not conviction;
- weak model agreement is not amplified into strong confidence;
- disagreement between model families is explained.

## Non-Goals

- No guaranteed prediction improvement.
- No direct trading automation.
- No live brokerage integration.
- No transformer/foundation time-series model as a production default.
- No reinforcement-learning allocation.
- No new experts or expert-voting logic.
- No UI expansion beyond the five Jarvis primary entries.

## Acceptance Criteria

- Model outputs include ranking and reliability metadata without breaking
  existing `model_predictions` consumers.
- Validation reports IC, Rank IC, bucket spread, same-category and asset-type
  metrics, and gap/purge/embargo settings.
- Candidate models are compared against `baseline_mean_v1` under the same
  validation framework.
- Expert and Jarvis model evidence packets use a shared schema.
- Jarvis can explain why a tempting signal is watch-only or excluded.
- No candidate model is promoted without satisfying explicit promotion gates.

## Implementation Notes

- `TASK-074` stores first-pass reliability metadata in
  `model_prediction_reliability`, a sidecar table keyed by `prediction_id`.
  This keeps point-return forecasts backward compatible while allowing
  reliability-aware consumers to join rank score, same-category rank,
  risk-adjusted score, validation status, degraded reason, and evidence IDs.
- `TASK-075` writes financial validation metrics into
  `backtest_runs.metrics_json`: information coefficient, Rank IC, top/bottom
  bucket spread, same-category and asset-type performance, probability
  calibration bins, validation policy, and validation status. Monitoring and
  MCP read the same metrics instead of inventing a parallel reliability view.
- `TASK-076` adds the first interpretable candidate pool:
  `momentum_reversal_v1` and `risk_adjusted_factor_v1`. Forecast, backtest,
  calibration, CLI, and MCP paths can evaluate one or more model versions while
  keeping `baseline_mean_v1` as the default primary baseline. Candidate rows
  write the same reliability sidecar fields as baseline rows and remain
  contextual unless later promotion gates approve them.
- `TASK-077` standardizes `model_evidence_packet_v1` for expert and Jarvis
  consumers. The packet is built from `model_predictions` joined with
  `model_prediction_reliability`, so experts and Jarvis see the same
  validation status, Rank IC, bucket spread, rank, risk-adjusted score,
  degraded reason, and evidence IDs. Expert plans must keep degraded,
  negative-Rank-IC, or negative-bucket-spread model evidence as watch-only
  context.
- `TASK-078` makes Jarvis an explicit model risk officer. It keeps raw model
  values visible but adds gate reasons, `model_risk_summary`,
  `excluded_horizons`, and `degraded_model_families` to daily synthesis. Phone
  summaries and MCP output expose the same gate reasons so agents and users can
  see why a high-return or high-rank signal is watch-only.
- `TASK-079` adds promotion/demotion governance without automatic production
  promotion. Calibration and monitoring now emit model governance state,
  promotion blockers, demotion reasons, Jarvis-primary eligibility, and product
  review requirements. The phase decision is that `baseline_mean_v1` remains
  primary, while current interpretable candidates remain contextual/degraded
  evidence until future validation and product review approve a change.

## Related Tasks

- `TASK-074`: Prediction target and model-output redesign.
- `TASK-075`: Financial validation upgrade.
- `TASK-076`: Interpretable candidate model pool.
- `TASK-077`: Model evidence packet and expert review.
- `TASK-078`: Jarvis model risk officer gates.
- `TASK-079`: Model promotion and demotion governance.
