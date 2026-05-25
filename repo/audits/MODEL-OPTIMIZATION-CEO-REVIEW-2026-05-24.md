# Investment Forecasting Model Optimization CEO Review

Date: 2026-05-24

Status: CEO review draft

## Executive Verdict

The current project has matured into an auditable local quantitative research
platform: data ingestion, feature calculation, forecasts, backtests, model
monitoring, expert committee simulations, Jarvis synthesis, news evidence, and
phone notifications are already connected.

The model layer, however, is still an MVP baseline. The main production
forecast is `baseline_mean_v1`, a simple extrapolation of recent average
returns. Current stored evidence shows direction accuracy around 51% across
5/20/60 day horizons, which is close to random, and the latest model monitoring
state is `degraded`.

The recommended next phase is therefore not "add a more powerful AI model".
It should be a model reliability upgrade:

> Move from single-model point-return prediction to multi-model cross-sectional
> ranking, probability calibration, risk confidence gates, and expert
> multi-model evidence review.

## Industry Context

Mature quantitative investing generally does not rely on accurately predicting
the exact future return of one asset. It uses many weak signals to improve
relative ranking, bucket-level performance, risk-adjusted return, and portfolio
decision quality.

The strongest practical lesson from modern machine-learning asset pricing is
that ML models are useful mostly because they capture nonlinear feature
interactions and cross-sectional differences. They do not remove the high-noise,
low-signal nature of financial return prediction.

Reference:

- Gu, Kelly, and Xiu, "Empirical Asset Pricing via Machine Learning":
  https://academic.oup.com/rfs/article/33/5/2223/5758276

Financial validation also needs stronger leakage controls than ordinary random
splits. For 20/60 day labels, overlapping outcome windows can create hidden
leakage. Purged and embargoed validation is a common financial ML pattern.

References:

- mlfinlab cross validation:
  https://random-docs.readthedocs.io/en/latest/implementations/cross_validation.html
- scikit-learn `TimeSeriesSplit` with `gap`:
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

Recent time-series foundation models such as Google TimesFM and Amazon Chronos
are worth tracking as offline challengers, but they should not become the
near-term mainline model. The project's current data scale, asset coverage, and
need for auditability favor structured factor and tree-ranking models first.

References:

- Google Research TimesFM:
  https://research.google/blog/a-decoder-only-foundation-model-for-time-series-forecasting/
- Amazon Chronos:
  https://www.amazon.science/publications/chronos-learning-the-language-of-time-series

## Current System Assessment

### Strengths

- The platform is local-first, reproducible, and auditable.
- Data already covers stocks, ETFs, funds, indexes, capital flow, fund holdings,
  market state, macro observations, and news evidence.
- Rolling backtests already reduce obvious future leakage.
- Jarvis can synthesize model output, expert views, market evidence, capital
  flow, user risk preferences, and evidence freshness.
- The expert committee has persisted personas, virtual portfolios, plans,
  simulated transactions, scorecards, reviews, and lifecycle states.
- Safety language and evidence links are built into advice, expert plans, and
  Jarvis outputs.

### Gaps

- The main forecast is still a single simple baseline model.
- The objective is still too close to point-return prediction, which is one of
  the hardest and noisiest financial prediction tasks.
- Stored model calibration evidence is not yet mature enough to justify trust.
- Current direction accuracy is around 51%, close to random.
- The expert committee has too little live valuation history to prove skill.
- AI provider analysis currently falls back to deterministic logic unless a real
  provider is configured.
- Jarvis is a good synthesis layer, but it should become stricter about model
  health and confidence gating before presenting stronger conclusions.

## Recommended Optimization Direction

### 1. Reframe The Prediction Target

The system should keep `expected_return`, but it should stop treating point
return prediction as the primary product signal.

The next model layer should produce:

- future 5/20/60 day return,
- calibrated probability of positive return,
- cross-sectional rank within comparable assets,
- risk-adjusted expected return,
- top-bucket and bottom-bucket evidence,
- model health and confidence metadata.

The main user-facing question should become:

> Which assets rank relatively better under current evidence, and how reliable
> is that ranking?

Not:

> Exactly how much will this asset rise?

### 2. Build A Multi-Model Candidate Pool

The current baseline should remain as the floor. New candidates should compete
against it under the same evaluation framework.

Recommended model families:

- `baseline_mean_v1`: current minimum baseline.
- `momentum_reversal_v1`: short-term momentum, medium-term reversal, and
  volatility penalty.
- `risk_adjusted_factor_v1`: interpretable linear or ridge factor model.
- `tree_ranker_v1`: LightGBM or XGBoost cross-sectional ranking model.
- `probability_calibrator_v1`: calibrated positive-return probability model.
- `ensemble_v1`: promoted only if stable out-of-sample evidence beats the
  baseline.

Tree models are the practical near-term frontier for this project because they
work well on structured tabular features, support feature importance, and are
less demanding than deep learning models. LightGBM also supports ranking
objectives such as LambdaRank.

Reference:

- LightGBM `LGBMRanker`:
  https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRanker.html

### 3. Upgrade Financial Validation

The next validation system should report more than direction hit rate and mean
return error.

Recommended metrics:

- IC and Rank IC,
- top 20% vs bottom 20% bucket return spread,
- same-category ranking performance,
- horizon-specific performance for 5/20/60 days,
- asset-type performance for stocks, ETFs, funds, and indexes,
- benchmark excess return,
- maximum drawdown,
- volatility,
- turnover,
- probability calibration curves,
- performance by market regime.

Only models that are stable out of sample should be eligible for Jarvis primary
conclusions.

### 4. Add Expert Multi-Model Evidence Review

The expert committee can support multi-model synthesis, but the role of experts
should be precise:

> Experts are style-biased reviewers of model evidence, not voting machines that
> can bypass model health checks.

Each model should emit a standard evidence packet:

- `model_version`
- `horizon_days`
- `expected_return`
- `up_probability`
- `rank_score`
- `confidence`
- `validation_status`
- `recent_rank_ic`
- `degraded_reason`
- `evidence_ids`

Expert styles can then weight evidence differently:

- Trend expert: momentum models, ranking models, trend persistence.
- Defensive expert: risk-adjusted models, downside risk, drawdown control.
- Balanced expert: ensemble output, calibrated probability, cross-model
  agreement.
- Macro expert: market state, capital flow, themes, news-derived aggregate
  signals.

All expert reasoning must still respect confidence gates. If a model is
`degraded`, the expert can cite it only as watch-list evidence, not as a strong
action driver.

### 5. Upgrade Jarvis Into A Model Risk Officer

Jarvis should not merely summarize model and expert output. It should actively
down-rank weak or stale evidence.

Recommended confidence-gate behavior:

- If a model is `degraded`, related asset signals become watch-only.
- If a horizon has negative Rank IC, that horizon is excluded from the primary
  conclusion.
- If an asset type lacks enough samples, Jarvis avoids strong ranking language.
- If expert history is immature, expert views remain context, not weighted
  conviction.
- If multiple weak models agree, Jarvis does not amplify the conclusion.
- If models disagree, Jarvis explains which model families disagree and why.

The goal is for Jarvis to answer:

- Which evidence can be trusted?
- Which horizon is currently usable?
- Which asset type has real signal?
- Which model is degraded?
- When should the assistant stay defensive?

## Feasibility Assessment

### High Feasibility

- Label redesign.
- Cross-sectional ranking.
- Factor models.
- Tree ranking models.
- Walk-forward validation with gap or purge/embargo.
- Jarvis confidence-gate upgrades.
- Expert multi-model evidence review.

### Medium Feasibility

- News-derived aggregate features.
- Capital-flow continuity features.
- Expert-performance-derived weak features.
- Automatic model promotion and demotion.

### Low Near-Term Priority

- Transformer forecasting.
- TimesFM or Chronos as production models.
- Multimodal financial models.
- Reinforcement-learning portfolio allocation.

These should remain research challengers until the simpler structured models
prove their ceiling.

## Recommended CEO-Level Decision

Approve the next phase as:

> Model Reliability Upgrade

The phase should focus on:

1. prediction target redesign,
2. financial-grade validation,
3. multi-model candidate comparison,
4. expert multi-model evidence review,
5. Jarvis model confidence gates.

The phase should not be framed as:

- guaranteed prediction improvement,
- direct trading automation,
- AI replacing quantitative validation,
- deep learning first,
- expert committee voting as investment truth.

The strategic goal is to make the system more honest, more measurable, and more
useful:

> Know which signals are real, which are weak, which are stale, and when Jarvis
> must say "observe only".

## CEO Guidance Addendum

The financial expert proposal is directionally approved, but product language
and implementation sequencing should be tightened. This phase must not be sold
internally or externally as "stronger prediction". It should be framed as
"model reliability": improving how the system ranks evidence, measures signal
quality, and prevents Jarvis from over-amplifying noisy forecasts.

### Product Principle

Jarvis should become more selective, not more aggressive.

The desired user outcome is not:

> Jarvis finds the next high-return asset.

The desired user outcome is:

> Jarvis explains which evidence is currently usable, which evidence is weak,
> which assets are worth observing, and why the assistant is staying cautious
> when model quality is poor.

This distinction matters because the product is an investment research
assistant, not an automated trading or return-guarantee system.

### Required Model Promotion Gates

Before any new model can become part of Jarvis's primary daily conclusion, it
must pass explicit promotion criteria. At minimum:

- It beats `baseline_mean_v1` across multiple walk-forward windows.
- Rank IC is positive and reasonably stable for the target horizon.
- Top-bucket minus bottom-bucket return spread is positive after costs or
  conservative assumptions.
- Drawdown and downside-risk behavior do not materially worsen relative to the
  baseline.
- Performance is reported by asset type and same-category peer group, not only
  as one aggregate score.
- The model is not in a `degraded` monitoring state.
- The model output is linked to persisted evidence IDs.
- Jarvis confidence gates do not downgrade the model's key signals to
  watch-only.

If a candidate only works in one market regime, asset type, or horizon, it may
be exposed as contextual evidence for that scope, but it should not become the
global default.

### Jarvis Presentation Rules

The WebUI and phone summary must avoid letting large raw expected-return values
dominate the experience. Jarvis should:

- Prefer relative ranking, calibrated probability, and risk-adjusted language
  over point-return claims.
- Downgrade low-confidence or outlier forecasts into observation signals.
- Explain when a horizon is excluded because recent validation is weak.
- State when expert performance history is immature and should not be treated
  as skill evidence.
- Show model disagreement as a product feature: disagreement tells the user
  where uncertainty is concentrated.

High-return numbers can remain in evidence views, but the daily brief should
translate them into conservative product language.

### Expert Committee Guidance

Experts should review model evidence through a standard packet rather than
free-form access to raw rows. The expert role is to interpret evidence through
style-specific lenses:

- Trend expert: momentum, rank improvement, trend persistence.
- Defensive expert: drawdown, volatility, downside risk, degraded warnings.
- Balanced expert: cross-model agreement, calibrated probabilities, risk
  adjusted scores.
- Macro expert: market state, capital flow, theme pressure, and retrieved news
  evidence.

Experts must not override degraded model health. If a model is degraded, the
expert can cite it as a reason to monitor, hedge, or stay patient, not as a
strong action driver.

### Recommended Next Task Sequence

Create the next phase as `Model Reliability Upgrade` with thin implementation
slices:

1. `Prediction Target Redesign`
   - Add model outputs for cross-sectional rank, same-category rank,
     calibrated up probability, and risk-adjusted score.
   - Keep `expected_return`, but remove it from the role of primary product
     signal.

2. `Financial Validation Upgrade`
   - Add IC, Rank IC, bucket spread, same-category performance, regime
     performance, and horizon-level validation.
   - Add purged or embargoed validation for overlapping 20/60 day labels.

3. `Multi-Model Candidate Pool`
   - Add `momentum_reversal_v1` and `risk_adjusted_factor_v1` before tree
     models.
   - Add `tree_ranker_v1` only after validation reporting can prove whether it
     improves ranking quality.

4. `Model Evidence Packet`
   - Standardize the evidence shape consumed by experts and Jarvis:
     `model_version`, `horizon_days`, `expected_return`, `up_probability`,
     `rank_score`, `confidence`, `validation_status`, `recent_rank_ic`,
     `degraded_reason`, and `evidence_ids`.

5. `Jarvis Model Risk Gates`
   - Ensure degraded, stale, low-confidence, negative-Rank-IC, and
     insufficient-sample signals are automatically downgraded before they
     appear in the daily brief or phone summary.

### Explicit Non-Priorities

Do not prioritize these until the structured reliability layer proves useful:

- Transformer or foundation time-series models as production defaults.
- Reinforcement-learning portfolio allocation.
- More experts or expert voting logic.
- Live trading or brokerage integration.
- UI expansion beyond the five Jarvis primary entries.
- Any claim that model optimization produces reliable directional prediction.

### CEO Acceptance Bar

This phase is successful only if Jarvis becomes more trustworthy in weak-signal
conditions. A good result may be that Jarvis recommends fewer actions, labels
more signals as watch-only, and explains model uncertainty better.

The acceptance question is:

> Can Jarvis tell the user why it should not trust a tempting signal?

If the answer is yes, the model optimization phase is moving the product toward
the correct long-term goal.
