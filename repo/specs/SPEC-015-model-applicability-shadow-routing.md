# SPEC-015: Model Applicability And Shadow Routing Governance

## Status

draft

## Goal

Turn the 2026 replay findings into a durable model prediction strategy
optimization loop. The system should stop treating model optimization as
"choose the best global model" and instead learn which model is applicable for
which horizon, asset scope, and output purpose.

This phase remains model-layer only. It does not change expert committee
behavior, Jarvis conclusions, investment advice, phone summaries, or
operational portfolio behavior.

## Source Evidence

The plan is based on:

- `research/model_tuning_2026/OPTIMIZATION_DIRECTION.md`
- `research/model_tuning_2026/CEO_GENERALIZABLE_MODEL_OPTIMIZATION_PLAN.md`
- 2026 replay run `1`
- `SPEC-014` replay and tuning audit output

Important current evidence:

- 5-day dynamic routing underperformed the fixed baseline in holdout.
- 20-day conservative routing has potential, but only as shadow evidence.
- 20-day signal is stronger for broad asset-type allocation than same-type
  asset ranking.
- Raw confidence is not predictive certainty.
- 60-day promotion must wait for more matured outcomes.

## Product Principle

Model suitability is conditional.

The same model may be useful for:

- short-horizon forecast;
- medium-term allocation bias;
- same-type ranking;
- risk reference;
- observation only.

A model can be helpful for one output purpose and harmful for another. A single
global score must not silently grant a model broader authority than the replay
evidence supports.

## Scope

- Build persistent model-health metrics by model, horizon, asset scope, month,
  and evaluation window.
- Derive model applicability profiles from model-health evidence.
- Add same-type ranking disable rules.
- Run a conservative 20-day shadow router named `router_floor70_cap05`.
- Keep operational model defaults unchanged.
- Add confidence calibration labels that treat raw confidence as evidence
  quality, not success probability.
- Produce a monthly model governance summary after matured holdout windows.

## Non-Goals

- No production model switch.
- No operational `model_predictions` overwrite.
- No expert committee behavior change.
- No Jarvis conclusion or confidence-gate change.
- No investment advice or portfolio behavior change.
- No phone-summary language change.
- No black-box model.
- No same-type ranking usage for 20-day router output.

## Model Health Fact Layer

Persist monthly and rolling health metrics with at least this grain:

```text
model_version
horizon_days
asset_type
same_category_key
prediction_month
evaluation_window
sample_count
direction_accuracy
rank_ic
bucket_spread
top_bottom_decile_spread
mae
median_abs_error
raw_high_conf_wrong_rate
coverage_rate
status
output_role
promotion_status
degradation_reason
minimum_sample_met
consumer_display_level
last_promoted_at
last_demoted_at
```

This table is a model fact layer. It may later inform products, but this phase
does not wire it into Jarvis, experts, advice, or UI behavior.

## Applicability Roles

Each model/horizon/scope should be assigned one role:

| Role | Meaning |
| --- | --- |
| `primary_forecast` | Model is acceptable as the current default for this scoped model output. |
| `allocation_bias` | Model is useful only for broad asset/product bucket direction. |
| `ranking_signal` | Model is useful for sorting comparable assets within the same type/category. |
| `risk_reference` | Model is useful only for caution/risk interpretation. |
| `observation_only` | Evidence is insufficient or unstable; use only for research review. |

Initial target profile:

- 5-day `baseline_mean_v1`: `primary_forecast`.
- 5-day router candidates: `observation_only`.
- 20-day `baseline_mean_v1`: keep as default forecast evidence, but not
  same-type selector if same-type metrics are weak.
- 20-day `router_floor70_cap05`: `allocation_bias` in shadow mode only.
- 20-day same-type ranking: `observation_only` until same-type Rank IC and
  bucket spread become positive.
- 60-day `baseline_mean_v1`: `primary_forecast` until additional holdout
  matures.
- 60-day risk-adjusted/ensemble candidates: `observation_only`.
- Raw confidence: `risk_reference` or caution label only.

## Same-Type Ranking Disable Rules

- If same-type Rank IC is non-positive, the model/horizon cannot be used as a
  same-type ranking signal.
- If same-type bucket spread is non-positive, the model/horizon cannot be used
  to sort comparable funds, ETFs, stocks, or indexes as if one is stronger than
  another.
- If either disable rule fires, the signal may only be assigned to
  `allocation_bias`, `risk_reference`, or `observation_only`.

## Shadow Router

Initial shadow candidate:

```text
name: router_floor70_cap05
horizon: 20
baseline floor: 70%
monthly max turnover: 5%
initial observed mean baseline weight: 93%
```

Shadow routing must:

- use only outcomes matured before each simulated decision month;
- persist shadow predictions or shadow metrics separately from operational
  predictions;
- compare against fixed baseline after each monthly maturity update;
- never change operational forecasts in this phase.

Promotion is explicitly out of scope. Shadow routing can only become eligible
for a future review if at least one additional matured monthly holdout is no
worse than fixed baseline on Rank IC, bucket spread, direction accuracy,
high-confidence wrong rate, and turnover stability.

## Confidence Calibration

Raw confidence must not be interpreted as "probability of being right."

Initial labels:

| Label | Minimum interpretation |
| --- | --- |
| `暂不强调` | Insufficient sample, negative Rank IC, negative bucket spread, or elevated high-confidence wrong rate. |
| `谨慎观察` | Enough evidence to watch, but calibration tiers do not yet show stable realized separation. |
| `相对稳健` | Multiple matured windows show positive separation, controlled error, and lower high-confidence wrong rate. |

No strong confidence language is allowed until calibrated tiers show stable
realized separation.

## Monthly Governance Summary

After each matured monthly holdout, produce a model-layer governance summary
that answers:

1. Which model/horizon/scope remains safe as default?
2. Which model/horizon/scope can continue in shadow mode?
3. Which model signals must be downgraded or disabled inside the model layer?
4. Did any model become promotion-review eligible under published gates?

The monthly review is governance, not constant parameter tinkering.

## Acceptance Criteria

- Model-health metrics are persisted from replay/shadow evidence.
- Applicability roles are derived deterministically from metrics.
- 20-day same-type ranking is disabled when same-type Rank IC or bucket spread
  is non-positive.
- `router_floor70_cap05` runs as shadow only and cannot alter operational
  `model_predictions`.
- Confidence labels are derived from sample size, rank/bucket quality,
  calibration separation, and high-confidence wrong rate.
- Monthly governance summary is generated from model facts and states that
  defaults remain unchanged unless a future review approves promotion.
- Tests prove no expert, Jarvis, advice, phone, WebUI, or portfolio path is
  invoked by this phase.

## Related Tasks

- `TASK-093`: Model health fact layer.
- `TASK-094`: Applicability profiles and same-type disable rules.
- `TASK-095`: 20-day shadow router.
- `TASK-096`: Confidence calibration labels.
- `TASK-097`: Monthly model governance summary.
