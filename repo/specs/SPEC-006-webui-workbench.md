# SPEC-006: Jarvis Consumer WebUI

## Status

draft

## Goal

Provide a Jarvis-first consumer product UI for daily investment decision
support, while keeping technical workbench evidence available as secondary
drill-down. The product should be organized around the user's daily decision
journey, not around internal system modules.

## Non-Goals

- Do not build a marketing landing page.
- Do not hide risk warnings behind decorative presentation.
- Do not allow UI-only model edits that are not stored or audited.

## Inputs

- Stored database records and service/API responses.
- Daily advice, prediction, backtest, and task-log outputs.

## Outputs

- Primary navigation:
  - 今日简报
  - 机会池
  - 专家团
  - 证据
  - 设置
- Secondary technical routes may remain available for direct links, evidence
  drill-down, and agent workflows, but they should not appear as first-level
  consumer navigation.

## Information Architecture

The UI must move from module-based pages to task-based pages:

- `今日简报`: combines the useful parts of Dashboard, Jarvis, Daily Advice,
  and Timeline. It is the default entry and should answer "今天怎么看，为什么，
  能不能信，接下来观察什么".
- `机会池`: combines Categories, Themes, Funds, Data, and part of Predictions.
  It helps users find which assets, funds, ETFs, indices, or stocks deserve
  attention under the active risk profile.
- `专家团`: keeps the expert committee, but frames it as expert opinions,
  disagreement, performance, and review lessons instead of an expert database.
- `证据`: combines Predictions, Backtests, Market/Macro, technical data
  details, model health, and raw evidence. It is for advanced users and Agents,
  not the default consumer path.
- `设置`: combines risk preferences, investment horizon, notification setup,
  communication health, data update state, and task logs as advanced system
  health details.

## Constraints

- UI should be dense and inspectable, but the first-level experience should
  feel like Jarvis serving the user rather than a developer workbench.
- Visual claims must show supporting fields: date, source, model version,
  confidence, risk, and historical score.
- Advice display must preserve the aggressive/balanced/conservative distinction.
- User risk settings must be persisted before they influence advice generation.
- Tables and charts should make stale or failed data visible.
- The left navigation should expose only the five primary entries. Route-level
  detail pages can be reached from tabs, cards, links, or collapsed technical
  sections.
- Product naming and visible chrome should reinforce Jarvis as the assistant.
  Avoid primary-brand copy such as "投资预测工作台" unless it appears only as
  secondary technical context.
- New WebUI pages are forbidden by default. Add a new first-level page only if
  a product review proves it cannot fit into 今日简报, 机会池, 专家团, 证据, or 设置,
  and record the decision in `decisions/`.
- Developer/system terms such as "预测", "回测评分", "任务日志", "数据与曲线", and
  "研究时间线" must remain secondary evidence labels or direct technical routes,
  not consumer navigation labels.
- Technical tables, raw JSON, provider payloads, SQL-like fields, task logs,
  and debug records must be collapsed or placed behind 证据 / 设置 details.

## Route Ownership Rules

- `今日简报` owns daily conclusion, reasons, trust state, focus assets, expert
  consensus, risk boundary, data freshness, and task health.
- `机会池` owns product/asset discovery, product type filters, theme/fund
  screening, prediction cards, and selected-asset drill-down links.
- `专家团` owns expert opinions, disagreement, virtual performance, lifecycle
  reviews, and lessons.
- `证据` owns model predictions, backtests, model health, market/macro/capital
  flow, data coverage, and raw technical evidence.
- `设置` owns risk preference, horizon, notification setup, communication
  health, data update state, and task logs/system health.

## Error Cases

- Database has no records yet.
- Latest scheduled run failed.
- Backtest or prediction data is missing for selected asset.
- Browser cannot reach the local service.

## Acceptance

- User can open the default page and see a Jarvis daily brief with today's
  judgment, one-line conclusion, three reasons, expert consensus/disagreement,
  focus assets, data freshness, task health, risk warnings, and watch
  conditions.
- User can use a five-entry primary navigation: 今日简报, 机会池, 专家团, 证据,
  设置.
- User can inspect opportunities across funds, ETFs, stocks, and indices in a
  single opportunity-pool flow with risk-profile-aware sorting and asset-level
  prediction cards.
- User can inspect expert opinions as a consumer-facing expert panel, with
  history and raw details secondary.
- User can inspect model predictions, backtests, market snapshots, data
  coverage, and raw evidence from a secondary evidence center.
- User can inspect risk preferences, notification settings, data update state,
  system health, and task logs from settings.
- Legacy technical routes do not appear as first-level navigation entries.
- User can see today's market state and advice summary on the daily brief.
- User can inspect latest market snapshots, macro observations, and historical
  capital-flow records on a dedicated market-indicator page.
- User can inspect historical price/NAV data and feature/risk metrics.
- User can see deterministic industry/theme labels in asset, fund, prediction,
  category, and market indicator views, and can filter funds by theme.
- User can inspect latest fund-holding observations and filtered
  theme-level holding look-through exposure on the fund workbench when holding
  data has been ingested.
- User can inspect theme-level coverage, risk/return, expected-return, and
  representative asset summaries on a dedicated theme allocation page.
- User can inspect forecasts with probability, expected return, downside risk,
  and confidence.
- User can inspect backtest performance, max drawdown, benchmark comparison, and
  scores.
- User can inspect model monitoring status, including stale inputs, score
  drift, benchmark excess, and degraded health.
- User can inspect target-volatility and correlation risk-budget evidence on
  the advice page without opening raw JSON first.
- User can inspect daily task logs and failure reasons.
- User can set the active risk preference and investment horizon in the WebUI.

## Implementation Notes

- The five-entry Jarvis consumer IA is implemented through `TASK-066` through
  `TASK-070`.
- `/` is the default 今日简报 route and is organized around the six daily
  decision questions: 今天怎么看, 为什么, 能不能信, 关注哪些资产, 专家是否一致,
  and 风险边界/观察条件.
- `/opportunities`, `/experts`, `/evidence`, and `/settings` are the remaining
  primary entries. Legacy technical routes are preserved for direct links,
  evidence drill-down, tests, and agents, but are not first-level navigation.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-008-webui-workbench.md`
