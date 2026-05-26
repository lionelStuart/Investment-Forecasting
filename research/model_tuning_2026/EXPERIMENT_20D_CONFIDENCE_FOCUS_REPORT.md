# Focused 20-Day Router And Confidence Experiment

Generated: 2026-05-25

This isolated experiment tests only the 20-day horizon. Monthly router weights use only outcomes already matured before the first day of each prediction month.

## Scope

- Source DB: `data/investment_forecasting.sqlite3`
- Output DB: `research/model_tuning_2026/model_tuning_research.sqlite3`
- Replay run: `1`
- Experiment ID: `2`
- Matured 20-day rows: 96,588
- Holdout split: prediction_date >= `2026-04-01`

## Holdout Strategy Metrics

| strategy | n | direction | MAE | Rank IC | bucket | top-bottom decile | raw high-conf wrong | calibrated conf |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_baseline | 6,507 | 0.708 | 0.147 | 0.326 | 0.131 | 0.134 | 0.286 | 0.474 |
| fixed_momentum | 6,507 | 0.698 | 0.134 | 0.242 | 0.098 | 0.135 | 0.302 | 0.424 |
| router_floor70_cap10 | 6,507 | 0.715 | 0.144 | 0.353 | 0.131 | 0.150 | 0.281 | 0.465 |
| router_floor80_cap10 | 6,507 | 0.717 | 0.145 | 0.349 | 0.136 | 0.148 | 0.278 | 0.468 |
| router_floor90_cap10 | 6,507 | 0.716 | 0.146 | 0.340 | 0.136 | 0.142 | 0.279 | 0.471 |
| router_no_floor_cap10 | 6,507 | 0.714 | 0.142 | 0.352 | 0.127 | 0.152 | 0.282 | 0.462 |

## Monthly Router Weights

| strategy | months | turnover | max turnover | baseline | momentum | risk-adjusted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| router_floor70_cap05 | 4 | 0.062 | 0.095 | 0.930 | 0.035 | 0.035 |
| router_floor70_cap10 | 4 | 0.098 | 0.182 | 0.881 | 0.055 | 0.065 |
| router_floor80_cap10 | 4 | 0.067 | 0.165 | 0.909 | 0.040 | 0.052 |
| router_floor90_cap10 | 4 | 0.035 | 0.100 | 0.950 | 0.021 | 0.029 |
| router_no_floor_cap10 | 4 | 0.116 | 0.182 | 0.868 | 0.066 | 0.066 |

## Holdout Confidence Tiers

| strategy | tier | n | direction | Rank IC | bucket | calibrated conf |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fixed_baseline | low | 6,507 | 0.708 | 0.326 | 0.131 | 0.474 |
| router_floor80_cap10 | low | 6,507 | 0.717 | 0.349 | 0.136 | 0.468 |

## Holdout By Asset Type

| strategy | asset type | n | direction | Rank IC | bucket | MAE |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fixed_baseline | etf | 2,099 | 0.633 | -0.147 | -0.028 | 0.167 |
| fixed_baseline | fund | 2,184 | 0.973 | -0.282 | -0.043 | 0.177 |
| fixed_baseline | stock | 2,140 | 0.522 | -0.006 | -0.006 | 0.099 |
| router_floor80_cap10 | etf | 2,099 | 0.677 | -0.098 | -0.037 | 0.163 |
| router_floor80_cap10 | fund | 2,184 | 0.950 | -0.266 | -0.037 | 0.175 |
| router_floor80_cap10 | stock | 2,140 | 0.527 | -0.027 | -0.007 | 0.099 |

## Holdout Signal Decomposition

| strategy | component | n | direction | Rank IC | bucket | top-bottom decile |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fixed_baseline | asset_type_allocation | 56 | 0.679 | 0.454 | 0.109 | -0.005 |
| fixed_baseline | within_asset_type_weighted | 6,423 | 0.712 | -0.146 | -0.026 | -0.009 |
| router_floor70_cap05 | asset_type_allocation | 56 | 0.679 | 0.497 | 0.117 | 0.027 |
| router_floor70_cap05 | within_asset_type_weighted | 6,423 | 0.724 | -0.130 | -0.027 | -0.009 |
| router_floor80_cap10 | asset_type_allocation | 56 | 0.679 | 0.499 | 0.117 | 0.027 |
| router_floor80_cap10 | within_asset_type_weighted | 6,423 | 0.720 | -0.131 | -0.027 | -0.010 |

## Readout

- The 20-day router should be conservative. Baseline-heavy router variants are the only candidates worth shadowing.
- A baseline floor prevents the router from turning into a momentum chase while still allowing small non-baseline contributions.
- Confidence should be displayed as calibrated tiers only if the tiers show monotonic or at least useful separation in holdout.
- If confidence tiers do not separate holdout quality, use them as caution labels rather than strong-signal labels.
- If asset-type allocation is positive while within-type ranking is weak, use the 20-day layer for broad allocation bias rather than individual asset ranking.

## Reproduce

```bash
python3 research/model_tuning_2026/focused_20d_confidence_experiment.py \
  --source-db data/investment_forecasting.sqlite3 \
  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \
  --replay-run-id 1
```
