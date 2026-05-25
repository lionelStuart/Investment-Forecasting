# ADR-007: Jarvis Consumer Information Architecture

## Status

accepted

## Context

The product had grown into an 11-entry module-oriented WebUI: dashboard,
timeline, categories, data, funds, predictions, backtests, advice, experts,
settings, and logs. Consumer feedback and product review found that this made
the system feel like a developer workbench instead of an AI financial
assistant.

The target product is Jarvis: a daily AI investment assistant that gives a
simple, evidence-backed wealth-management brief first, then lets users inspect
opportunities, experts, evidence, and settings as needed.

## Decision

The primary WebUI information architecture is fixed to five consumer entries:

1. 今日简报
2. 机会池
3. 专家团
4. 证据
5. 设置

`/` must be the Jarvis daily brief experience. It should answer:

- 今天怎么看?
- 为什么?
- 能不能信?
- 关注哪些资产?
- 专家是否一致?
- 风险边界是什么?

Legacy technical routes may remain available for direct URLs, tests, agents,
and evidence drill-down. They must not appear as first-level consumer
navigation.

## Route Ownership

- 今日简报 owns daily conclusion, reasons, trust state, focus assets, expert
  consensus/disagreement, risk boundary, data freshness, and task health.
- 机会池 owns product/asset discovery, product type filters, themes, fund
  screening, selected-asset summaries, and prediction cards.
- 专家团 owns expert opinions, disagreement, virtual performance, lifecycle
  reviews, and lessons.
- 证据 owns model predictions, backtests, model health, market/macro/capital
  flow, data coverage, raw rows, and technical evidence.
- 设置 owns risk preference, investment horizon, notification setup,
  communication health, data update state, and task logs/system health.

## Consequences

- New first-level WebUI navigation entries are prohibited unless a new
  product-review task and ADR change this decision.
- Technical labels such as 预测, 回测评分, 任务日志, 数据与曲线, 研究时间线, and
  产品分类 may appear as evidence links, tabs, or collapsed details, but not as
  primary navigation.
- Product chrome and user-facing copy should identify the product as Jarvis
  理财助理, not as a generic investment forecasting workbench.
- Every WebUI task must state which of the five entries owns the change.
- `SPEC-006`, `ARCHITECTURE.md`, `CODE_INDEX.md`, `STATUS.md`, and task docs
  must remain synchronized with this IA.

## Non-Goals

- This decision does not remove technical routes or agent-facing evidence
  surfaces.
- This decision does not hide risk warnings, model uncertainty, task failures,
  or raw evidence.
- This decision does not authorize marketing-style landing pages.
