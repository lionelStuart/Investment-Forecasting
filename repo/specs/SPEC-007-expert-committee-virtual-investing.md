# SPEC-007: Expert Committee Virtual Investing

## Status

draft

## Summary

Introduce an expert-committee architecture that runs multiple parallel virtual
investment experts. Each expert has a distinct investing style, data
preferences, model focus, risk constraints, virtual capital account, daily
investment plan, execution record, scorecard, review history, and lifecycle
state.

The first product target is three active experts, each starting with virtual
capital such as CNY 500,000. Every day, each expert reviews stored research
evidence, decides whether to invest, hold, reduce, or stay in cash, then writes
a traceable plan and simulated execution. Over time, the system evaluates each
expert's return, drawdown, benchmark excess, consistency, and risk discipline.
Underperforming experts are reviewed, their failure lessons are recorded, and
they can be retired. When one expert is retired, the system hires a replacement
expert using historical lessons and a different style gap.

## Product Goals

- Turn daily research into competing, inspectable investment styles instead of
  one generic advice voice.
- Evaluate investment plans as virtual portfolios with capital, positions,
  cash, transactions, and equity curves.
- Keep at least three active experts in parallel so users can compare style,
  behavior, and outcomes.
- Retain lessons from failed experts and use those lessons when hiring new
  experts.
- Preserve investment-safety guardrails: no guaranteed returns, no live
  brokerage execution, no hidden future leakage, and every plan must reference
  stored evidence.

## Core Concepts

- `Expert`: A durable persona with style, preferences, model focus, risk limits,
  allowed asset categories, review cadence, and lifecycle state.
- `Expert Style`: The investing philosophy and behavior pattern, such as
  value/quality, momentum/trend, defensive income, macro rotation, or
  risk-parity allocation.
- `Expert Observation Focus`: Which stored signals the expert weighs more
  heavily, such as valuation proxies, momentum, drawdown, volatility, market
  snapshots, fund metadata, backtest quality, or prediction confidence.
- `Expert Plan`: A daily, evidence-backed plan containing target actions,
  reasons, risk checks, expected horizon, and a `no trade` option.
- `Expert Virtual Portfolio`: A simulated account linked to one expert, with
  initial capital, cash, holdings, transactions, and daily valuation.
- `Expert Scorecard`: A rolling evaluation of return, drawdown, benchmark
  excess, volatility, hit rate, turnover discipline, evidence quality, and
  adherence to the expert's own mandate.
- `Expert Review`: A periodic lifecycle decision: keep, warn, probation, retire,
  or hire replacement.
- `Expert Lesson`: A structured failure or success lesson used to avoid hiring
  the same failing pattern repeatedly.

## Requirements

### Expert Roster

- The system must support exactly three active experts by default.
- Each expert must have:
  - name and short description;
  - style label;
  - model/data focus weights;
  - risk budget and maximum drawdown tolerance;
  - allowed asset categories;
  - default cash buffer;
  - lifecycle state: candidate, active, probation, retired.
- Experts must be persisted, not hardcoded only in UI.
- Expert prompts or plan templates may exist, but structured fields are the
  source of truth.

### Daily Planning

- Each active expert must produce at most one plan per run date.
- A plan may decide to buy, sell, rebalance, hold, or stay in cash.
- Every plan must reference stored evidence such as model predictions,
  backtests, features, market snapshots, fund metadata, or advice records.
- Plans must include risk warnings and must avoid certainty language.
- Plans must obey both global investment-safety constraints and expert-specific
  limits.
- Plans must be generated from data already available for the run date; no
  future market data may influence the plan.

### Virtual Execution

- Each expert receives an initial virtual capital amount, defaulting to CNY
  500,000 unless configured otherwise.
- Executions are simulated only; there is no brokerage integration.
- Orders should execute at stored close/nav prices available for the simulated
  trade date.
- If price data is missing, the order must remain unfilled with a reason.
- The system must record cash, positions, transactions, fees/slippage
  assumptions, and daily portfolio valuation.
- The `no trade` decision is a valid action and should be scored for risk
  discipline when markets are unfavorable.

### Scoring

- Scorecards must evaluate both returns and behavior. Minimum metrics:
  portfolio return, benchmark return, benchmark excess, max drawdown,
  volatility, cash drag, turnover, win rate, evidence completeness, and mandate
  adherence.
- Scores must be rolling-window based and must identify whether the evaluation
  period is mature enough for lifecycle decisions.
- A losing expert is not automatically bad if they followed a defensive mandate
  during a falling market; scoring must compare outcomes to style intent and
  benchmark context.

### Retirement And Hiring

- Experts can be warned, put on probation, or retired.
- Retirement requires structured evidence, not a single bad day.
- When an expert is retired, the system must write a failure review explaining:
  what happened, what signals were overweighted or ignored, what risk controls
  failed, and what future hiring should avoid.
- The system must hire a new candidate when active expert count falls below
  three.
- Replacement hiring should reference historical expert lessons and prefer a
  style or focus that improves committee diversity.

### WebUI

- The WebUI must provide an expert-committee view with:
  - active expert roster and lifecycle state;
  - each expert's current capital, cash, positions, return, drawdown, and score;
  - today's expert plans and whether orders executed;
  - equity curves and comparison against benchmark;
  - warnings, probation, retired experts, and lessons learned.
- The UI must not frame a top expert as guaranteed to keep winning.

### Agent Workflow

- Before implementing an expert feature, the Agent must inspect existing
  portfolio, advice, backtest, scoring, daily workflow, database, MCP, and WebUI
  capabilities.
- Expert plans should reuse existing stored evidence and simulated-portfolio
  mechanics before adding new data paths.
- Every implementation task must update `ARCHITECTURE.md` and `CODE_INDEX.md`
  if it adds tables, modules, CLI commands, MCP tools, or routes.

## Non-Goals

- No live trading, order routing, account connection, or capital transfer.
- No claim that experts are real licensed advisers.
- No hidden LLM-only state that cannot be audited through persisted records.
- No clearing or firing an expert solely because of one short-term loss.
- No advanced multi-agent orchestration before the deterministic data model and
  scoring loop exist.

## Suggested Initial Expert Roster

1. `稳健防守专家`
   - Style: defensive income and drawdown control.
   - Focus: volatility, max drawdown, cash buffer, market snapshot risk,
     conservative fund metadata.
   - Behavior: can choose no trade frequently; penalized less for cash drag in
     high-risk market states.

2. `趋势进攻专家`
   - Style: momentum and growth participation.
   - Focus: 20/60-day momentum, up probability, expected return, confidence,
     improving market breadth.
   - Behavior: accepts higher volatility but must reduce exposure after
     drawdown or confidence deterioration.

3. `均衡轮动专家`
   - Style: category rotation and risk-adjusted balance.
   - Focus: Sharpe, Calmar, benchmark excess, category diversification,
     model/backtest quality.
   - Behavior: prefers partial rebalancing and avoids concentration.

## Acceptance Criteria

- Three active experts can be created from structured configuration.
- Each expert can receive CNY 500,000 virtual initial capital.
- Each active expert can create a daily plan with explicit `trade` or
  `no_trade` action and evidence links.
- Simulated execution records transactions, cash, positions, and valuation
  using stored prices only.
- Expert scorecards compare return, drawdown, benchmark, and mandate adherence
  over a rolling window.
- Underperforming experts can enter probation or retirement with a written
  failure lesson.
- When an expert is retired, a replacement candidate can be hired from style
  gaps and historical lessons.
- WebUI can compare active, probation, and retired experts without exposing raw
  tables as the primary experience.

## Related Tasks

- `TASK-036`: Expert architecture and roster model.
- `TASK-037`: Expert virtual portfolio foundation.
- `TASK-038`: Expert daily planning and simulated execution.
- `TASK-039`: Expert scoring, reviews, retirement, and replacement hiring.
- `TASK-040`: Expert committee WebUI and timeline.
- `TASK-041`: Expert agent workflow and MCP integration.
