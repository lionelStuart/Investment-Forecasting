# Routing and Gate Validation Experiment

Generated: 2026-05-25

This is an isolated research artifact. The source database was opened read-only and all experiment outputs were written to the research database.

## Scope

- Source DB: `data/investment_forecasting.sqlite3`
- Output DB: `research/model_tuning_2026/model_tuning_research.sqlite3`
- Replay run: `1`
- Experiment ID: `2`
- Matured samples: 255,201
- Train split: prediction_date <= `2026-03-31`, rows 194,970
- Holdout split: prediction_date >= `2026-04-01`, rows 60,231

## Holdout Metrics

| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile | high-conf wrong | cooled high-conf wrong |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_all | 5 | 13,570 | 0.651 | 0.051 | 0.149 | 0.021 | 0.012 | 0.345 |  |
| ensemble_60_route | 5 | 13,570 | 0.651 | 0.051 | 0.149 | 0.021 | 0.012 | 0.345 |  |
| ranking_route | 5 | 13,570 | 0.651 | 0.051 | 0.149 | 0.021 | 0.012 | 0.345 |  |
| risk_60_route | 5 | 13,570 | 0.651 | 0.051 | 0.149 | 0.021 | 0.012 | 0.345 |  |
| baseline_all | 20 | 6,507 | 0.708 | 0.147 | 0.326 | 0.131 | 0.134 | 0.286 |  |
| ensemble_60_route | 20 | 6,507 | 0.698 | 0.134 | 0.242 | 0.098 | 0.135 | 0.302 |  |
| ranking_route | 20 | 6,507 | 0.698 | 0.134 | 0.242 | 0.098 | 0.135 | 0.302 |  |
| risk_60_route | 20 | 6,507 | 0.698 | 0.134 | 0.242 | 0.098 | 0.135 | 0.302 |  |

## Full-Sample 60-Day Metrics

The 60-day horizon has no April/May holdout rows because those predictions had not matured yet.

| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_all | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 |
| direction_route | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 |
| ensemble_60_route | 60 | 13,610 | 0.729 | 0.188 | 0.321 | 0.181 | 0.156 |
| gated_ranking_route | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 |
| ranking_route | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 |
| risk_60_route | 60 | 13,610 | 0.686 | 0.199 | 0.307 | 0.173 | 0.155 |

## Gate Decisions From Train Split

| model | horizon | n | train direction | train Rank IC | train bucket | enabled |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| baseline_mean_v1 | 5 | 25,691 | 0.500 | -0.046 | -0.008 | no |
| momentum_reversal_v1 | 5 | 25,691 | 0.448 | -0.119 | -0.011 | no |
| risk_adjusted_factor_v1 | 5 | 25,691 | 0.483 | -0.075 | -0.010 | no |
| baseline_mean_v1 | 20 | 25,689 | 0.534 | -0.062 | -0.023 | no |
| momentum_reversal_v1 | 20 | 25,689 | 0.461 | -0.101 | -0.025 | no |
| risk_adjusted_factor_v1 | 20 | 25,689 | 0.437 | -0.124 | -0.040 | no |
| baseline_mean_v1 | 60 | 13,610 | 0.744 | 0.329 | 0.185 | yes |
| momentum_reversal_v1 | 60 | 13,610 | 0.500 | -0.100 | -0.062 | no |
| risk_adjusted_factor_v1 | 60 | 13,610 | 0.686 | 0.307 | 0.173 | yes |

## Readout

- 5-day: `baseline_mean_v1` is still the best short-horizon default in the April/May holdout, but the January/March train split was negative. Do not use a static old-period gate to disable this horizon.
- 20-day: the earlier full-sample preference for `momentum_reversal_v1` is not stable in the April/May holdout. Baseline wins on direction, Rank IC, and bucket spread in holdout, while momentum has lower MAE. This needs rolling, recency-weighted gating rather than a single global route.
- 60-day: no independent April/May holdout is available yet. Full-sample evidence still supports `baseline_mean_v1` and `risk_adjusted_factor_v1` as ranking candidates, with baseline slightly stronger.
- Train-derived hard gates are too brittle for 5-day and 20-day because regime changed after March. Use rolling monthly diagnostics as a weight/cooling input, not a binary production switch.
- Confidence cooling reduces qualifying high-confidence rows to zero at the 0.70 threshold for holdout 5-day/20-day, which confirms raw confidence is not safe as product-facing certainty.

## Reproduce

```bash
python3 research/model_tuning_2026/validate_routing_and_gates.py \
  --source-db data/investment_forecasting.sqlite3 \
  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \
  --replay-run-id 1
```
