# Walk-Forward Control Layer Experiment

Generated: 2026-05-25

This experiment opens the source replay database read-only. It simulates monthly model routing using only outcomes whose `outcome_date` is before the first day of each prediction month.

## Scope

- Source DB: `data/investment_forecasting.sqlite3`
- Output DB: `research/model_tuning_2026/model_tuning_research.sqlite3`
- Replay run: `1`
- Experiment ID: `1`
- Matured samples: 255,201
- Holdout split: prediction_date >= `2026-04-01`

## Holdout Metrics

| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile | raw high-conf wrong | cooled high-conf count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_baseline | 5 | 13,570 | 0.651 | 0.051 | 0.149 | 0.021 | 0.012 | 0.345 | 0 |
| fixed_prior_route | 5 | 13,570 | 0.651 | 0.051 | 0.149 | 0.021 | 0.012 | 0.345 | 0 |
| wf_blend_20_40_60_cap10 | 5 | 13,570 | 0.588 | 0.053 | 0.074 | 0.008 | -0.002 | 0.410 | 0 |
| wf_w40_cap10 | 5 | 13,570 | 0.589 | 0.053 | 0.072 | 0.008 | -0.002 | 0.409 | 0 |
| fixed_baseline | 20 | 6,507 | 0.708 | 0.147 | 0.326 | 0.131 | 0.134 | 0.286 | 0 |
| fixed_prior_route | 20 | 6,507 | 0.698 | 0.134 | 0.242 | 0.098 | 0.135 | 0.302 | 0 |
| wf_blend_20_40_60_cap10 | 20 | 6,507 | 0.714 | 0.142 | 0.352 | 0.127 | 0.152 | 0.282 | 0 |
| wf_w40_cap10 | 20 | 6,507 | 0.714 | 0.142 | 0.352 | 0.127 | 0.152 | 0.282 | 0 |

## Full-Sample Metrics

| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile | raw high-conf wrong | cooled high-conf count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_baseline | 5 | 39,261 | 0.552 | 0.042 | 0.032 | 0.004 | 0.004 | 0.446 | 0 |
| fixed_prior_route | 5 | 39,261 | 0.552 | 0.042 | 0.032 | 0.004 | 0.004 | 0.446 | 0 |
| wf_blend_20_40_60_cap10 | 5 | 39,261 | 0.519 | 0.043 | -0.006 | -0.003 | -0.004 | 0.481 | 0 |
| wf_w40_cap10 | 5 | 39,261 | 0.519 | 0.043 | -0.006 | -0.003 | -0.003 | 0.481 | 0 |
| fixed_baseline | 20 | 32,196 | 0.569 | 0.106 | -0.009 | -0.003 | -0.005 | 0.426 | 0 |
| fixed_prior_route | 20 | 32,196 | 0.509 | 0.132 | 0.068 | 0.038 | 0.061 | 0.491 | 0 |
| wf_blend_20_40_60_cap10 | 20 | 32,196 | 0.562 | 0.105 | 0.009 | 0.003 | 0.006 | 0.434 | 0 |
| wf_w40_cap10 | 20 | 32,196 | 0.562 | 0.105 | 0.009 | 0.003 | 0.006 | 0.434 | 0 |
| fixed_baseline | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 | 0.256 | 0 |
| fixed_prior_route | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 | 0.256 | 0 |
| wf_blend_20_40_60_cap10 | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 | 0.256 | 0 |
| wf_w40_cap10 | 60 | 13,610 | 0.744 | 0.183 | 0.329 | 0.185 | 0.154 | 0.256 | 0 |

## Best Holdout Candidate By Horizon

| horizon | strategy | Rank IC | bucket | direction | MAE |
| ---: | --- | ---: | ---: | ---: | ---: |
| 5 | fixed_baseline | 0.149 | 0.021 | 0.651 | 0.051 |
| 20 | wf_w20_cap10 | 0.352 | 0.127 | 0.714 | 0.142 |

## Router Turnover

| strategy | horizon | mean monthly turnover | max monthly turnover | mean baseline | mean momentum | mean risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wf_blend_20_40_60_cap10 | 5 | 0.151 | 0.182 | 0.687 | 0.168 | 0.145 |
| wf_w40_cap10 | 5 | 0.152 | 0.182 | 0.683 | 0.171 | 0.146 |
| wf_blend_20_40_60_cap10 | 20 | 0.121 | 0.182 | 0.797 | 0.104 | 0.099 |
| wf_w40_cap10 | 20 | 0.122 | 0.182 | 0.796 | 0.103 | 0.100 |
| wf_blend_20_40_60_cap10 | 60 | 0.035 | 0.142 | 0.972 | 0.009 | 0.019 |
| wf_w40_cap10 | 60 | 0.035 | 0.142 | 0.972 | 0.009 | 0.019 |

## Confidence Cooling At 0.70 Threshold

| split | strategy | horizon | type | coverage | wrong rate | count |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| holdout | fixed_baseline | 5 | cooled | 0.000 |  | 0 |
| holdout | fixed_baseline | 5 | raw | 0.980 | 0.346 | 13,303 |
| holdout | wf_blend_20_40_60_cap10 | 5 | cooled | 0.000 |  | 0 |
| holdout | wf_blend_20_40_60_cap10 | 5 | raw | 0.980 | 0.411 | 13,303 |
| holdout | fixed_baseline | 20 | cooled | 0.000 |  | 0 |
| holdout | fixed_baseline | 20 | raw | 0.978 | 0.288 | 6,363 |
| holdout | wf_blend_20_40_60_cap10 | 20 | cooled | 0.000 |  | 0 |
| holdout | wf_blend_20_40_60_cap10 | 20 | raw | 0.978 | 0.283 | 6,363 |

## Readout

- Monthly walk-forward routing is safer than a hard global switch, but it is not automatically better than fixed baseline. Treat it as a shadow control layer until it beats baseline on Rank IC/bucket without excessive turnover.
- 20-day remains the main instability zone. The control layer should prefer conservative smoothing and recency confirmation rather than a fast 20-day router.
- Confidence cooling is directionally justified, but the current threshold can become too strict and reduce coverage sharply. A calibrated three-band display is safer than a single high-confidence cutoff.
- 60-day still has limited late-period maturity. Do not promote a 60-day ensemble until more matured April/May outcomes arrive.

## Reproduce

```bash
python3 research/model_tuning_2026/walk_forward_control_layer_experiment.py \
  --source-db data/investment_forecasting.sqlite3 \
  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \
  --replay-run-id 1
```
