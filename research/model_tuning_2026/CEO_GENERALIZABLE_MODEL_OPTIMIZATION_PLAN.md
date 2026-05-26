# Generalizable Model Optimization System Plan

Generated: 2026-05-25

Audience: CEO / product and engineering leadership

Status: proposal based on 2026 replay research. This document separates
generalizable system design from parameters that are only current-data
candidates.

## Executive Summary

The 2026 replay experiments show that the next model improvement should not be
"pick a better single model." The stronger and more generalizable approach is
to build a model applicability and governance layer around the existing model
pool.

The system should learn which model is suitable for which context:

- horizon: 5 / 20 / 60 trading days;
- asset scope: asset type, category, and same-type ranking;
- market phase: recent drift and regime shift;
- output purpose: allocation bias, ranking signal, risk reference, or display
  confidence.

This proposal recommends a four-layer optimization system:

1. model health monitoring;
2. model applicability profiles;
3. shadow routing and promotion gates;
4. confidence and product-language calibration.

The immediate product decision is conservative:

- keep 5-day and 60-day production defaults stable;
- run 20-day routing only as a shadow layer;
- treat 20-day signal as broad allocation bias, not same-type asset selection;
- stop exposing raw confidence as predictive certainty.

## Why This Is Generalizable

The reusable insight is not that a specific router parameter won. The reusable
insight is that model suitability is conditional.

The same model can be useful for one output purpose and harmful for another.
For example, a model can help choose between asset types while failing to rank
funds within the same asset type. A single global accuracy score hides this
difference and can push the product toward misleading recommendations.

The proposed system generalizes because it creates a repeatable loop:

1. observe model quality by context;
2. assign each model a context-specific role;
3. test changes in shadow mode;
4. promote only after out-of-sample evidence;
5. degrade product language when evidence is weak.

This can work across future market periods, new models, new assets, and new
data providers because it is a governance architecture rather than a fixed
2026 parameter rule.

## Evidence From Current Replay

Current evidence comes from local 2026 replay run `1`.

- Matured replay samples: 255,201 across 5/20/60 day horizons.
- Focused 20-day matured rows: 96,588.
- 20-day focused shadow predictions: 257,568.
- Walk-forward experiments only used outcomes that had matured before the
  simulated decision period.

Important findings:

1. Dynamic routing is not universally helpful.
   - 5-day router underperformed fixed baseline in holdout.
   - This proves routing must be horizon-specific.

2. 20-day routing has potential, but only conservatively.
   - A baseline-heavy 20-day router improved holdout direction accuracy,
     Rank IC, bucket spread, and high-confidence wrong rate versus fixed
     baseline.
   - The effect is not strong enough for immediate production replacement.

3. 20-day signal is mainly allocation-level, not same-type ranking.
   - In holdout, asset-type allocation Rank IC was positive.
   - Within ETF/fund/stock groups, Rank IC and bucket spread were weak or
     negative.

4. Raw confidence is not predictive certainty.
   - Raw high-confidence wrong rate stayed too high for strong product claims.
   - Initial calibrated tiers did not create a trustworthy high-confidence
     segment.

5. 60-day promotion must wait.
   - April/May 60-day outcomes have not matured yet.
   - Existing evidence supports keeping the current baseline.

## Target System Model

### Layer 1: Model Health Monitoring

Create a durable monitoring asset that evaluates every model by context.

Recommended grain:

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
```

Purpose:

- detect model drift;
- identify where a model is useful;
- provide evidence for routing, confidence, and product copy;
- create auditability for future model changes.

This layer should not change predictions. It is a measurement foundation.

### Layer 2: Model Applicability Profiles

Each model should have a context-specific role, not just a score.

Recommended roles:

| Role | Meaning | Product usage |
| --- | --- | --- |
| `primary_forecast` | Can drive the main forecast for this context | operational prediction |
| `allocation_bias` | Useful for broad asset/product bucket preference | opportunity pool emphasis |
| `ranking_signal` | Useful for sorting within comparable assets | ranking cards and filters |
| `risk_reference` | Useful for caution/risk adjustment | risk panel and warnings |
| `observation_only` | Evidence is insufficient or unstable | research only |

Initial applicability profile from current evidence:

| Context | Recommended role |
| --- | --- |
| 5-day `baseline_mean_v1` | `primary_forecast` |
| 5-day router | `observation_only` |
| 20-day fixed baseline | `primary_forecast` baseline, but not same-type selector |
| 20-day conservative router | `allocation_bias` in shadow mode |
| 20-day same-type ranking | `observation_only` until within-type Rank IC turns positive |
| 60-day `baseline_mean_v1` | `primary_forecast` until new holdout matures |
| 60-day risk-adjusted / ensemble | `observation_only` |
| raw confidence | `risk_reference` / caution label only |

### Layer 3: Shadow Routing And Promotion Gates

Routing should not be a production switch at first. It should run as a shadow
prediction and compete against the current baseline.

Initial shadow candidate:

```text
20-day router_floor70_cap05
baseline floor: 70%
monthly max turnover: 5%
initial observed mean baseline weight: 93%
```

Promotion requirements:

- at least one additional matured monthly holdout;
- no worse than fixed baseline on:
  - Rank IC;
  - bucket spread;
  - direction accuracy;
  - high-confidence wrong rate;
  - turnover stability;
- no severe degradation by asset type;
- no claim that it improves same-type ranking unless within-type evidence is
  positive.

Demotion or stop conditions:

- if the shadow route loses Rank IC or bucket spread versus fixed baseline in
  the next matured month, do not promote;
- if turnover spikes without quality gain, tighten cap or disable;
- if gains come only from one unstable asset type, keep it in research.

### Layer 4: Confidence And Product-Language Calibration

Raw model confidence should not be shown as probability of being right.

Recommended product wording:

| Internal state | Product wording | Meaning |
| --- | --- | --- |
| evidence weak or unstable | `暂不强调` | do not promote as a strong signal |
| enough evidence but elevated error | `谨慎观察` | usable context, not certainty |
| repeated out-of-sample separation | `相对稳健` | only after calibrated tiers prove separation |

Rules:

- No "高置信收益" language until calibrated confidence tiers show stable
  realized separation.
- Confidence should combine recent model health, sample size, horizon, asset
  type, and high-confidence wrong rate.
- Confidence should affect product emphasis before it affects alpha.

## Implementation Plan

### Phase 1: Measurement Foundation

Deliver:

- persistent model-health table;
- monthly and rolling-window metrics;
- report command and WebUI evidence panel;
- regression tests for no future leakage.

Success criteria:

- every model/horizon has monthly health metrics;
- metrics are point-in-time and reproducible;
- product and engineering can see where a model is healthy or degraded.

### Phase 2: 20-Day Shadow Router

Deliver:

- shadow route `router_floor70_cap05`;
- persisted shadow predictions or aggregate metrics;
- baseline comparison after each maturity update;
- no impact on operational predictions.

Success criteria:

- shadow route is comparable to fixed baseline every month;
- no hidden production behavior changes;
- router promotion decision is evidence-backed.

### Phase 3: Product Semantics Update

Deliver:

- 20-day output labeled as "中期大类倾向" unless within-type ranking evidence
  becomes positive;
- confidence language downgraded from certainty to caution;
- evidence links explaining why a signal is used for allocation, ranking, or
  risk only.

Success criteria:

- product no longer implies guaranteed or high-certainty correctness;
- users can distinguish short-term forecast, medium-term allocation bias, and
  long-term observation.

### Phase 4: Promotion Governance

Deliver:

- formal model promotion checklist;
- stop conditions and rollback conditions;
- change log for model-role changes;
- monthly CEO/product review summary.

Success criteria:

- no model default changes without out-of-sample evidence;
- every promotion has a baseline comparison and failure mode review;
- degraded models become quieter automatically.

## Architecture Sketch

```text
Replay / live predictions
        |
        v
Model health monitoring
        |
        v
Model applicability profile
        |
        +--> production default model
        |
        +--> shadow router experiments
        |
        +--> confidence/product language calibration
        |
        v
Jarvis / Opportunity Pool / Evidence UI
```

## CEO-Level Decision Requests

1. Approve the shift from "best model wins" to "model applicability by
   context."

2. Approve shadow-first governance for routing changes.
   The system should gather evidence before changing production model outputs.

3. Approve product-language downgrade for confidence.
   The product should avoid strong confidence claims until calibration proves
   realized separation.

4. Approve treating 20-day output as allocation bias first.
   It should not be marketed internally or externally as same-type asset
   selection until within-type evidence improves.

## What This Does Not Claim

- It does not claim the 20-day router is ready for production.
- It does not claim current results generalize permanently.
- It does not claim any model can guarantee returns.
- It does not claim confidence is an investment success probability.
- It does not recommend adding a complex black-box model before monitoring and
  governance exist.

## Recommended Next Step

Implement Phase 1 and Phase 2 together:

1. build model-health monitoring;
2. run `router_floor70_cap05` as a 20-day shadow route;
3. keep production defaults unchanged;
4. review after the next matured 20-day monthly holdout.

This is the highest-signal next step because it converts current research into
a durable optimization loop without overfitting one 2026 sample.

## CEO Review Addendum

Reviewed: 2026-05-25

CEO decision: directionally approved as a model governance and reliability
system, not as a model production rollout.

The proposal is aligned with Jarvis's long-term product goal. Jarvis is not a
return-prediction machine; it is a consumer-facing investment research
assistant that must know which evidence is usable, which evidence is weak, and
when a tempting model signal should be downgraded or ignored.

### What To Preserve

The strongest part of the proposal is the shift from `best model wins` to
`model applicability by context`.

Keep these principles:

- model suitability is horizon-specific;
- model suitability is asset-scope-specific;
- model output purpose matters: allocation bias, same-type ranking, risk
  reference, and display confidence are different jobs;
- routing changes must run in shadow mode before production use;
- raw confidence must not be presented as predictive certainty.

These principles are more valuable than any specific 2026 router parameter.

### Required Tightening

#### 1. Treat Phase 1 As A Product Governance Foundation

The model-health table should not be a developer-only monitoring artifact. It
should become the shared model fact layer for Jarvis, experts, Opportunity
Pool, Evidence UI, and future model reviews.

Add or derive fields that can support product behavior:

- `output_role`
- `promotion_status`
- `degradation_reason`
- `last_promoted_at`
- `last_demoted_at`
- `minimum_sample_met`
- `consumer_display_level`

This lets the product say, for example, "this signal is only an allocation
tilt" instead of exposing a raw score without context.

#### 2. Keep 20-Day Routing Strictly Shadow

The 20-day router should not change:

- operational `model_predictions`;
- Jarvis primary stance;
- expert action generation;
- Opportunity Pool same-type ranking;
- phone-summary language.

It may run as shadow evidence and appear in internal model-health review, but
it must not influence user-facing product behavior until at least one
additional matured monthly holdout passes promotion gates.

#### 3. Add Same-Type Ranking Disable Rules

The current evidence says the 20-day signal is more promising for broad
allocation bias than for same-type asset selection. Make this an explicit rule:

- If same-type Rank IC is non-positive, the model/horizon cannot be used for
  same-type asset ranking.
- If same-type bucket spread is non-positive, the model/horizon cannot be used
  to sort comparable funds, ETFs, or stocks as if one is stronger than another.
- In that state, the signal may only be used for broad allocation, risk
  reference, or observation language.

This protects the consumer product from turning a weak ranking signal into a
strong recommendation.

#### 4. Quantify Confidence Language

The proposed labels are right, but they need measurable gates.

Recommended first-pass mapping:

| Product wording | Minimum interpretation |
| --- | --- |
| `暂不强调` | insufficient sample, negative Rank IC, negative bucket spread, or elevated high-confidence wrong rate |
| `谨慎观察` | enough evidence to watch, but calibration tiers do not yet show stable realized separation |
| `相对稳健` | multiple matured windows show positive separation, controlled error, and lower high-confidence wrong rate |

No UI, Jarvis brief, expert prompt, or phone summary should use language that
sounds like high certainty until this separation is proven.

#### 5. Bind Model Roles To Product Surfaces

Applicability roles should directly control where a signal can appear:

| Role | Allowed product usage |
| --- | --- |
| `primary_forecast` | Jarvis model summary and operational forecast evidence |
| `allocation_bias` | broad asset/product bucket emphasis only |
| `ranking_signal` | Opportunity Pool same-type ranking and comparable-asset sorting |
| `risk_reference` | caution, drawdown, volatility, or risk-boundary panels only |
| `observation_only` | Evidence UI or watch-list language only |

This prevents implementation drift where a model labeled "contextual" quietly
starts affecting primary recommendations.

### CEO Monthly Review Gate

Add a monthly CEO/product review summary after each matured holdout window. The
review should answer only four questions:

1. Which model/horizon/scope remains safe as production default?
2. Which model/horizon/scope can continue in shadow mode?
3. Which signals must be downgraded in Jarvis or Opportunity Pool language?
4. Did any model earn promotion eligibility under the published gates?

Avoid monthly parameter tinkering. The review is for governance, not constant
optimization.

### Approved Next Scope

Approved:

1. Build persistent model-health monitoring.
2. Run `router_floor70_cap05` as a 20-day shadow route.
3. Keep production defaults unchanged.
4. Downgrade confidence/product language so users understand confidence as
   evidence quality, not success probability.
5. Review after the next matured 20-day monthly holdout.

Not approved yet:

- promoting the 20-day router to production;
- using the 20-day router for same-type asset ranking;
- introducing a more complex black-box model;
- letting shadow output affect Jarvis primary stance, expert actions, or
  phone-summary language;
- changing model defaults based on one 2026 sample.

### CEO Acceptance Bar

This phase succeeds if Jarvis becomes more trustworthy, not more exciting.

The key acceptance question is:

> Can Jarvis explain why a signal is useful only for allocation bias, only for
> observation, or not useful at all?

If yes, the system is moving toward a durable model-reliability platform. If
not, it risks turning replay research into another overfit prediction layer.
