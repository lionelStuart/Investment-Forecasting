# TASK-061: AI Provider Adapter Contract

## Status

completed

## Purpose

Turn the current deterministic AI-analysis source into a real, bounded AI
interaction layer without letting provider calls leak into expert, Jarvis,
WebUI, MCP, workflow, or communication code.

## Scope

- Add an AI provider adapter boundary for configured model calls.
- Define provider config loading without hardcoded credentials.
- Preserve deterministic fallback as the default safe path.
- Record source, model, provider status, duration, errors, and fallback reason
  in analysis metadata or task logs.
- Add a CLI inspection or dry-run surface that proves configuration and
  fallback behavior without requiring live market data changes.

## Non-Scope

- No prompt redesign beyond the minimum provider request envelope.
- No changes to advice, portfolio, expert scoring, or model forecasting logic.
- No new data provider, new expert, automatic rebalancing, or inbound phone
  command.
- No direct model SDK import outside the provider adapter boundary.

## Files Likely To Change

- `src/investment_forecasting/ai_analysis.py`
- `src/investment_forecasting/ai_providers/`
- `src/investment_forecasting/cli.py`
- `src/investment_forecasting/workflows/daily.py`
- `tests/test_ai_providers.py`
- `tests/test_experts.py`
- `tests/test_jarvis.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Define an adapter protocol with request, response, timeout, error, and
  provider metadata fields.
- Implement a deterministic fallback adapter using the existing analysis
  builders.
- Add a fake/test provider that returns valid structured JSON.
- Add config discovery from environment or local config, without committing
  secrets.
- Make provider unavailability non-fatal and auditable.

## Acceptance Criteria

- Tests can exercise provider success, missing config, timeout/error, and
  deterministic fallback without real network calls.
- Provider metadata is visible in persisted `ai_analysis_records.source` or
  validation metadata.
- No module outside the AI provider boundary imports a model SDK.
- The default local workflow still works without credentials.

## Test Plan

- `python3 -m pytest tests/test_ai_providers.py tests/test_experts.py tests/test_jarvis.py -q`

## Result

- Added `investment_forecasting.ai_providers` with request/response/config
  dataclasses, deterministic fallback behavior, fake provider support, timeout
  and error fallback metadata, and environment-based config discovery.
- Added `investment-forecasting ai provider-check` as a dry-run inspection
  surface that proves provider success and fallback behavior without reading or
  changing market data.
- Added provider/fallback metadata to persisted AI-analysis validation JSON for
  deterministic expert and Jarvis analysis records.
- Verified provider success, missing config, missing credentials, forced
  provider error, CLI fallback, CLI fake-provider success, and existing
  expert/Jarvis workflows without real network calls.

## Depends On

- `TASK-052`
- `TASK-060`
