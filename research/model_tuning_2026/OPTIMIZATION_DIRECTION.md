# Model Optimization Direction From 2026 Replay Experiments

Generated: 2026-05-25

This report summarizes isolated research under `research/model_tuning_2026/`.
The operational SQLite database was used read-only. The evidence comes from
2026 replay run `1`, with matured replay predictions only.

## Evidence Base

- Exploratory replay samples: 255,201 matured rows across 5/20/60 day horizons.
- Routing/gate validation: train <= 2026-03-31, holdout >= 2026-04-01.
- Monthly walk-forward control layer: router weights use only outcomes matured
  before the first day of each prediction month.
- Focused 20-day experiment: 96,588 matured 20-day rows and 257,568 shadow
  strategy predictions.

## Optimization Decisions

### 1. Keep 5-Day Baseline; Do Not Add Router

The 5-day dynamic router is a negative optimization in holdout.

| strategy | holdout n | direction | Rank IC | bucket | MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| fixed baseline | 13,570 | 0.651 | 0.149 | 0.021 | 0.051 |
| walk-forward router | 13,570 | 0.589 | 0.072 | 0.008 | 0.053 |

Decision:

- Keep `baseline_mean_v1` as the 5-day production default.
- Add monitoring only: monthly direction accuracy, Rank IC, bucket spread, and
  high-confidence wrong rate.
- Do not enable dynamic model routing for 5-day predictions.

### 2. Use 20-Day Router Only As A Conservative Shadow Layer

The 20-day signal has the strongest evidence for a small control-layer
improvement, but only when the router stays baseline-heavy.

Holdout strategy metrics:

| strategy | direction | MAE | Rank IC | bucket | top-bottom decile | high-conf wrong |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed baseline | 0.708 | 0.147 | 0.326 | 0.131 | 0.134 | 0.286 |
| fixed momentum | 0.698 | 0.134 | 0.242 | 0.098 | 0.135 | 0.302 |
| router floor70 cap05 | 0.721 | 0.144 | 0.350 | 0.136 | 0.149 | 0.274 |
| router floor80 cap10 | 0.717 | 0.145 | 0.349 | 0.136 | 0.148 | 0.278 |

Preferred shadow candidate:

- `router_floor70_cap05`
- Mean baseline weight: 0.930
- Mean momentum weight: 0.035
- Mean risk-adjusted weight: 0.035
- Mean monthly turnover: 0.062
- Max monthly turnover: 0.095

Decision:

- Run `router_floor70_cap05` as a shadow 20-day route.
- Do not replace the operational 20-day baseline yet.
- Promotion gate: require at least one additional matured monthly holdout where
  Rank IC, bucket spread, direction accuracy, and high-confidence wrong rate are
  all no worse than fixed baseline.

### 3. Treat 20-Day Signal As Asset-Type Allocation, Not Within-Type Ranking

The focused 20-day decomposition changes the interpretation of the signal.
Aggregate 20-day holdout looks strong, but within ETF/fund/stock groups the
ranking signal is weak or negative.

Holdout decomposition:

| strategy | component | n | direction | Rank IC | bucket |
| --- | --- | ---: | ---: | ---: | ---: |
| fixed baseline | asset-type allocation | 56 | 0.679 | 0.454 | 0.109 |
| fixed baseline | within asset type | 6,423 | 0.712 | -0.146 | -0.026 |
| router floor70 cap05 | asset-type allocation | 56 | 0.679 | 0.497 | 0.117 |
| router floor70 cap05 | within asset type | 6,423 | 0.724 | -0.130 | -0.027 |

Decision:

- Use 20-day output to bias broad opportunity-pool allocation across asset
  types or product buckets.
- Do not use 20-day scores as the primary same-type asset ranking signal.
- Product copy should say "中期大类倾向/机会方向" rather than "同类资产精选".

### 4. Keep 60-Day Baseline Until More Outcomes Mature

There is no April/May independent 60-day holdout yet because the horizon has
not matured. Full-sample evidence still favors baseline over risk-adjusted or
ensemble variants.

Decision:

- Keep `baseline_mean_v1` as the 60-day default.
- Keep `risk_adjusted_factor_v1` as an observation candidate only.
- Re-run this analysis when new 60-day outcomes mature.

### 5. Do Not Expose Raw Confidence As Predictive Certainty

Raw confidence is overconfident:

- 5-day holdout raw high-confidence wrong rate: about 0.345.
- 20-day holdout raw high-confidence wrong rate: about 0.286.
- 20-day router floor70 cap05 improves this to 0.274, but that is still too
  high for "high confidence" product language.

The first calibrated confidence tier experiment also failed to produce useful
positive tiers: all 20-day holdout rows stayed in the low tier.

Decision:

- Remove or avoid strong "高置信" language for these model outputs.
- Use confidence as a caution/freshness/reliability label, not as probability
  of being right.
- Product tiers should be conservative:
  - `观察`: enough data, but not a strong claim.
  - `谨慎`: model disagreement or weak recent evidence.
  - `暂不强调`: high-conf wrong rate remains elevated.

## Implementation Order

1. Add a model-health monitoring asset for `model_version + horizon + month`.
   It should compute direction accuracy, Rank IC, bucket spread, MAE, and raw
   high-confidence wrong rate.

2. Add a 20-day shadow route named `router_floor70_cap05`.
   It should not affect operational predictions yet. Persist shadow metrics and
   compare it against fixed baseline after each monthly maturity update.

3. Change product interpretation for 20-day predictions.
   Treat them as broad allocation/opportunity bias, not same-type asset
   selection.

4. Downgrade confidence language.
   Do not display raw confidence as certainty. Until calibration separates
   quality tiers in holdout, use cautious labels only.

5. Revisit 60-day models after enough April/May 60-day outcomes mature.

## Stop Conditions

- Stop 5-day router work unless a future replay shows fixed baseline losing on
  at least two consecutive matured months.
- Stop 20-day router promotion if the shadow route fails to beat fixed baseline
  on Rank IC or bucket spread in the next matured month.
- Stop confidence tier promotion if tiers do not separate realized direction
  accuracy or high-confidence wrong rate in holdout.
- Stop within-type 20-day ranking usage until within-type Rank IC and bucket
  spread become positive by asset type.
