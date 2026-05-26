# 2026 Model Tuning Exploratory Research

Generated: 2026-05-25

This is an isolated research artifact. The source database was opened read-only:
`data/investment_forecasting.sqlite3`. All computed results were written to:
`research/model_tuning_2026/model_tuning_research.sqlite3`.

## Scope

- Source replay run: `model_replay_runs.id = 1`
- Replay window: 2026-01-01 to 2026-05-22
- Matured samples analyzed: 255,201
- Pending samples observed but excluded from accuracy metrics: 119,487
- Skipped samples observed but excluded from accuracy metrics: 234
- Models: `baseline_mean_v1`, `momentum_reversal_v1`,
  `risk_adjusted_factor_v1`
- Horizons: 5, 20, 60 trading days

## Model / Horizon Summary

| model | horizon | n | direction | MAE | median AE | mean actual | mean pred | Rank IC | bucket | high-conf wrong | downside miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 5 | 39,261 | 0.552 | 0.042 | 0.031 | 0.011 | 0.009 | 0.032 | 0.004 | 0.436 | 0.146 |
| baseline | 20 | 32,196 | 0.569 | 0.106 | 0.079 | 0.043 | 0.032 | -0.009 | -0.003 | 0.416 | 0.171 |
| baseline | 60 | 13,610 | 0.744 | 0.183 | 0.135 | 0.127 | 0.114 | 0.329 | 0.185 | 0.252 | 0.146 |
| momentum/reversal | 5 | 39,261 | 0.488 | 0.049 | 0.035 | 0.011 | 0.006 | -0.015 | 0.001 | 0.500 | 0.160 |
| momentum/reversal | 20 | 32,196 | 0.509 | 0.132 | 0.097 | 0.043 | 0.019 | 0.068 | 0.038 | 0.479 | 0.173 |
| momentum/reversal | 60 | 13,610 | 0.500 | 0.334 | 0.253 | 0.127 | 0.032 | -0.100 | -0.062 | 0.492 | 0.160 |
| risk-adjusted | 5 | 39,261 | 0.429 | 0.048 | 0.036 | 0.011 | -0.018 | -0.025 | -0.001 | 0.559 | 0.065 |
| risk-adjusted | 20 | 32,196 | 0.430 | 0.113 | 0.075 | 0.043 | -0.020 | -0.075 | -0.023 | 0.556 | 0.077 |
| risk-adjusted | 60 | 13,610 | 0.686 | 0.199 | 0.150 | 0.127 | 0.028 | 0.307 | 0.173 | 0.309 | 0.080 |

## Main Findings

1. `baseline_mean_v1` is the best short-horizon default.
   Its 5-day slice is the only short-horizon slice with positive Rank IC and
   positive top/bottom bucket spread. It is still overconfident, so confidence
   should be cooled before product language treats it as a strong signal.

2. 20-day ranking is not solved by the current baseline.
   Baseline 20-day has acceptable direction accuracy but negative Rank IC and
   bucket spread. Momentum/reversal 20-day has positive ranking metrics, but
   point-return magnitude is too noisy. Use it as a ranking candidate, not as a
   direct expected-return forecast.

3. 60-day ranking has signal, but return amplitude is too aggressive/noisy.
   Baseline and risk-adjusted 60-day both have strong Rank IC and bucket
   spread. Their MAE remains large, so the research direction should separate
   ranking/selection from point-return magnitude.

4. Current confidence is not calibrated.
   Most mature rows fall into the 0.95-1.00 confidence bin with actual
   correctness far below 0.95. This makes confidence more like "history length
   completeness" than predictive certainty.

5. Up-probability is shared across models and is not model-specific.
   The probability calibration table is identical across model versions for a
   given horizon, indicating `up_probability` is currently derived from recent
   historical positive-return frequency rather than candidate-model output.

6. The naive amplitude shrinkage experiment often picks scale `0.0`.
   This should not be interpreted as "predict zero return" being a good model.
   It means current point-return magnitudes are weak enough that MAE improves
   when alpha magnitude is removed. Ranking metrics are a better objective for
   model tuning than raw point-return MAE in this phase.

## Recommended Experiments

1. Add horizon-specific model routing.
   - 5-day primary: `baseline_mean_v1`
   - 20-day ranking candidate: `momentum_reversal_v1`, gated by positive Rank IC
   - 60-day ranking candidates: `baseline_mean_v1` and
     `risk_adjusted_factor_v1`
   - Verification: Rank IC and bucket spread remain positive on the next
     isolated replay.

2. Split alpha ranking from return magnitude.
   - Use expected return only for relative sorting after per-horizon
     normalization.
   - Apply a separate calibrated return-magnitude layer.
   - Verification: bucket spread stays positive while MAE does not worsen.

3. Add confidence cooling.
   - Replace confidence based mostly on input-window length with a function of
     recent direction accuracy, Rank IC, bucket spread, asset type, and horizon.
   - Verification: high-confidence wrong-direction rate falls below 15%.

4. Calibrate probability by horizon.
   - Keep probability bins per horizon; do not treat the current probability as
     model-specific until the probability function changes.
   - Verification: max probability calibration error <= 0.08.

5. Add model/horizon degradation gates.
   - Disable ranking contribution when Rank IC < 0 or bucket spread < 0.
   - Verification: gated model does not reduce top/bottom spread in a replay
     holdout.

6. Add asset-type and theme gates after a second replay.
   - ETFs and funds show many negative within-category ranking slices.
   - Do not hard-code these gates from one sample; repeat on another period or
     use rolling monthly splits.

## Tables In Research DB

- `analysis_runs`: source/run metadata and coverage.
- `group_metrics`: model/horizon, asset-type, category, and month slices.
- `calibration_bins`: probability and confidence calibration bins.
- `amplitude_experiments`: return-magnitude shrinkage experiments.
- `top_errors`: largest absolute prediction errors.
- `recommendations`: ranked experiment ideas and stop conditions.

## Reproduce

```bash
python3 research/model_tuning_2026/explore_model_tuning.py \
  --source-db data/investment_forecasting.sqlite3 \
  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \
  --replay-run-id 1
```
