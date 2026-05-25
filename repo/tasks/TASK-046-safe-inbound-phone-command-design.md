# TASK-046: Safe Inbound Phone Command Design

## Status

completed

## Purpose

Design, but do not immediately implement, safe phone-originated commands for
future replies such as acknowledgements, rerun requests, or report requests.

## Scope

- Define allowed inbound command types.
- Define authentication, allowlist, confirmation, replay protection, and audit
  requirements.
- Define commands that are explicitly forbidden, including live trading or
  real-money execution.
- Evaluate whether inbound iMessage parsing is acceptable or whether a safer
  future channel is required.
- Produce an ADR or update `SPEC-008` before implementation.

## Non-Scope

- No reading Messages history in this task.
- No implementation of inbound command execution.
- No investment actions from phone replies.

## Acceptance Criteria

- A written design identifies allowed commands, forbidden commands, risks,
  confirmations, audit logs, and adapter requirements.
- The design decides whether iMessage is suitable for inbound commands or only
  outbound notifications.
- No code path executes a phone-originated command until a later implementation
  task is approved.

## Depends On

- `TASK-043`

## Implementation Notes

- Added `ADR-006` to decide that iMessage remains outbound-only and is not an
  approved inbound command transport for the current system.
- Updated `SPEC-008` with allowed non-trading future command families,
  forbidden command families, authentication/allowlist/confirmation/replay
  protection requirements, and command audit requirements.
- Updated architecture notes so future agents do not add inbound execution to
  the iMessage adapter, WebUI, Jarvis, MCP, or investment workflows without a
  later explicit implementation task.

## Verification

- `rg -n "Messages history|inbound|phone-originated|execute investment actions" src tests`
  confirms there is no inbound phone command implementation in runtime code.
- `python3 -m pytest tests/test_communication.py`
- `scripts/restart_web.sh`
