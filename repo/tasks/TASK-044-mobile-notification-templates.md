# TASK-044: Mobile Notification Templates

## Status

pending

## Purpose

Use the communication service to send safe, concise phone notifications for
daily research, failures, and expert updates.

## Scope

- Add templates for daily workflow success, daily workflow failure, provider
  warning, expert plan ready, expert probation, and expert retirement.
- Reuse existing daily brief, run-health, advice, and expert summaries where
  possible.
- Integrate optional sends into daily workflow and expert workflow behind
  enabled configuration.
- Add idempotency keys so reruns do not spam the phone.
- Ensure messages avoid raw JSON and investment certainty language.

## Non-Scope

- No new investment logic.
- No inbound command handling.
- No dependency on successful message delivery for core workflow success.

## Files Likely To Change

- `src/investment_forecasting/communication/templates.py`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/experts/`
- `tests/test_communication.py`
- `tests/test_daily_workflow.py`

## Acceptance Criteria

- Daily success and failure messages can be rendered in dry-run.
- Expert plan/retirement templates can be rendered from persisted expert data.
- Workflow reruns do not create duplicate sends for the same event.
- Communication failure records warning status but does not fail the research
  workflow.
- Templates include research-support or virtual-simulation wording where
  appropriate.

## Depends On

- `TASK-042`
- `TASK-043`
- `TASK-033`
- `TASK-038`
