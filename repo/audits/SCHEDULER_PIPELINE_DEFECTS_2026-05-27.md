# 定时任务全链路缺陷单（2026-05-27）

## 结论

当前系统的基础模块、WebUI、Codex runtime、专家团、Jarvis 和通信服务具备可运行实现，单元测试整体通过；但从产品目标看，定时任务支撑的“市场数据 -> 资讯 -> 模型预测 -> 专家团 -> Jarvis -> 短讯”闭环尚未完整成立。

2026-05-27 修复进度：

- D-001 至 D-005 已修复：scheduler 的 news、market context、price/NAV、features、model post-close 不再只是水位/计划；它们开始调用真实业务服务，并以 job-specific output 作为 success 证据。
- D-007/D-008 已补回归：专家 buy/sell agent action 与虚拟组合成本、已实现/未实现收益计算有更强测试保护。
- D-009 已补强：Jarvis readiness 会报告上游 scheduler 证据是否真实执行，便于 Jarvis 降级 stale/degraded 证据。
- D-010/D-011 已补强：scheduler run 输出 `execution_mode`，MCP 和设置页能区分 `real_provider`、`real_model_run`、`real_calculation`、`readiness_only` 等语义。
- D-012 已修复：README 已改成“系统 scheduler + Codex role runtime”的调度架构说明。
- IT-001/IT-002 已补强：新增 fake provider + fake Codex 的 scheduler 全链路集成测试，按顺序验证 news、market context、price/NAV、features、model、expert、Jarvis 均产生真实业务输出或真实 runtime 结果。
- IT-004 已补强：新增 provider backoff 过期后的恢复测试，成功拉数后会清空 `backoff_until`、失败计数和失败原因。
- 追加修复：`market_context_intraday` 不再在 scheduler 持有 SQLite 连接时嵌套调用会重新打开写连接的 capital-flow ingest，改为在同一连接内调用 provider 并落库，避免 `database is locked`。
- 复查追加修复：`model_post_close` 不再在写入 readiness watermark 后持锁调用模型服务；市场资金流和特征计算返回 0 行时不再标记 success 或推进成功水位。
- 验证：`python3 -m pytest -q` 通过，240 passed。

原主要缺陷是：系统 scheduler 能注册、到点、记录运行，并能触发专家/Jarvis agent；但多个前置 job 只推进水位、统计计划或做 readiness gate，没有真正执行增量拉数、特征重算、预测、回测、监控和建议生成。2026-05-27 本轮已将这些 P0 handler 接入真实业务服务，并补充 success 语义测试；后续仍需通过真实 provider 环境的定时运行观察来验证外部数据源稳定性。

验证证据：

- `python3 -m pytest -q`：240 passed。
- Web smoke：`/`、`/opportunities`、`/experts`、`/evidence`、`/settings`、`/jarvis`、`/communication` 均返回 200。
- Codex readiness：`ok=true`，`resolved_bin=/Users/wonderwall/.nvm/versions/node/v24.15.0/bin/codex`，登录状态正常。
- 通信配置：`owner_phone` + `imessage` verified，系统 probe 本次跳过。
- 本地库新鲜度：`news_items` 最新 `2026-05-24 17:45:00`，而 `price_daily`、`features_daily`、`model_predictions` 最新为 `2026-05-26`，`jarvis_daily_briefs` 最新为 `2026-05-28`。
- 新增 scheduler 集成测试中，`news_hourly_incremental`、`market_context_intraday`、`price_nav_post_close`、`features_post_close`、`model_post_close` 均以 job-specific output predicate 验证真实输出；真实外部 provider 的稳定性仍需依赖后续定时运行观察。

## 模块缺陷

### D-001 Scheduler / News 增量资讯任务没有真实入库

- 严重级别：P0
- 目标意图：每两小时补齐资讯增量窗口，供 Codex 专家和 Jarvis 通过新闻证据检索使用。
- 当前证据：`src/investment_forecasting/scheduler/service.py` 的 `_run_news_incremental` 只计算窗口并更新 `scheduler_watermarks`，metadata 写入 `real_provider_calls=false`，没有调用 `data.news.ingest_news`。
- 当前影响：scheduler 可显示 success，但 `news_items` 最新仍停在 `2026-05-24 17:45:00`；专家/Jarvis 可能基于陈旧新闻做判断。
- 建议修复：将 `news_hourly_incremental` 接入 `ingest_news`，按 source/watermark 计算 bounded window，真实写入 `news_items`、`news_item_links`、`news_item_tags`，并在 provider 失败时进入 backoff/deferred。
- 已有测试：`tests/test_news_evidence.py` 覆盖 `ingest_news` 本身；`tests/test_scheduler.py` 覆盖 scheduler 水位和非全量行为。
- 需补单测：
  - `test_scheduler_news_incremental_calls_ingest_news_with_bounded_window`
  - `test_scheduler_news_incremental_updates_watermark_to_actual_ingested_end`
  - `test_scheduler_news_incremental_provider_failure_records_backoff_and_task_log`

### D-002 Scheduler / Market Context 任务没有真实同步资金流

- 严重级别：P0
- 目标意图：每两小时同步轻量市场上下文和资金流，保证专家/Jarvis 使用的市场证据新鲜。
- 当前证据：`_run_market_context_incremental` 只选取 market + 20 个股票 subject 并更新 watermark，metadata 为 `real_provider_calls=false`，没有调用 `data.capital_flow.ingest_capital_flow`。
- 当前影响：任务 success 只代表计划成功，不代表 `capital_flow_observations` 增量更新成功；Jarvis 中资金流证据可能滞后或与 scheduler 状态不一致。
- 建议修复：接入 `ingest_capital_flow`，按 scope/subject/provider 做 request cap、delay、backoff，并记录真实 updated/skipped 数。
- 已有测试：`tests/test_capital_flow.py` 覆盖资金流入库；`tests/test_scheduler.py` 覆盖 provider budget/backoff。
- 需补单测：
  - `test_scheduler_market_context_calls_capital_flow_ingestion_for_market_and_tracked_stocks`
  - `test_scheduler_market_context_respects_request_cap_without_advancing_unfetched_watermarks`
  - `test_scheduler_market_context_records_provider_failure_and_deferred_status`

### D-003 Scheduler / Price NAV 收盘任务没有真实拉取行情/净值

- 严重级别：P0
- 目标意图：收盘后只补齐落后资产的行情/NAV，不做全量历史抓取。
- 当前证据：`_run_price_nav_incremental` 只计算 stale assets 并写 watermark，metadata 为 `real_provider_calls=false`，没有调用 AKShare/Tushare provider 的历史行情方法，也没有写 `price_daily`。
- 当前影响：如果某天行情缺失，scheduler 会记录 planned/success，但不会补齐 `price_daily`；后续 features/model 可能基于旧价格继续运行。
- 建议修复：为 price job 增加 provider adapter 注入，按 asset 类型调用对应增量 history/NAV 接口，写入 `price_daily` 和 data quality/task logs；watermark 只能推进到实际成功写入日期。
- 已有测试：`tests/test_akshare_ingestion.py` 覆盖 provider/ingestion 层；`tests/test_scheduler.py` 覆盖 stale assets 计划。
- 需补单测：
  - `test_scheduler_price_nav_fetches_only_stale_assets`
  - `test_scheduler_price_nav_does_not_mark_success_when_provider_returns_no_rows`
  - `test_scheduler_price_nav_partial_success_keeps_failed_asset_watermark_behind`

### D-004 Scheduler / Features 任务没有调用特征计算

- 严重级别：P0
- 目标意图：行情补齐后只重算受影响资产/date range 的特征。
- 当前证据：`_run_features_incremental` 只比较 `latest_price_date` 和 `latest_feature_date`，写 affected watermark，metadata 为 `real_provider_calls=false`，没有调用 `quant.features.calculate_features_for_db`。
- 当前影响：新行情即使被补齐，也不会由 scheduler 自动产生 `features_daily`；model gate 可能被 watermark 误导。
- 建议修复：对 affected asset/date range 调用特征计算服务，并让结果返回真实 inserted/updated/failed 统计。
- 已有测试：`tests/test_features.py` 覆盖特征计算；`tests/test_scheduler.py` 覆盖 affected range 计划。
- 需补单测：
  - `test_scheduler_features_incremental_calls_calculator_for_affected_range`
  - `test_scheduler_features_incremental_does_not_advance_watermark_on_calculation_failure`
  - `test_scheduler_features_incremental_continues_after_asset_failure_when_configured`

### D-005 Scheduler / Model Post Close 只做 readiness gate，没有跑预测、回测、监控和建议

- 严重级别：P0
- 目标意图：特征就绪后固定运行预测、可靠性、监控和建议准备，让专家 T 日晚间读取当天模型证据。
- 当前证据：`model_post_close` 在 `_run_incremental_job` 中只调用 `_run_readiness_gate_job`，返回 `readiness_gate_passed`，没有调用 `run_latest_forecasts`、`run_backtest`、`run_model_monitoring_report`、`generate_daily_advice`、`score_matured_advice` 或模型可靠性治理命令。
- 当前影响：scheduler 显示 model job success 不代表当天模型、监控和建议已刷新。专家/Jarvis 会读取旧 `model_predictions` / `daily_advice`，形成“后置 AI 正常但证据未更新”的假闭环。
- 建议修复：将 model job 改为编排真实服务，并区分 `success`、`partial`、`degraded`、`deferred`；没有足够新鲜 feature 时不应成功。
- 已有测试：`tests/test_backtest.py`、`tests/test_monitoring.py`、`tests/test_advice.py` 覆盖各服务；`tests/test_scheduler.py` 仅覆盖 readiness。
- 需补单测：
  - `test_scheduler_model_post_close_runs_forecast_backtest_monitoring_and_advice`
  - `test_scheduler_model_post_close_blocks_when_price_or_features_stale`
  - `test_scheduler_model_post_close_records_partial_failure_without_triggering_experts`

### D-006 Daily Workflow 与新 Scheduler 目标存在割裂

- 严重级别：P1
- 目标意图：系统调度应拥有数据、特征、预测、建议、Jarvis/短信闭环；旧 daily workflow 可作为手动完整流程或被 scheduler 复用。
- 当前证据：`workflows/daily.py` 的 `run_daily_workflow` 能顺序执行 ingest/features/snapshot/forecast/backtest/advice/monitoring/Jarvis/notification，但 scheduler 没有复用这条完整流程；scheduler 各 job 另有水位实现。
- 当前影响：手动 daily workflow 和系统 scheduler 产生两套语义：手动跑可以真实生成，定时跑只部分标记。
- 建议修复：明确架构：要么 scheduler 分阶段调用同一批服务函数，要么 daily workflow 拆成可复用 job steps；禁止存在一条“真实流程”和一条“状态流程”。
- 已有测试：`tests/test_daily_workflow.py` 覆盖 daily workflow。
- 需补集成测试：
  - `test_scheduler_post_close_pipeline_reuses_real_daily_services`
  - `test_daily_workflow_and_scheduler_produce_consistent_task_logs_for_same_date`

### D-007 Expert Agent 运行已通，但需要防止旧缺陷回归

- 严重级别：P1
- 目标意图：T 日每个专家基于证据提交一个虚拟动作，系统验证并记录计划、交易、组合估值、reason/analysis/reflection。
- 当前证据：最新专家 runs 4/4 completed，卖出动作已能生成交易；但这是近期修复点，历史记录里曾出现 agent 输出 sell 但持久化为 no_trade。
- 当前影响：如果回归，会造成专家页面和真实组合记录不一致，Jarvis 读取错误专家行为。
- 建议修复：保留当前 sell/buy/no_trade 执行路径，并增加更强的集成级断言：从 agent output -> tool call payload -> expert_plan -> virtual_transaction -> valuation 全链路一致。
- 已有测试：`tests/test_experts.py` 已覆盖 sell action execution；`tests/test_portfolio.py` 覆盖组合交易。
- 需补单测：
  - `test_expert_agent_buy_action_persists_quantity_cost_and_transaction`
  - `test_expert_agent_output_and_tool_submission_conflict_is_rejected_or_resolved_deterministically`
  - `test_expert_plan_detail_exposes_reason_analysis_reflection_and_transaction_link`

### D-008 Portfolio 收益计算需要更强的成本/持仓回归测试

- 严重级别：P1
- 目标意图：买卖必须记录购买量、成本价、累计成本和卖出实现收益；专家收益曲线应按成本和后续涨跌价计算。
- 当前证据：组合模块有持仓、交易、估值测试；但本轮关注点要求“按其成本和涨跌价计算收益”，需要覆盖多次买入、部分卖出、剩余成本、已实现/未实现收益的组合场景。
- 当前影响：收益曲线若只看当前价格或总资产，可能掩盖成本基准错误。
- 建议修复：补足 average cost / realized pnl / unrealized pnl / equity curve 的多交易场景测试。
- 已有测试：`tests/test_portfolio.py` 覆盖基础买卖、估值。
- 需补单测：
  - `test_portfolio_partial_sell_realized_pnl_uses_average_cost`
  - `test_portfolio_remaining_position_cost_basis_after_partial_sell`
  - `test_expert_equity_curve_reflects_cash_plus_position_market_value`

### D-009 Jarvis T+1 与短讯链路可跑通，但依赖上游证据 freshness

- 严重级别：P1
- 目标意图：T+1 Jarvis 在 T 专家终态后生成日报，并默认通过通信 adapter 发短讯。
- 当前证据：`_run_agent_runtime_job` 对 Jarvis 默认读取 `INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY`，缺省为 `owner_phone`，并使用 iMessage；最新 dry-run 已生成 `outbound_messages`。Codex readiness 正常。
- 当前影响：Jarvis 可以成功，但如果 D-001 至 D-005 未修，Jarvis 成功只是“基于旧证据成功”。另外真实发送未在本轮执行，只验证了 dry-run 和配置。
- 建议修复：Jarvis readiness 应纳入上游数据/模型 freshness 状态，并在短信正文中明确 degraded/stale；真实发送只在 allowlist + dry_run=false 时执行。
- 已有测试：`tests/test_jarvis.py`、`tests/test_communication.py`、`tests/test_agent_runtime.py`。
- 需补单测：
  - `test_jarvis_scheduler_degrades_or_blocks_when_model_post_close_not_real_success`
  - `test_jarvis_notification_defaults_to_owner_phone_when_env_missing`
  - `test_jarvis_sms_body_includes_stale_evidence_warning`

### D-010 MCP/API 工具面完整，但缺少 scheduler 真实执行状态契约测试

- 严重级别：P2
- 目标意图：AI 只能通过结构化 MCP/API 工具读取证据和提交结果，不能直接猜测行情或绕过系统验证。
- 当前证据：MCP tools 已列出基础资产、历史、指标、市场、建议、专家、Jarvis、scheduler health 等工具；`tests/test_mcp_tools.py` 覆盖部分工具。
- 当前影响：MCP 可以读取 scheduler status，但缺少契约保证：`success` 是否代表真实数据/模型执行完成，还是仅代表 watermark 已推进。
- 建议修复：为 scheduler run status 增加 `execution_mode` 或 `real_outputs` 字段，并让 MCP/WebUI 区分 planned/readiness/real。
- 已有测试：`tests/test_mcp_tools.py`、`tests/test_mcp_server.py`。
- 需补单测：
  - `test_mcp_scheduler_status_exposes_real_execution_mode`
  - `test_mcp_jarvis_readiness_reports_stale_upstream_evidence`

### D-011 WebUI 健康页可访问，但应更清楚暴露“成功但未真实更新”

- 严重级别：P2
- 目标意图：用户需要知道今天什么任务失败了、没跑，或者证据是否陈旧。
- 当前证据：Web smoke 全部 200，`scheduler today-status` 可输出 success/deferred/not_yet_due；但当前 metadata 中 `real_provider_calls=false` 没有作为用户级风险强提示。
- 当前影响：用户看到任务 success 可能误以为数据已刷新。
- 建议修复：设置/系统健康中增加“执行模式：真实执行/水位计划/readiness-only”，并把 stale data 展示为 warning。
- 已有测试：`tests/test_web_app.py` 覆盖路由和部分内容。
- 需补单测：
  - `test_settings_system_health_marks_readiness_only_jobs_as_warning`
  - `test_evidence_page_shows_news_freshness_gap`

### D-012 文档目标存在旧架构描述

- 严重级别：P2
- 目标意图：当前项目目标以系统 scheduler 为调度主体，Codex 是专家/Jarvis runtime。
- 当前证据：`repo/PROJECT.md` 已说明 system-owned scheduler 和 two-hour incremental jobs；但 `README.md` 仍写“每天 08:00 自动请求 Codex CLI，完成数据更新、量化分析、模型预测、风险评估和每日建议”。
- 当前影响：新 agent 或研发会误以为 Codex CLI 本身仍是每日数据/模型 scheduler。
- 建议修复：更新 README，将“Codex 定时任务”改为“系统 scheduler + Codex role runtime”，并标注市场/资讯两小时、T 专家、T+1 Jarvis/短讯。
- 已有测试：无文档一致性测试。
- 需补检查：
  - `rg` 文档验收：README/PROJECT/STATUS/SPEC-012/SPEC-013 不再出现互相矛盾的调度表述。

## 集成测试缺陷

### IT-001 缺少真实 post-close pipeline 集成测试

- 缺陷：没有一个测试证明 `price_nav_post_close -> features_post_close -> model_post_close -> expert_t_day_agents -> jarvis_t_plus_one -> outbound_messages` 能在同一临时数据库中按顺序产生真实业务输出。
- 建议测试：使用 fake provider + fake Codex adapter + dry-run communication，断言每阶段真实表行数或日期推进，而不是只断言 scheduler_runs success。

### IT-002 缺少“success 语义”集成测试

- 缺陷：当前 `tests/test_scheduler.py` 中有测试断言 `real_provider_calls is False`，这保护了不做全量抓取，但没有保护“success 必须意味着真实输出已完成”。
- 建议测试：`scheduler_runs.status='success'` 时必须满足 job-specific output predicate，例如 news 写入新闻、features 写入 feature、model 写入 prediction/advice/monitoring；否则只能是 `planned`、`skipped`、`deferred` 或 `readiness_only`。

### IT-003 缺少新鲜度门禁集成测试

- 缺陷：Jarvis 可以在上游模型/新闻陈旧时生成简报；目前主要依赖文本里提示 stale，但 scheduler readiness 没有硬性检查所有关键上游日期。
- 建议测试：构造新闻/模型/特征落后日期，断言 Jarvis readiness 返回 degraded 或 blocked，并在 brief/phone 中出现 stale warning。

### IT-004 缺少 provider backoff 到恢复的端到端测试

- 缺陷：有 provider budget/backoff 单测，但缺少“失败进入 backoff -> 后续 due deferred -> backoff 过期后恢复真实拉数”的端到端测试。
- 建议测试：fake provider 第一次抛 throttling，第二次成功，验证 `provider_rate_limits`、`scheduler_runs`、`task_logs` 和 watermark 状态。

### IT-005 缺少真实发送前的通信端到端验收

- 缺陷：本轮只验证了 dry-run 和配置，未验证真实 iMessage 发送；这符合安全策略，但不能作为“手机一定收到”的证据。
- 建议测试/验收：保留自动测试 dry-run；真实发送作为手动验收步骤，记录 `outbound_messages.status='sent'` 或具体 permission error。

## 建议修复顺序

1. 修 D-005：让 `model_post_close` 真实运行预测、回测、监控、建议，并修正 success 语义。
2. 修 D-001/D-002/D-003/D-004：将 news、market、price、features scheduler job 接入真实服务函数，watermark 只按真实结果推进。
3. 加 IT-001/IT-002：先用 fake provider/fake Codex/dry-run 通信建立全链路测试保护。
4. 修 D-009/D-011：Jarvis 和 WebUI 明确暴露 stale/degraded upstream evidence。
5. 修 D-012：同步 README 调度架构，避免后续研发误解。

## 当前可以信任与不能信任的结论

可以信任：

- 本地服务可运行，主要页面可访问。
- Codex CLI runtime 当前可用，专家和 Jarvis agent 能被系统触发。
- 通信 adapter 配置和 dry-run 路径可用。
- scheduler 在 fake provider/fake Codex/dry-run 通信条件下可以按顺序完成“市场数据 -> 资讯 -> 模型预测 -> 专家团 -> Jarvis -> 短讯记录”链路。
- 大部分底层服务已有单元测试，当前全量测试通过。

不能信任：

- 真实外部 provider 的下一次自动触发仍可能因为网络、限流、代理或数据源字段变化失败，需要观察 `scheduler_runs.execution_mode`、`error`、`provider_rate_limits` 和 Web 设置页健康状态。
- iMessage 真实发送仍应作为手动验收项确认；自动化测试只覆盖 dry-run 和配置链路，避免测试环境误发。
