# TASK-048: Jarvis Synthesis Engine

## Status

completed

## Purpose

Build the Jarvis synthesis service that combines system market information,
prediction models, expert plans, expert scores, expert current returns, and
user preferences into a simple daily recommendation.

## Scope

- Read latest market snapshot, macro observations, task health, model
  predictions, backtests/model quality, expert plans, expert scorecards,
  expert virtual portfolios, and active user preference.
- Generate:
  - today's focus directions;
  - one-line stance;
  - model prediction summary;
  - one expert summary per active expert;
  - disagreement explanation;
  - combined recommendation;
  - risk and freshness warnings.
- Reuse compliance checks from advice generation.
- Record source evidence IDs.
- Add CLI/daily workflow entry point behind explicit command or flag.

## Non-Scope

- No real-money trading instruction.
- No LLM-only hidden memory.
- No phone notification wiring.

## Files Likely To Change

- `src/investment_forecasting/jarvis/`
- `src/investment_forecasting/advice/generator.py`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/cli.py`
- `tests/test_jarvis.py`
- `tests/test_daily_workflow.py`

## Acceptance Criteria

- Jarvis can generate a daily brief from persisted evidence.
- Output includes model forecasts and every active expert's stance, score, and
  current return.
- Jarvis explains model/expert disagreement when present.
- Missing or stale evidence appears as a warning, not as hidden failure.
- Compliance tests reject guaranteed-return or certain-profit language.

## Depends On

- `TASK-047`
- `TASK-032`
- `TASK-033`
- `TASK-038`
- `TASK-039`

## Implementation Notes

- Added `src/investment_forecasting/jarvis/synthesis.py` as the deterministic
  Jarvis synthesis service over persisted evidence.
- The service gathers latest market snapshot, macro observations, task logs,
  model predictions, backtest quality, active expert plans, expert scorecards,
  virtual valuations, and active user preference.
- Generated briefs include focus directions, one-line stance, model summary,
  one row per active expert, model/expert disagreement explanation, combined
  recommendation, risk warnings, source evidence IDs, missing evidence, and
  stale evidence.
- Added `investment-forecasting jarvis generate` and the explicit
  `daily run --generate-jarvis` flag. Daily workflow does not generate Jarvis
  unless the flag is supplied.
- Evidence references now store top model-prediction IDs plus the total
  prediction count, avoiding giant ID lists in product output.

## Verification

- `python3 -m pytest tests/test_jarvis.py tests/test_daily_workflow.py`
- `python3 -m pytest`
- `PYTHONPATH=src python3 -m investment_forecasting.cli db init --db data/investment_forecasting.sqlite3`
- `PYTHONPATH=src python3 -m investment_forecasting.cli jarvis generate --db data/investment_forecasting.sqlite3 --date 20260523`
- `scripts/restart_web.sh`
