# TASK-021: User Risk Preferences

## Status

completed

## Source

Updated `ROADMAP.md` backlog theme: user risk profiles and investment horizon
settings.

## Goal

Persist user risk preference and investment horizon, expose them in the WebUI
and CLI, and apply the active preference when generating daily advice.

## Required Context

- `repo/ROADMAP.md`
- `repo/specs/SPEC-003-advice-generation.md`
- `repo/specs/SPEC-006-webui-workbench.md`
- `src/investment_forecasting/advice/generator.py`
- `src/investment_forecasting/web/app.py`

## Modify Scope

- SQLite schema and repository helpers.
- CLI preference commands.
- Daily advice generation.
- WebUI settings page.
- Tests and project memory write-back.

## Forbidden

- Do not turn research guidance into direct buy/sell orders.
- Do not hide default behavior when no user preference is saved.
- Do not let UI-only settings affect advice without persistence.

## Acceptance

- `user_preferences` stores named profiles with risk profile, horizon, equity
  cap, cash floor, active flag, and notes.
- CLI can set and list preferences.
- WebUI can save an active risk setting.
- Daily advice uses the active horizon for focus assets and applies equity/cash
  constraints to allocation ranges.
- Advice evidence includes the active user preference.

## Test Plan

- Run database tests for active preference persistence.
- Run advice tests proving active preference affects focus horizon and
  allocation ranges.
- Run WebUI tests for settings save behavior.
- Run full `python3 -m pytest`.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `user_preferences` persistence and active-profile uniqueness.
- Added repository helpers for setting, listing, and reading active preference.
- Added `investment-forecasting prefs set/list`.
- Added WebUI `风险设置` page.
- Daily advice now reads the active preference, uses its horizon for focus
  assets, applies max-equity/min-cash constraints, and stores the preference in
  `allocation_json`.
- Validation passed with `python3 -m pytest`.
