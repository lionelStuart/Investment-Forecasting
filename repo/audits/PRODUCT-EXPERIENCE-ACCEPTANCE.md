# Product Experience Acceptance Reports

This document is the rolling product and UX acceptance record for the
Investment Forecasting WebUI. Each phase records the observed product shape,
key gaps, and the next iteration target.

## Long-Term Product Goal

长期目标是建设一个人机友好的理财预测和建议系统：它既能让普通用户快速理解市场状态、风险边界和下一步观察动作，也能让 AI Agent 基于结构化数据、可回测模型和稳定工作流持续改进产品。

这个系统不是交易指令机，也不是收益承诺工具。它应该成为一个可信的投资研究伙伴：

- 对人友好：把复杂行情、模型预测、回测评分和风险提示翻译成清晰、克制、可复核的日常理财建议。
- 对 Agent 友好：每个页面、指标、建议和异常状态都有结构化来源、可点击证据、明确验收标准和可执行任务。
- 对数据诚实：显式暴露数据覆盖、新鲜度、缺失、异常、样本外表现和模型局限。
- 对系统稳定：每日任务可重复、失败可定位、恢复路径清楚，页面能及时告诉用户当前结果是否可用。

### North-Star Experience

用户每天打开首页后，应在 30 秒内获得一份“今日理财研究简报”：

1. 今天整体市场倾向是什么。
2. 系统建议采取什么风险姿态。
3. 哪些资产值得关注，哪些需要回避或降权。
4. 这些判断基于哪些数据、预测、回测和市场环境证据。
5. 当前建议是否受到数据滞后、覆盖不足、低置信度或任务失败影响。

### Product Quality Metrics

| Dimension | Target Metric | Why It Matters |
| --- | --- | --- |
| 用户友好 | 首页 30 秒内读懂今日风险姿态、关键原因和观察动作 | 降低从数据表到投资判断的认知成本 |
| 建议可解释 | 任一建议 2 次点击内追溯到预测、回测、行情和市场快照证据 | 避免黑盒建议，方便人和 Agent 复核 |
| 数据可靠 | 首页展示最新行情日、特征日、预测日、建议日、快照日和覆盖率 | 防止用过期或不完整数据做判断 |
| 预测准确 | 每个模型版本展示方向准确率、收益误差、风险命中、基准超额和样本窗口 | 让模型改进基于历史证据而非主观感觉 |
| 风险控制 | 建议页同时展示上行、下行、置信度、回撤和减仓触发条件 | 理财建议优先管理损失边界 |
| 系统稳定 | 每日任务成功率、最近失败原因、重试状态和恢复入口可见 | 让用户知道系统是否健康，Agent 知道修哪里 |
| Agent 可执行 | 每个改进项有任务边界、验收标准、测试建议和页面证据 | 方便 gstack 协助下持续自动化迭代 |

## Current Target Breakdown

当前阶段目标不是扩张成完整投顾平台，而是把已有 WebUI 从“技术工作台”升级为“可信研究驾驶舱”的第一版。

## Jarvis Consumer IA Acceptance: 2026-05-23

Status: accepted.

The WebUI first-level navigation now contains exactly five consumer entries:
今日简报, 机会池, 专家团, 证据, 设置. The default `/` page is no longer a generic
module dashboard; it is organized around the Jarvis daily decision questions:
今天怎么看, 为什么, 能不能信, 关注哪些资产, 专家是否一致, and 风险边界/观察条件.

Acceptance evidence:

- `/` renders `今日简报` with the six question sections and links onward to
  `/opportunities` and `/evidence`.
- `/opportunities` consolidates product categories, themes, fund candidates,
  holding look-through, and asset-level prediction cards.
- `/experts` remains the consumer expert panel and drill-down surface.
- `/evidence` consolidates predictions, backtests/model health,
  market/macro/capital-flow evidence, data coverage, and collapsed raw rows.
- `/settings` consolidates risk preferences, communication health, data update
  state, system health, and task-log guidance.
- Legacy routes such as `/timeline`, `/market`, `/categories`, `/themes`,
  `/data`, `/funds`, `/predictions`, `/backtests`, `/advice`,
  `/communication`, and `/logs` remain reachable for drill-downs and agents,
  but are no longer first-level navigation.

Remaining UI risks:

- The 今日简报 page is structurally aligned, but copy quality still depends on
  deterministic Jarvis synthesis until `TASK-062` and provider-backed follow-up
  tasks improve prompt and evidence discipline.
- Prediction values can still look overconfident if later AI/provider work does
  not add confidence gates and outlier wording.
- Expert performance remains early-stage; the page exposes sample limitations,
  but future copy should keep avoiding mature ranking language.

Decision: resume `TASK-062` next. Do not return to data expansion,
rebalancing, additional experts, or phone-command expansion before the AI
prompt/evidence schema is frozen.

### Current Target 1: Make The Daily Brief Human-Readable

用户问题：我今天应该更进攻、更防守，还是继续观察？

改进方向：

- 首页增加“今日决策简报”，包含市场姿态、风险姿态、主要原因、观察动作。
- 把 `medium`、`risk_on`、`53.33% confidence` 等系统语言翻译成中文解释。
- 对每个建议标注适用用户：激进型、中等型、保守型。

### Current Target 2: Make Data And Prediction Trust Visible

用户问题：这些建议是否基于新鲜、足够、可信的数据？

改进方向：

- 首页保留当前已出现的数据状态，并升级为新鲜度/覆盖率/异常状态组件。
- 在建议页和预测页显示“数据截至 2024-05-22，建议生成于 2026-05-23”这类时间差说明。
- 对低覆盖、低置信度、缺失基金信息、缺失市场快照等状态给出影响说明。

### Current Target 3: Make Evidence Traceable For Humans And Agents

用户问题：为什么系统推荐这些资产，依据是什么？

改进方向：

- 将每日建议中的 raw JSON evidence 替换为证据卡片或证据 chips。
- 每个证据项链接到资产页、预测页、回测页或市场快照。
- 为 Agent 保留结构化 ID，但避免让普通用户直接阅读 JSON。

### Current Target 4: Make Forecasts Actionable

用户问题：同一个资产 5/20/60 日预测不同，我应该怎么看？

改进方向：

- 预测页按资产聚合，不再把多个 horizon 当成独立推荐重复展示。
- 增加 horizon agreement：短中长期一致、短期反弹长期偏弱、短期弱长期改善等。
- 对下行风险明显高的资产加入警示视觉。

### Current Target 5: Make Operations Stable And Recoverable

用户问题：系统今天是否正常跑完，失败了该怎么办？

改进方向：

- 任务日志页从原始日志表升级为运行健康面板。
- 显示最近一次 daily run 的分阶段状态：ingest、features、market snapshot、forecast、backtest、advice。
- 对失败任务显示重试建议、影响范围和 Agent 可执行修复入口。

### Current Target 6: Productize The Research Flow

用户问题：这个工具不像一个完整产品，更像若干粗糙页面拼在一起；我的研究过程在哪里？

改进方向：

- 增加时间轴视图，把每日建议、市场快照、预测变化、回测结果和任务状态串成连续历史。
- 从单页表格升级为产品化信息架构：今日、资产、产品分类、预测、回测、日志之间要形成清晰路径。
- 每个页面增加主任务区域、次级详情和技术详情层级，避免所有信息同权展示。

### Current Target 7: Classify Financial Products Before Filtering

用户问题：理财产品类型不同，不能只用一张粗筛表比较。

改进方向：

- 先按产品类型分层：指数、ETF、股票、公募基金、固收/债券类、现金类、宏观/市场指标。
- 基金页继续细分：股票型、混合型、债券型、货币型、指数型、QDII、行业主题等。
- 筛选条件随分类变化：基金关注规模、费率、经理、回撤、Sharpe；ETF 关注跟踪标的、流动性、折溢价；指数关注市场风格和宽度。

### Current Target 8: Use Red/Green Market Semantics

用户问题：涨跌和风险状态不够直观，用户需要一眼看懂正负变化。

改进方向：

- 对涨跌、预期收益、实际收益、超额收益使用统一红绿标记。
- 按中国投资语境约定：红色表示上涨/正收益，绿色表示下跌/负收益；风险、告警、失败状态不与涨跌颜色混用。
- 在表格、推荐卡、曲线、预测卡和历史时间轴中保持颜色语义一致，并为色弱用户保留符号、箭头或文字标签。

## Progress Review: 2026-05-23 After Data Expansion

Reviewed URL: `http://127.0.0.1:8765/`

### Current Progress

The product has moved beyond the initial MVP workbench:

- Data coverage is materially larger: the dashboard shows 63 assets, 24,837
  price/nav rows, 219 predictions, and 3 daily advice records.
- Data freshness is much better: latest price and prediction data are through
  2026-05-22, and the market snapshot is dated 2026-05-23.
- User preference work has landed: the navigation includes `风险设置`, and the
  active profile records account name, risk preference, investment horizon,
  maximum equity ratio, and minimum cash ratio.
- Daily advice now references the active risk setting and applies user
  constraints to allocation ranges.
- Fund metadata and data coverage are broad enough that product classification
  and category-specific screening are now worth building.

### Remaining Product Gaps

1. The experience is still page-list driven.
   The user sees a dashboard, advice, predictions, funds, and logs, but there is
   no timeline that explains how today's state evolved from prior runs.

2. The dashboard has more data, but still lacks a productized daily brief.
   It shows strong metrics such as 5.18% average expected return and 86.05%
   average confidence, but does not summarize whether the recommended stance is
   cautious, balanced, selective, or aggressive.

3. Fund screening is more valuable now, but not yet usable enough.
   With 18 funds and more metadata, a raw ranking table is no longer sufficient.
   Users need product categories, fund-type filters, risk filters, fee/scale
   filters, and profile-aware suitability sorting.

4. Predictions still repeat horizons as independent cards.
   The predictions page repeats the same asset across 5, 20, and 60 day
   horizons. This hides the actual question: does the asset have consistent
   short/medium/long signal quality?

5. Visual semantics have not caught up with investment usage.
   Positive and negative values appear mostly as plain text. The product still
   needs red/green market semantics, arrows, and text labels for gains, losses,
   drawdowns, and deltas.

6. Operational health is still raw-log oriented.
   The logs page records successful ingestion and feature calculation, but it
   does not show a grouped daily run timeline or explain which downstream
   advice/results depend on each stage.

### Next Phase Decision

下一期应优先进入 `Phase 2: Actionable Research Workflows`，而不是立即把主资源投入组合跟踪或目标波动配置。

Reasoning:

- `TASK-021` and `TASK-027` have already improved personalization and data
  coverage, so the product now has enough raw material for a better experience.
- If the next work jumps directly to portfolios, the UI will accumulate another
  complex table before the core research flow is productized.
- The most valuable next step is to make the existing expanded data usable:
  timeline, product categories, filters, red/green semantics, and asset-level
  forecast cards.

## Next Phase Target: Phase 2 Productized Research Flow

### Big Goal

把当前“数据丰富但粗糙的研究工作台”升级为“可连续阅读、可分类筛选、可一眼判断涨跌风险的理财研究产品”。

### User Outcome

用户打开系统后，不只是看到很多表格，而是能完成一条自然路径：

1. 先在首页看到今日简报和风险姿态。
2. 再通过时间轴理解今天相比上一期发生了什么变化。
3. 然后按理财产品分类进入基金、ETF、指数、股票等候选池。
4. 使用适合该分类的筛选条件缩小范围。
5. 在资产级预测卡里比较 5/20/60 日信号。
6. 用红绿涨跌标记快速识别正收益、负收益、回撤和风险。
7. 最后从建议页追溯到证据和历史变化。

### Next Phase Work Items

1. Build product timeline.
   Add a timeline entry point in navigation or dashboard. Each row should show
   date, daily advice status, market snapshot, prediction run, backtest score,
   task health, and major deltas versus the previous run.

2. Productize dashboard brief.
   Add a top module that translates current metrics into one stance, such as
   `偏积极但需控制回撤`, `均衡观察`, or `防守等待确认`. Include three reasons and
   one next watch condition.

3. Add product classification navigation.
   Create category tabs or segmented controls for funds, ETFs, indices, stocks,
   fixed-income/cash-like assets, and macro/market indicators. The current asset
   coverage counts should become category entry points. The `/data` page should
   not show the full raw asset-list table as primary content; it should show a
   selector, selected-asset summary, and category context, with any full asset
   list moved to secondary technical details if retained.

4. Upgrade fund screening.
   Add filters for fund type, manager, scale range, fee availability, 20-day
   return, 60-day drawdown, Sharpe, win rate, and market state. Add default
   presets for conservative, balanced, and aggressive profiles.

5. Redesign prediction priority section.
   Group predictions by asset and show horizon agreement across 5/20/60 days.
   Keep the full prediction table as technical detail, not the primary
   experience.

6. Add red/green market semantics.
   Apply Chinese market convention: red for上涨/正收益 and green for下跌/负收益.
   Pair color with `+/-`, arrows, or text so the signal is accessible.

7. Turn logs into run health.
   Group tasks by run date and stage. Show whether ingestion, feature
   calculation, snapshot, forecast, backtest, advice, and monitoring completed.

8. Apply progressive disclosure to technical data.
   The current UI still exposes raw tables, evidence JSON, saved-setting fields,
   and task logs too early on several pages. These details should remain
   available for debugging, but user-facing summaries, cards, filters, warnings,
   and recovery guidance should appear first.

### Cross-Page Usability Findings

- `/data`: the full raw asset-list table under the selector should be removed
  from the primary workflow and replaced with selected-asset context.
- `/funds`: the page still behaves like a raw ranking table instead of a
  screening workflow with presets, filters, and candidate summaries.
- `/predictions`: repeated horizon rows should become asset-level cards before
  any raw prediction table.
- `/backtests`: model quality, horizon scores, and degraded states should appear
  before historical result rows.
- `/advice`: evidence should be shown as chips or cards; raw evidence JSON
  should be retained only as collapsed technical detail.
- `/settings`: saved preferences should be summarized as a human-readable risk
  profile before raw field tables.
- `/logs`: run health, failure impact, and recovery guidance should precede raw
  task-log rows.

### Next Phase Acceptance Criteria

- Dashboard includes a daily brief with stance, reasons, and watch condition.
- Timeline shows at least latest three advice/run dates and links to evidence.
- Fund page supports at least four filters and one profile preset.
- Product categories are visible before users inspect raw tables.
- The `/data` page no longer leads with the raw full asset-list table shown
  under the selector.
- Prediction priority area shows one card per asset, not one card per
  asset-horizon row.
- Red/green market semantics are applied on dashboard, predictions, funds, and
  advice focus assets.
- Logs page has a grouped daily run health section.
- Raw technical tables, JSON, saved-setting fields, and long logs are secondary
  or collapsible on table-heavy pages.
- Existing risk preference settings remain visible and continue to constrain
  advice.

### Recommended Task Sequence

1. `TASK-028`: Product timeline and daily run history.
2. `TASK-029`: Product category navigation and classification view model.
3. `TASK-030`: Fund screening filters and profile presets.
4. `TASK-031`: Red/green market visual semantics.
5. `TASK-032`: Asset-level prediction cards and horizon agreement.
6. `TASK-033`: Dashboard daily brief and run-health summary.
7. `TASK-035`: Progressive disclosure for raw technical tables and JSON.

### Architecture And Code Health Requirements

Each next-phase task must include a short design pass before implementation:

- Inspect existing modules, routes, database helpers, formatting helpers, tests,
  and workflow outputs that already cover the capability.
- State which existing code will be reused or extended, and why any new helper,
  route, table, or module is necessary.
- Update `ARCHITECTURE.md` if the work changes data flow, module ownership,
  WebUI route families, workflow stages, MCP surfaces, or persistence areas.
- Update `CODE_INDEX.md` if important files, commands, routes, tables, tests, or
  task surfaces are added, removed, renamed, or materially repurposed.
- Run the relevant tests and restart/smoke the WebUI before marking the task
  complete.

This requirement is meant to prevent code膨胀 and code腐败: new product UI
should emerge from existing capabilities and shared view-model patterns rather
than one-off SQL, duplicate formatters, or isolated route logic.

### Defer From This Phase

- Full simulated portfolio tracking can remain `TASK-022`, but should start
  after the research flow is easier to use.
- Target-volatility allocation should remain `TASK-023`, because allocation
  proposals will be more understandable once product categories, timeline, and
  asset-level forecast cards exist.
- Model drift reporting remains valuable, but should be presented through the
  run-health and model-quality surfaces added in this phase.

## Phase 0: MVP WebUI Acceptance

Date: 2026-05-23

Reviewed URL: `http://127.0.0.1:8765/`

Reviewer role: product design and user experience officer

### Current Product Shape

The current WebUI is a local investment research workbench with seven primary
views:

- Overview: database status, asset/price/prediction/advice counts, latest data
  dates, risk level, latest prediction date, average expected return, downside
  risk, confidence, latest task status, market snapshot, asset coverage,
  priority assets, and latest daily advice.
- Data and curve: asset selector, asset inventory, simple return curve, price
  history, and quantitative feature table.
- Fund screening: fund return/risk ranking table.
- Predictions: priority assets and raw model prediction table across horizons.
- Backtest scoring: backtest run summary and historical prediction scores.
- Daily advice: profile-specific advice for aggressive, balanced, and
  conservative users, assumptions, risk warnings, evidence IDs, and history.
- Task logs: daily workflow and subtask execution logs.

The MVP proves the full data-to-advice loop exists: data is persisted, baseline
forecasts are generated, backtests are scored, daily advice is stored, and the
browser can inspect the result.

Current observed state on 2026-05-23:

- The dashboard shows 10 assets, 330 price/nav rows, 30 predictions, and 3 daily
  advice records.
- Latest price data is 2024-05-22 while latest advice is 2026-05-23.
- The dashboard now surfaces market snapshot fields including `risk_on`,
  breadth, liquidity heat, stock-bond proxy, snapshot date, and data source.
- Advice history now has multiple selectable records and focus assets link to
  data pages.
- Fund metadata is partially populated for two funds, including type, manager,
  scale, fee proxy, return, drawdown, Sharpe, win rate, and market state.

### Acceptance Judgment

The product is acceptable as an internal technical workbench MVP, but not yet
acceptable as a decision-grade investment research product for repeated use.

Its strongest value is completeness of backend evidence exposure. Its main
weakness is that the interface still asks users to translate raw tables,
technical metrics, and JSON evidence into an investment conclusion by
themselves.

### Key Product Gaps

1. Decision hierarchy is weak.
   The overview shows many useful indicators, but does not answer the user's
   first question: "What changed, what should I do, and why now?" Medium risk,
   risk-on market environment, positive average expected return, and candidate
   assets are visible, yet no clear stance such as observe, reduce risk, wait
   for confirmation, or add in batches is promoted.

2. Advice and evidence are not connected tightly enough.
   Daily advice contains allocation ranges and trigger language, but the
   supporting prediction IDs and backtest IDs are surfaced as raw JSON. Users
   cannot click through from a claim to the exact asset, metric, forecast
   horizon, or backtest result that justifies it.

3. Data freshness is potentially confusing.
   The daily advice date is 2026-05-23 while the prediction data is through
   2024-05-22. This may be correct for seeded or sample data, but the UI does
   not make the gap explicit enough. For investment workflows, stale data
   needs a prominent freshness badge and a clear explanation.

4. Confidence and scoring are hard to interpret.
   Average confidence appears as 53.33%, while the backtest/advice overall
   score is around 93/100. The product does not explain whether confidence and
   historical score represent different concepts or how users should weigh
   them.

5. Fund screening is too raw for the target workflow.
   The fund page is a table with technical fields and no filters.
   A user cannot quickly screen by risk, fund type, fee, manager, recent return,
   drawdown, or suitability profile.

6. Prediction pages over-rank repeated horizons.
   The priority list repeats the same asset across 1, 5, 20, and 60 day
   horizons. This makes the page dense but not more actionable. The user needs
   an asset-level summary with horizon disagreement, trend, and risk.

7. Visual design is clear but utilitarian.
   The layout is readable and stable, with good navigation and table handling.
   However, it lacks visual encoding for risk direction, data quality, model
   confidence, recommendation status, and stale/missing data. The current
   palette and card system support a workbench, but not yet a refined
   investment decision experience.

8. Empty and NULL states reduce trust.
   Examples include raw log JSON truncation, possible missing data branches, and
   technical status strings. These should become guided states: what is
   missing, why it matters, what advice is affected, and what run or ingestion
   step fixes it.

## Phase 1: Next Iteration Target

### Big Trend Goal

Move the product from a "data and model inspection workbench" to a
"decision-grade investment cockpit" that explains market stance, evidence,
freshness, confidence, and next actions in one coherent flow.

The next version should make the product feel less like browsing database
tables and more like opening a daily investment research memo backed by
auditable data.

### Product Principle

Every important number should answer three questions:

- What does this mean?
- What evidence supports it?
- What action or watch condition follows from it?

### Recommended Phase 1 Improvements

1. Add a daily decision brief to the overview.
   Create a top-level module with one clear stance, such as "defensive watch",
   "neutral hold", or "selective add". Include three concise bullets:
   market condition, model signal, and recommended action boundary.

2. Add data freshness and coverage status.
   Show latest price date, latest feature date, latest prediction date, latest
   advice date, and market snapshot status as badges. Highlight stale,
   incomplete, or sample data states with plain-language explanations.

3. Connect advice to evidence.
   Replace raw evidence JSON with clickable evidence chips that link to the
   related prediction, backtest run, asset page, and source date. Each advice
   claim should have traceable support.

4. Redesign prediction into asset-level decision cards.
   Group horizons by asset. Show 1/5/20/60 day expected return, downside risk,
   up probability, confidence, and a compact "horizon agreement" label. Keep
   the raw table as a secondary detail view.

5. Upgrade fund screening from table to filterable workflow.
   Add filters for fund type, return range, drawdown ceiling, Sharpe threshold,
   fee availability, data completeness, and suitability profile. Add a default
   ranked view for "balanced profile candidates".

6. Make confidence and backtest score explainable.
   Add inline definitions and visual legends for confidence, direction
   accuracy, risk hit rate, return error, advice score, and overall score.
   Where metrics disagree, surface a warning such as "high historical score,
   low current confidence".

7. Improve market environment visibility.
   Promote market snapshot to a first-class section once available: sentiment,
   breadth, liquidity heat, stock-bond proxy, and macro evidence. If missing,
   show the exact command or workflow step needed to generate it.

8. Add guided empty states.
   Replace generic NULL/no-record states with product copy that states impact
   and recovery. Example: "Fund scale is missing, so scale-based screening is
   unavailable until fund info ingestion succeeds."

9. Create a daily research trail.
   Let users move from today's brief to previous briefs, with changes in risk
   level, top assets, confidence, and recommended allocation range highlighted
   against the prior run.

10. Add visual risk semantics.
    Use consistent color and icon treatment for positive return, negative
    return, warning, stale data, high drawdown, low confidence, and successful
    task completion. Avoid relying only on raw numbers and English status
    strings.

11. Add a product timeline.
    Introduce a timeline that connects daily advice, market snapshots,
    predictions, backtest scores, and task health. The timeline should make the
    system feel like a continuous research product instead of disconnected
    tables.

12. Add product classification before screening.
    Categorize investable products first, then expose filters appropriate to
    each category. Avoid comparing funds, ETFs, indices, stocks, and cash-like
    instruments as if they were the same object.

13. Add Chinese market red/green semantics.
    Use red for上涨/正收益 and green for下跌/负收益 across cards, tables, charts,
    forecasts, and timeline deltas. Pair color with arrows or text so the
    signal remains accessible.

### Phase 1 Success Criteria

- A user can understand today's market stance within 30 seconds from the
  overview page.
- A user can trace any daily advice claim to supporting predictions and
  backtest evidence within two clicks.
- Stale, missing, or sample data is visible before the user reads any advice.
- Fund screening supports at least three practical filters and one default
  suitability ranking.
- Prediction pages reduce repeated-horizon clutter by grouping signals by
  asset.
- Empty and NULL states explain user impact and recovery path.
- The UI includes a timeline entry point for daily advice and historical
  market/model changes.
- Financial products are categorized before users apply filters.
- Positive and negative market values use consistent red/green semantics with
  non-color text or arrow backup.

### Suggested Implementation Order

1. Overview decision brief and freshness badges.
2. Evidence chips and advice-to-prediction/backtest links.
3. Asset-level prediction cards.
4. Fund filters and suitability ranking.
5. Product classification model and category-specific filters.
6. Red/green market semantics for returns and changes.
7. Guided empty states and metric explanations.
8. Daily timeline and research trail comparison.

## Agent Execution Plan For GStack

This section breaks the product direction into implementation-ready work
packages for future Agent runs. Each task should keep the product's advisory
language conservative and preserve evidence traceability.

### EPIC-A: Human-Friendly Daily Brief

Goal: Make the home page communicate today's research stance before exposing
raw metrics.

Agent tasks:

- Add a `decision_brief` view model derived from latest advice, market snapshot,
  prediction summary, and data freshness.
- Render a top-of-dashboard brief with stance, confidence, key reasons, and
  watch conditions.
- Translate internal status values into Chinese product language.
- Add tests for brief content when data is fresh, stale, missing, or low
  confidence.

Acceptance criteria:

- The dashboard answers "today should I be defensive, neutral, or selective?"
  without requiring table reading.
- The brief includes a non-guarantee risk note.
- Empty database and stale-data cases do not show false confidence.

### EPIC-B: Data Freshness And Coverage Trust Layer

Goal: Make data quality visible before users consume advice.

Agent tasks:

- Build a freshness summary from latest dates in prices, features,
  predictions, market snapshots, advice, and task logs.
- Add status categories: fresh, delayed, stale, incomplete, sample-only,
  failed-run.
- Surface coverage by asset type and row counts with plain-language impact.
- Add recovery hints that map to existing CLI commands.

Acceptance criteria:

- Dashboard and advice pages show whether advice is based on delayed market
  data.
- Data date and advice date mismatch is explicit.
- Missing market snapshot or failed ingestion creates a warning state with a
  recovery path.

### EPIC-C: Evidence Graph For Advice

Goal: Replace raw evidence JSON with navigable evidence.

Agent tasks:

- Parse `allocation_json.evidence` into typed evidence items.
- Render evidence chips/cards for prediction IDs, backtest run IDs, market
  snapshot ID, source date, model version, and top focus assets.
- Add routes or query anchors that let users jump to the relevant prediction,
  backtest, asset, or market snapshot context.
- Preserve raw JSON only in a collapsible technical details block.

Acceptance criteria:

- Any advice paragraph can be traced to supporting evidence within two clicks.
- Users do not need to read JSON to understand why an asset is recommended.
- Tests verify evidence links exist for latest advice.

### EPIC-D: Asset-Level Forecast Experience

Goal: Turn the predictions page from repeated rows into asset-level decision
cards.

Agent tasks:

- Group predictions by asset and render one card per asset.
- Show horizon table or compact bars for 5/20/60 day expected return, downside
  risk, up probability, and confidence.
- Add horizon agreement labels and risk warnings.
- Keep raw prediction table below as "technical details".

Acceptance criteria:

- Each asset appears once in the priority forecast section.
- Users can compare short, medium, and long horizon signals without scanning
  duplicate cards.
- Downside-heavy assets are visually distinct from balanced candidates.

### EPIC-E: Fund Screening Workflow

Goal: Make fund selection usable for real screening instead of raw inspection.

Agent tasks:

- Add a product category layer before the filter form: public fund, ETF, index,
  stock, bond/fixed-income proxy, cash-like product, macro/market indicator.
- Add filters for fund type, drawdown ceiling, Sharpe threshold, scale
  availability, fee availability, and market state.
- Add profile presets: conservative, balanced, aggressive.
- Add sortable suitability score derived from return, drawdown, Sharpe, win
  rate, fee, and data completeness.
- Make filters category-aware. For example, public funds can filter manager,
  scale, fee and fund type, while ETFs can filter liquidity, tracking target,
  volatility and drawdown.
- Explain NULL or missing fund fields in user language.

Acceptance criteria:

- A balanced user can narrow candidates without editing URLs or reading raw SQL
  fields.
- Users can browse by product category before screening.
- Missing fund metadata lowers data completeness instead of silently appearing
  as `NULL`.
- Tests cover at least one filter and one preset.

### EPIC-F: Operational Stability Console

Goal: Let humans and Agents understand whether the daily system is healthy.

Agent tasks:

- Add a run-health summary for latest daily workflow stages.
- Group task logs by run date and task family.
- Show failure impact: which downstream pages/advice are affected.
- Add retry guidance using existing commands from `repo/PROJECT.md`.

Acceptance criteria:

- The logs page tells whether the latest daily run completed all critical
  stages.
- A failed stage shows both the error and the user-facing consequence.
- Agent can use the page to decide the next repair task.

### EPIC-G: Prediction Quality And Model Improvement Loop

Goal: Connect product UX to model accuracy improvement.

Agent tasks:

- Add model score summaries by horizon and asset type.
- Show calibration window, sample count, direction accuracy, mean error, risk
  hit rate, benchmark excess, and overall score.
- Add "model status" language: experimental, usable, promoted, degraded.
- Define a gate: no model should influence daily advice unless it has a
  qualifying backtest or calibration record.

Acceptance criteria:

- Users can tell whether model output is experimental or trusted.
- Daily advice references the model quality gate used.
- Agent has a clear next task when a model degrades.

### EPIC-H: Product Timeline And Research Trail

Goal: Turn isolated pages into a continuous product experience.

Agent tasks:

- Add a timeline page or dashboard module that lists daily advice, market
  snapshot, prediction run, backtest score, and workflow health by date.
- Show changes between adjacent timeline entries: risk level, market sentiment,
  top focus assets, confidence, expected return, downside risk, and task status.
- Link each timeline entry to the relevant advice, prediction, backtest, and
  logs views.
- Design the timeline as a user-facing research history, with technical details
  available but secondary.

Acceptance criteria:

- Users can answer "what changed since the last run?" from one timeline.
- Each timeline row links to underlying evidence.
- The timeline handles missing stages without breaking the story.

### EPIC-I: Red/Green Market Visual Semantics

Goal: Make gains, losses, and deltas visually immediate while preserving
accessibility.

Agent tasks:

- Introduce CSS utility classes for market-positive, market-negative,
  market-neutral, warning, and failed states.
- Apply red to positive returns/gains and green to negative returns/losses in
  recommendation cards, prediction cards, backtest tables, fund screening, data
  tables, and charts.
- Pair color with arrows, signs, or labels so color is not the only signal.
- Keep operational health colors separate from market performance colors.

Acceptance criteria:

- All return-like fields have consistent red/green treatment.
- Status values such as success/failure do not reuse market gain/loss colors in
  a confusing way.
- Tests or visual smoke checks cover at least dashboard, predictions, and fund
  screening.

## Iteration Roadmap

### Phase 1: Trust And Explainability

Primary outcome: users trust what they are seeing and understand the limits.

Scope:

- Daily decision brief.
- Freshness and coverage trust layer.
- Evidence chips replacing raw JSON.
- Guided empty/missing states.

Exit criteria:

- 首页 30 秒可读懂今日姿态。
- 建议页 2 次点击可追溯证据。
- 数据滞后和缺失状态不可被忽略。

### Phase 2: Actionable Research Workflows

Primary outcome: users can compare assets and funds without reading raw tables.

Scope:

- Asset-level forecast cards.
- Product timeline for daily research history.
- Product classification and category-aware filters.
- Fund screening filters and profile presets.
- Daily research trail comparing prior advice.
- Better visual risk semantics.

Exit criteria:

- 用户能沿时间轴查看每日建议、市场状态、预测和任务健康的变化。
- 理财产品先分类再筛选，不同分类有不同筛选维度。
- 预测页按资产聚合，重复 horizon 噪音明显降低。
- 基金页支持至少 3 个筛选条件和 1 个默认画像排序。
- 涨跌、收益和变化值使用统一红绿标记，并有箭头或文字辅助。
- 历史建议能显示风险、资产和仓位建议的变化。

### Phase 3: Accuracy And Stability Feedback Loop

Primary outcome: model quality and system health actively guide the product.

Scope:

- Model quality dashboard.
- Calibration and degradation alerts.
- Daily workflow health console.
- Agent repair and rerun guidance.

Exit criteria:

- 每个参与建议的模型都有可见评分和样本窗口。
- 失败任务能定位到阶段、影响范围和恢复命令。
- Agent 可以根据页面状态创建下一步修复或优化任务。

### Phase 4: Personalization And Portfolio Context

Primary outcome: advice becomes more personally useful while staying bounded.

Scope:

- User risk profile persistence.
- Investment horizon and liquidity preference.
- Watchlist and simulated portfolio tracking.
- Advice comparison against user target allocation.

Exit criteria:

- 同一市场状态下，保守/中等/激进用户看到的建议差异更具体。
- 用户能理解建议对自己组合的影响，而不是只看市场通用观点。
- 所有个性化建议仍保留风险提示和证据链。

### Phase 5: Expert Committee Virtual Investing

Primary outcome: users can compare several virtual investment styles and learn
which styles work under which market conditions.

Scope:

- Four active virtual experts with durable persona names, different styles,
  preferences, model focus, and risk budgets.
- Initial virtual capital such as CNY 500,000 per expert.
- Daily expert plans that can buy, sell, rebalance, hold, or choose no trade.
- Simulated execution, positions, cash, transactions, and valuation.
- Rolling expert scorecards covering return, drawdown, benchmark excess,
  evidence quality, and mandate adherence.
- Probation, retirement, failure lessons, and replacement hiring.
- Expert committee WebUI and MCP/CLI inspection.

Exit criteria:

- 用户可以看到 4 位专家各自的人名、风格、今日计划、虚拟持仓、收益、回撤和评分。
- 专家计划都能追溯到入库预测、回测、市场快照、基金元数据或历史建议。
- 投资失败专家不会被简单删除，而是沉淀失败经验、清退原因和未来招聘禁忌。
- 清退后系统能基于历史经验补充一位新专家，并保持 4 位活跃专家并行。
- 所有专家输出都明确是虚拟研究模拟，不构成真实买卖指令。

### Phase 6: Local Phone Communication

Primary outcome: important research events can reach the user's phone without
making the phone a trading surface.

Scope:

- Channel-neutral communication service and persistence.
- iMessage as the first outbound adapter from the local Mac to an allowlisted
  phone identity.
- Setup verification, dry-run testing, delivery status, error capture, quiet
  hours, rate limits, and idempotency.
- Daily workflow success/failure templates.
- Expert-plan, expert-warning, and expert-retirement templates.
- WebUI and CLI inspection for adapter health and recent outbound messages.
- Future inbound command safety design before any phone-originated command is
  implemented.

Exit criteria:

- Mac 本地系统可以通过 iMessage 向白名单手机发送研究通知。
- 通信失败不会中断数据、预测、建议或专家工作流。
- 所有发送都有状态、错误、幂等键和审计记录。
- 消息内容是摘要和风险提示，不直接倾倒 raw JSON。
- 手机回复类能力先完成安全设计，不直接进入真实交易或自动执行。

### Phase 7: Jarvis AI Investment Assistant

Primary outcome: Jarvis becomes the simple daily interface for the whole
investment system.

Scope:

- Jarvis daily brief persistence.
- Jarvis synthesis over system market information, prediction model output,
  backtest/model quality, expert plans, expert scores, expert current virtual
  returns, and active user preferences.
- First-screen WebUI experience.
- MCP/Agent access to Jarvis structured output.
- Phone summary template through the communication adapter layer.

Exit criteria:

- 用户每天先看到贾维斯，而不是先读市场表格、模型表格或专家日志。
- 贾维斯输出当天关注方向、一句话结论、模型预测、每位专家的预测/动作/分数/当前收益和风险提示。
- 贾维斯能解释模型和专家分歧，而不是只给一个黑盒结论。
- 所有贾维斯建议都能追溯到市场快照、预测、回测、专家计划、专家评分和任务日志。
- 贾维斯可以生成适合手机通知的简短摘要，但不直接触发真实交易。

## Future Phase Template

### Phase N: Title

Date:

Reviewed URL:

### Long-Term Goal Alignment

### Current Product Shape

### Acceptance Judgment

### Key Product Gaps

### Next Iteration Target

### Recommended Improvements

### Agent Work Packages

### Success Criteria
