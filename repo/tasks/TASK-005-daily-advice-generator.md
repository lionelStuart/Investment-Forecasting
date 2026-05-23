# TASK-005: Daily Advice Generator

## Status

completed

## Source

`SPEC-003`

## Goal

Generate structured daily advice for aggressive, balanced, and conservative risk
profiles from stored market snapshots, forecasts, backtests, and risk metrics.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-003-advice-generation.md`
- `ARCHITECTURE.md`

## Modify Scope

- Advice generation services.
- Guardrail/compliance checks.
- Persistence writes for `daily_advice`.
- Tests and fixtures.
- Project memory write-back files.

## Forbidden

- Do not generate advice without source prediction/backtest references.
- Do not use prohibited certainty language.
- Do not collapse all risk profiles into one generic answer.

## Acceptance

- A command or service call creates a daily advice record for a target date.
- Advice includes market view, risk level, assumptions, risk factors, confidence,
  and three risk-profile variants.
- Allocation ranges and add/reduce exposure triggers are present.
- Compliance checks flag prohibited language.
- Failure states write `task_logs`.

## Test Plan

- Run advice generation tests with fixture model outputs.
- Run prohibited-language guardrail tests.
- Run one local advice generation smoke test after forecasts exist.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `investment-forecasting advice generate --db ... --date ...`.
- Added `daily_advice_v1` generation from stored `model_predictions` and
  `backtest_runs`.
- Added market summary, risk level, assumptions, risk warnings, confidence,
  evidence links, and three distinct risk-profile variants.
- Added allocation ranges and add/reduce exposure triggers in `allocation_json`.
- Added compliance checks for prohibited certainty or capital-protection
  language.
- Added task-log failure handling and idempotent `daily_advice` persistence.
- Validation passed with `python3 -m pytest`.
- Smoke validation generated advice for 2026-05-23 using 9 source prediction
  records and 1 backtest run from the MVP sample database.

## Follow-Ups

- `TASK-006`: MCP tools.
- `TASK-008`: WebUI workbench can start after advice storage exists.
