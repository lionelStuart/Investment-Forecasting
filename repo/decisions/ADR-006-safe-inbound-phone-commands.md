# ADR-006: Inbound Phone Commands Stay Gated And Non-Trading

## Status

accepted

## Context

Outbound phone notifications now exist for daily workflow, expert lifecycle
events, and Jarvis summaries. The next natural product question is whether the
user can reply from the phone with commands such as acknowledging a warning,
requesting a rerun, or asking for a report.

Phone-originated commands are a much higher-risk surface than outbound
notifications. iMessage on macOS is designed for human conversation, not for
trusted command ingestion. Reading Messages history can expose unrelated
private content, can be brittle across macOS releases, and does not provide a
strong application-level authentication, nonce, or confirmation primitive.

## Decision

The system remains outbound-only for iMessage. iMessage may continue to deliver
research-support notifications, but it is not accepted as an inbound command
transport for the current architecture.

Future inbound phone commands require a separate explicit implementation task
and a safer command channel. The preferred future channel is a purpose-built
local WebUI or app-bridge flow that can provide scoped authentication,
single-use nonces, command previews, confirmation, replay protection, and
auditable command records.

Allowed future inbound command families are limited to non-trading operational
requests:

- acknowledge a notification or risk warning;
- request a regenerated Jarvis report using already configured local settings;
- request a status snapshot or report resend;
- pause or resume non-critical notifications;
- create a review reminder or mark an item for local WebUI follow-up.

Forbidden command families include:

- live brokerage actions, real-money buy/sell/rebalance/transfer commands, or
  anything that can be interpreted as real-money execution;
- changing investment risk limits, user preference caps, expert mandates, or
  model promotion state without a local WebUI confirmation step;
- adding recipients, changing allowlists, disabling audit, disabling safety
  language, or escalating permissions;
- executing arbitrary shell, SQL, Python, AppleScript, MCP, or agent prompts;
- reading arbitrary Messages history or discovering contacts broadly.

Any future inbound implementation must store every parsed command, sender,
channel, nonce, received timestamp, validation result, confirmation result,
execution status, and error in an audit table before side effects occur.
Commands must be allowlisted, authenticated, freshness-limited, single-use,
rate-limited, and idempotent. Side effects must be constrained to explicit
non-trading operations and must fail closed when validation is incomplete.

## Consequences

- The current iMessage adapter stays simpler and safer: outbound delivery only,
  no private message scraping, and no phone-originated execution path.
- Product work can still design future phone interactions, but implementation
  must start from a command audit model and safer transport rather than
  AppleScript conversation parsing.
- Daily workflow, Jarvis, expert, MCP, and WebUI code must continue to treat
  phone communication as notification-only until a later task explicitly adds
  a compliant inbound command service.
