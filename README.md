# Investment Forecasting

这是一个持续演进的 AI 投资理财项目，目标是搭建一个可靠、可复现、可审计、中文友好的本地投资研究与提醒系统。系统不应该只空洞展示数据，而要把完整数据、涨幅曲线、量化预测、预测入库、未来真实值评分、具体关注标的和风险提示串成闭环，帮助用户知道“近期应该重点关注什么、为什么、风险边界在哪里”。

> 重要说明：本系统输出仅作为投资研究和辅助决策参考，不构成保本承诺、收益承诺或直接投资建议。所有策略和预测都必须展示假设、风险、回测结果和不确定性。

## 本地开发命令

```bash
python3 -m pip install -e '.[dev]'
investment-forecasting db init --db data/investment_forecasting.sqlite3
investment-forecasting ingest mvp --db data/investment_forecasting.sqlite3 --start-date 20240520 --end-date 20240522
investment-forecasting ingest mvp --universe research --db data/investment_forecasting.sqlite3 --start-date 20240101 --end-date 20260523
investment-forecasting ingest full --db data/investment_forecasting.sqlite3 --asset-types stock,etf,fund --max-assets-per-type 12 --start-date 20250101 --end-date 20260523
investment-forecasting ingest full --db data/investment_forecasting.sqlite3 --asset-types stock,etf,fund --max-assets-per-type 50 --offset-per-type 150 --skip-existing-assets --start-date 20250101 --end-date 20260523
investment-forecasting ingest macro --db data/investment_forecasting.sqlite3 --start-date 20240520 --end-date 20240524 --series DGS10,T10YIE,DTWEXBGS
investment-forecasting features calculate --db data/investment_forecasting.sqlite3 --start-date 20240520 --end-date 20240522 --continue-on-error
investment-forecasting market snapshot --db data/investment_forecasting.sqlite3 --date 20240522
investment-forecasting forecast run --db data/investment_forecasting.sqlite3 --horizons 5,20,60
investment-forecasting backtest run --db data/investment_forecasting.sqlite3 --horizons 5,20,60 --lookback-days 60
investment-forecasting advice generate --db data/investment_forecasting.sqlite3 --date 20260523
investment-forecasting advice score-outcomes --db data/investment_forecasting.sqlite3 --horizon-days 20
investment-forecasting prefs set --db data/investment_forecasting.sqlite3 --name 稳健账户 --risk-profile conservative --horizon-days 60 --max-equity-pct 0.30 --min-cash-pct 0.25
investment-forecasting prefs list --db data/investment_forecasting.sqlite3
investment-forecasting mcp list-tools
investment-forecasting mcp call get_market_snapshot --db data/investment_forecasting.sqlite3 --args '{}'
investment-forecasting-mcp --db data/investment_forecasting.sqlite3
investment-forecasting daily run --db data/investment_forecasting.sqlite3 --date 20260523 --horizons 5,20,60 --lookback-days 60
investment-forecasting web run --db data/investment_forecasting.sqlite3 --host 127.0.0.1 --port 8765
scripts/restart_web.sh
investment-forecasting calibration run --db data/investment_forecasting.sqlite3 --date 20260523 --horizons 5,20,60 --lookback-days 60
python3 -m pytest
```

`scripts/restart_web.sh` 是推荐的后台服务重启命令。macOS 下会使用 `launchctl` 注册常驻后台服务；其他环境回退到 `nohup`。重启后会打印当前数据库关键行数，便于确认服务没有指向空库。可通过环境变量覆盖参数：

```bash
DB_PATH=data/investment_forecasting.sqlite3 HOST=127.0.0.1 PORT=8765 scripts/restart_web.sh
```

AKShare 数据抓取会自动依次尝试当前网络环境、强制直连和本地代理 `127.0.0.1:7890`。如果 `ingest full` 的东方财富股票列表接口不可用，系统会回退到 AKShare 的 A 股代码/名称列表接口继续发现股票池。`--max-assets-per-type` 可按股票/ETF/基金分别限额，`--offset-per-type` 可按类型推进下一批，`--skip-existing-assets` 会跳过本地已注册资产，适合把股票、ETF、公募基金逐批推进到全量覆盖。

## 项目目标

当前阶段的目标不是做一个演示页面，而是把系统推进到可给真实用户试用的投资研究工作台：

- 数据更完整：默认保留轻量 MVP 标的池，同时提供 `--universe research` 扩展到更多指数、ETF、基金和代表性股票；`ingest full` 会从 AKShare 动态发现 A 股、ETF、公募基金列表并批量拉取历史数据，支持用 `--max-assets`、`--max-assets-per-type`、`--offset-per-type` 和 `--skip-existing-assets` 分批推进到更全量覆盖。
- 曲线先行：任何预测前都要先能看到资产历史行情/净值和累计涨幅曲线，让用户理解趋势、波动和回撤背景。
- 预测入库：所有模型预测写入 `model_predictions`，包含周期、上涨概率、预期收益区间、下行风险、置信度和输入窗口。
- 事后评分：预测和建议到期后要用未来真实值评分，持续记录方向准确率、收益误差、风险识别、跑赢基准和综合分。
- 建议具体：每日建议必须点名近期优先关注或谨慎观察的股票、ETF 或基金，并说明触发条件、仓位范围和减仓条件。
- 偏好可配置：用户可以设置风险偏好、投资期限、权益仓位上限和现金下限，后续每日建议必须按活跃设置约束输出。
- UI 有价值：WebUI 以中文呈现总览、涨幅曲线、基金筛选、预测排序、回测评分、每日建议和任务日志，避免只堆表格。
- Git 管理：项目已初始化为 git 仓库，后续所有可运行变更都应通过提交记录沉淀，便于回滚、审计和协作。

## 一期 MVP 范围

MVP 不是追求一次性做出复杂交易系统，而是先搭建可靠闭环：

1. 数据可获取：支持 MVP 小池和 research 扩展池，失败时记录任务日志和数据质量报告。
2. 数据可持久化：资产、行情/净值、基金信息、宏观、特征、预测、回测、建议、建议评分都落 SQLite。
3. 曲线可查看：WebUI 数据页按资产展示行情/净值和累计涨幅曲线。
4. 指标可复现：收益、波动、回撤、夏普、Calmar、胜率和市场状态从入库数据计算。
5. 模型可回测：预测使用历史窗口，回测使用滚动切分和未来真实收益评分。
6. 建议可执行：输出激进/中等/保守三类仓位，并点名近期关注标的。
7. 用户偏好可持久化：风险偏好、投资期限和仓位约束会影响每日建议。
8. 每日任务可自动运行：每日流程完成采集、特征、市场快照、预测、回测、建议和成熟建议评分。
9. 用户可通过中文 WebUI 查看结果，而不是阅读原始数据库。

## 系统架构

```text
数据源
  A股行情 / 指数 / ETF / 公募基金 / 宏观数据 / 市场情绪
    ↓
数据服务
  拉取、清洗、标准化、增量更新、异常检测
    ↓
SQLite 持久化
  原始数据、清洗数据、特征、预测、回测、建议、任务日志
    ↓
量化分析服务
  指标计算、风险评估、模型预测、情景分析、组合建议
    ↓
MCP 服务
  向 AI 暴露可调用工具
    ↓
Codex 定时任务
  每天 8 点执行数据分析和建议生成
    ↓
WebUI
  中文总览、涨幅曲线、预测排序、每日建议、历史评分、模型评估
```

## 数据需求

一期优先支持以下数据，并逐步从小样本扩展为更全量的研究数据：

- A 股：日线行情、成交量、成交额、涨跌幅、复权价格。
- 指数：沪深 300、中证 500、创业板指、上证指数等主流指数。
- ETF：宽基 ETF、行业 ETF、债券 ETF、货币 ETF。
- 公募基金：基金列表、基金类型、单位净值、累计净值、历史净值、近阶段收益。
- 偏股型基金：股票型基金、混合型偏股基金、指数增强基金。
- 风险指标：收益率、波动率、最大回撤、夏普比率、Calmar 比率、胜率。
- 市场环境：指数趋势、市场宽度、成交热度、风格轮动、股债性价比。

当前可用标的池：

- `mvp`：少量指数、ETF、基金和股票，用于本地快速验证。
- `research`：扩展的指数、宽基/行业/债券/货币 ETF、偏股基金和代表性股票，用于更接近真实使用的研究样本。
- `full`：通过 AKShare 动态发现 A 股、ETF、公募基金列表，再按日期区间拉取历史行情/净值；2026-05-23 探测到候选池约 23,952 个资产，其中股票 5,522、ETF 1,475、公募基金 16,955。大批量运行建议用 `--max-assets-per-type` + `--offset-per-type` 分批入库，并用 `--skip-existing-assets` 避免重复抓取。
- 后续目标：继续引入 Tushare、行业分类、基金持仓和资金流，形成更稳定的全量资产池。

优先数据源：

- AKShare：用于快速接入 A 股、指数、ETF、公募基金数据。
- Tushare Pro：作为后续增强数据源，用于更规范的行情、财务、基金持仓等数据。
- FRED 或其他宏观数据源：用于补充海外利率、通胀、美元指数等宏观变量。

## SQLite 持久化设计

一期使用 SQLite，便于本地开发、任务调度和 WebUI 查询。后续如数据规模扩大，可迁移到 PostgreSQL 或 DuckDB。

建议表结构：

```text
assets
  资产基础信息：代码、名称、类型、市场、状态

price_daily
  股票、指数、ETF、基金的日频行情或净值

fund_info
  基金基础信息、类型、费率、基金经理、规模

features_daily
  量化特征：收益率、动量、波动率、回撤、估值、市场状态

model_predictions
  模型预测结果：预测周期、上涨概率、预期收益、下行风险、置信度

backtest_runs
  回测任务记录：样本区间、参数、指标、模型版本

backtest_results
  回测明细：每个预测点的真实结果、预测结果、评分

daily_advice
  每日理财建议：市场判断、资产建议、风险等级、建议等级、AI 总结

user_preferences
  用户偏好：风险偏好、投资期限、权益上限、现金下限、活跃状态

task_logs
  定时任务日志：运行时间、状态、错误信息、耗时

market_snapshots
  市场环境：指数趋势、市场宽度、成交热度、股债性价比、情绪代理

macro_observations
  宏观观测：FRED 利率、通胀预期、美元流动性等免费序列

data_quality_reports
  数据质量检查：异常、缺口、重复和更新状态
```

## 量化预测与模型校准

系统需要在核心功能开发期采集一段时间的旧数据，用历史数据进行回测和模型校准。

核心方法：

- 使用 `N-x` 时间点之前的数据生成预测。
- 预测未来 `x` 天收益、回撤、跑赢基准概率或风险状态。
- 等待或读取真实的后 `x` 天结果。
- 对预测结果和真实结果进行评分。
- 使用多段历史数据集进行训练、验证和测试，避免只在单一区间有效。

示例：

```text
样本 A：2018-01-01 至 2020-12-31
样本 B：2021-01-01 至 2022-12-31
样本 C：2023-01-01 至 2025-12-31

在每个时间点 T：
  只使用 T 之前的数据
  预测 T + x 个交易日后的结果
  对比真实结果
  记录预测误差、方向正确率、收益表现和回撤表现
```

预测目标包括：

- 未来 5 / 20 / 60 个交易日上涨概率。
- 未来 20 / 60 个交易日预期收益区间。
- 未来 20 / 60 个交易日最大回撤风险。
- 是否跑赢沪深 300、中证偏股基金指数或同类基金平均。
- 当前市场适合激进、中等还是保守配置。

## 建议等级

每日建议需要按用户风险偏好输出三种等级，并且必须包含具体标的关注列表：

### 激进型

适合风险承受能力较高、可接受较大波动的用户。

- 更高权益仓位。
- 更关注成长、行业轮动、弹性资产。
- 明确最大回撤风险和减仓条件。
- 给出 2-3 个近期优先关注的股票/ETF/基金，仅在置信度、预期收益和风险边界同时达标时分批行动。

### 中等型

适合希望在收益和波动之间平衡的用户。

- 权益、债券、现金类资产均衡配置。
- 分批买入或定投。
- 根据市场状态动态调整仓位。
- 给出 1-2 个主要关注标的，并强调组合分散和止损/降仓条件。

### 保守型

适合低风险偏好或短期资金安全要求较高的用户。

- 更高现金、货币基金、短债或低波动资产比例。
- 降低权益暴露。
- 优先控制回撤和流动性风险。
- 仅给出低波动或观察型关注标的，权益暴露必须显著低于激进/中等型。

## 预测建议评分

为了持续优化模型，每条预测和建议都需要评分。

评分维度：

- 方向准确率：是否判断对上涨、下跌或震荡。
- 收益误差：预测收益与实际收益的偏差。
- 风险识别：是否提前识别主要回撤风险。
- 跑赢基准：建议组合是否跑赢对应基准。
- 回撤控制：最大回撤是否低于预期风险边界。
- 建议可执行性：仓位建议是否清晰，是否包含触发条件。

建议评分输出：

```text
prediction_score: 0-100
risk_score: 0-100
advice_score: 0-100
overall_score: 0-100
```

## MCP 服务需求

MCP 服务负责向 AI 暴露可调用的结构化工具。AI 不直接猜测行情，而是调用 MCP 获取数据、指标、模型结果和回测结果。

一期 MCP 工具建议：

```text
get_asset_list
  获取资产列表，支持按股票、指数、ETF、基金、偏股型基金筛选

get_asset_history
  获取指定资产的历史行情或净值

get_fund_metrics
  获取基金收益、波动、回撤、夏普、同类排名等指标

get_market_snapshot
  获取当前市场状态摘要

run_forecast
  对指定资产或组合执行量化预测

run_backtest
  对指定模型、资产、区间和预测周期执行回测

get_daily_advice
  获取某天生成的理财建议

generate_daily_advice
  触发一次完整的数据分析和建议生成
```

MCP 返回结构应尽量使用 JSON，保证可解析、可存档、可回测。

## Codex 定时任务

需要建立一个每日定时任务：

```text
时间：每天 08:00
动作：自动请求 Codex CLI
目标：完成一次数据更新、量化分析、模型预测、风险评估和每日理财指导建议生成
输出：写入 SQLite，并在 WebUI 可查看
```

每日任务流程：

```text
1. 拉取最新行情、基金净值和市场数据
2. 更新 SQLite
3. 计算最新特征和风险指标
4. 执行预测模型
5. 生成激进、中等、保守三类建议
6. 对比历史建议表现并更新评分
7. 生成今日理财指导摘要
8. 写入 daily_advice 和 task_logs
```

## WebUI 需求

WebUI 用于查看系统生成的数据和建议，不是营销页面。默认界面必须中文友好、直接服务投资判断。

一期页面建议：

- 首页仪表盘：今日市场状态、总体风险等级、今日建议摘要、近期优先关注标的。
- 数据页：资产列表、历史净值/行情、累计涨幅曲线、指标表。
- 基金页：偏股型基金筛选、收益/回撤/评分排名。
- 预测页：模型输出、上涨概率、预期收益、下行风险，并按关注价值排序。
- 每日建议页：激进、中等、保守三类建议和仓位参考。
- 回测页：历史预测评分、回测收益、最大回撤、跑赢基准情况。
- 任务日志页：每日任务运行状态、错误信息、耗时。

## AI 分工

系统中 AI 的职责：

- 理解用户目标和风险偏好。
- 调用 MCP 工具获取数据和模型结果。
- 整理每日分析报告。
- 解释预测结果、风险来源和关键假设。
- 对激进、中等、保守三类用户生成不同表达。
- 帮助开发、调试和持续优化系统。

系统中量化服务的职责：

- 拉取和清洗数据。
- 计算指标和特征。
- 执行预测模型。
- 进行回测和评分。
- 输出结构化、可复现的结果。

## 开发原则

- 所有投资建议必须可追溯到数据和模型输出。
- 所有模型必须有样本外回测结果。
- 所有预测必须包含风险和不确定性。
- 所有定时任务必须记录日志。
- 所有数据更新必须可重试、可检查、可回滚。
- 不输出保本、稳赚、确定性收益等结论。

## 后续演进方向

- 引入更多数据源：Tushare Pro、基金持仓、行业配置、资金流、宏观数据。
- 引入多模型集成：LightGBM、XGBoost、时间序列模型、情绪模型。
- 支持用户画像：风险偏好、投资期限、资金流动性需求。
- 支持组合优化：资产相关性、目标波动率、风险预算、再平衡。
- 支持模拟组合：记录每日建议的模拟交易和真实表现。
- 支持多账户或多策略管理。
- 支持更完整的 MCP 工具集和 WebUI 交互。
