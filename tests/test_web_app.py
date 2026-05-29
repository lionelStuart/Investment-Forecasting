from __future__ import annotations

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.db import (
    connect,
    init_db,
    upsert_asset,
    upsert_communication_adapter_config,
    upsert_communication_recipient,
    upsert_expert,
    upsert_fund_info,
    upsert_price_daily,
)
from investment_forecasting.experts.roster import initialize_default_experts
from investment_forecasting.jarvis.synthesis import generate_jarvis_brief
from investment_forecasting.portfolio.accounting import create_virtual_portfolio, ensure_expert_portfolios, record_virtual_order, value_virtual_portfolio
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot
from investment_forecasting.quant.monitoring import run_model_monitoring_report
from investment_forecasting.scheduler import initialize_scheduler, record_provider_failure, run_scheduler_job
from investment_forecasting.web.app import expert_return_curve, render_route
from tests.test_daily_workflow import seed_asset_with_prices


def primary_nav(html: str) -> str:
    return html.split("<nav>", 1)[1].split("</nav>", 1)[0]


def prepare_web_db(tmp_path):
    db_path = tmp_path / "web.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    seed_typed_asset(db_path, "511010", "国债ETF", "etf", [101, 101.1, 101.2, 101.1, 101.3, 101.4, 101.5])
    seed_typed_asset(db_path, "510300", "沪深300ETF", "etf", [100, 99, 101, 102, 103, 102, 104])
    balanced_fund_id = seed_typed_asset(db_path, "000001", "华夏成长混合", "fund", [1.0, 1.01, 1.02, 1.03, 1.02, 1.04, 1.05])
    aggressive_fund_id = seed_typed_asset(db_path, "000002", "科技成长股票", "fund", [1.0, 0.98, 1.01, 1.04, 1.08, 1.10, 1.12])
    missing_meta_fund_id = seed_typed_asset(db_path, "000003", "资料待补基金", "fund", [1.0, 1.0, 1.01, 1.01, 1.02, 1.02, 1.03])
    seed_fund_info(db_path, balanced_fund_id, "混合型-偏股", "张经理", 26.4, 0.15)
    seed_fund_info(db_path, aggressive_fund_id, "股票型", "王经理", 8.2, None)
    seed_fund_info(db_path, missing_meta_fund_id, None, None, None, None)
    stock_id = seed_typed_asset(db_path, "600519", "贵州茅台", "stock", [1500, 1510, 1520, 1505, 1530, 1540, 1550])
    calculate_features_for_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO macro_observations(series_id, observation_date, value, source, raw_payload)
            VALUES ('DGS10', '2026-05-22', 4.25, 'fred', '{}')
            ON CONFLICT(series_id, observation_date, source) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO capital_flow_observations(
                flow_date, scope, subject_code, subject_name, asset_id,
                pct_change, main_net_inflow, main_net_inflow_pct,
                super_large_net_inflow, large_net_inflow, medium_net_inflow,
                small_net_inflow, source, raw_payload
            )
            VALUES (
                '2026-05-22', 'stock', '600519', '贵州茅台', ?,
                0.012, 12000000, 0.06, 3000000, 9000000, -1000000,
                -11000000, 'test', '{}'
            )
            ON CONFLICT(scope, subject_code, flow_date, source) DO NOTHING
            """,
            (stock_id,),
        )
        conn.execute(
            """
            INSERT INTO fund_holdings(
                fund_asset_id, report_period, holding_type, holding_code,
                holding_name, holding_asset_id, weight_pct, shares,
                market_value, rank, source, raw_payload
            )
            VALUES (?, '2024年4季度股票投资明细', 'stock', '600519',
                    '贵州茅台', ?, 0.082, 120000, 18000000, 1, 'test', '{}')
            ON CONFLICT(fund_asset_id, report_period, holding_type, holding_code, source) DO NOTHING
            """,
            (balanced_fund_id, stock_id),
        )
    calculate_market_snapshot(db_path, snapshot_date="20260523")
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)
    generate_daily_advice(db_path, advice_date="20260523")
    run_model_monitoring_report(db_path, report_date="20260523")
    return db_path


def seed_typed_asset(db_path, code: str, name: str, asset_type: str, values: list[float]) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": code,
                "name": name,
                "asset_type": asset_type,
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for index, value in enumerate(values, start=1):
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": f"2026-01-{index:02d}",
                    "open": value,
                    "high": value,
                    "low": value,
                    "close": value,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": value,
                    "nav": value if asset_type == "fund" else None,
                    "accumulated_nav": value if asset_type == "fund" else None,
                    "raw_payload": None,
                },
            )
    return asset_id


def seed_fund_info(db_path, asset_id: int, fund_type: str | None, manager: str | None, scale: float | None, purchase_fee: float | None) -> None:
    with connect(db_path) as conn:
        upsert_fund_info(
            conn,
            asset_id=asset_id,
            source="test",
            info={
                "fund_type": fund_type,
                "fund_company": "测试基金公司",
                "manager": manager,
                "custodian": None,
                "management_fee": None,
                "custody_fee": None,
                "purchase_fee": purchase_fee,
                "scale": scale,
                "inception_date": None,
                "benchmark": None,
                "strategy": None,
                "objective": None,
                "stage_returns_json": "{}",
                "raw_payload": "{}",
            },
        )


def test_dashboard_renders_empty_database(tmp_path):
    db_path = tmp_path / "empty.sqlite3"
    init_db(db_path)

    html = render_route(db_path, "/", {})
    jarvis_html = render_route(db_path, "/jarvis", {})

    assert "今日简报" in html
    assert "贾维斯今日简报" in html
    assert "今天怎么看?" in html
    assert "为什么?" in html
    assert "能不能信?" in html
    assert "关注哪些资产?" in html
    assert "专家是否一致?" in html
    assert "风险边界和观察条件" in html
    assert "三条理由" in html
    assert "运行健康" in html
    assert "数据采集" in html
    assert "恢复提示" in html
    assert "还没有 Jarvis 关注方向" in html
    assert "还没有 Jarvis 简报" in jarvis_html
    assert "数据新鲜度" in html
    assert "当前数据库" in html
    assert "没有资产或行情数据" in html


def test_workbench_pages_render_with_data(tmp_path):
    db_path = prepare_web_db(tmp_path)

    seed_expert_web_state(db_path)
    seed_communication_web_state(db_path)
    generate_jarvis_brief(db_path, brief_date="20260523")
    pages = ["/", "/opportunities", "/experts", "/evidence", "/settings", "/jarvis", "/timeline", "/market", "/categories", "/themes", "/data", "/funds", "/predictions", "/backtests", "/advice", "/portfolios", "/communication", "/logs"]
    rendered = {page: render_route(db_path, page, {}) for page in pages}

    nav = primary_nav(rendered["/"])
    assert nav.count("<a ") == 5
    assert "今日简报" in nav
    assert "机会池" in nav
    assert "专家团" in nav
    assert "证据" in nav
    assert "设置" in nav
    for legacy_label in ["研究时间线", "产品分类", "数据与曲线", "基金筛选", "预测", "回测评分", "每日建议", "风险设置", "任务日志"]:
        assert legacy_label not in nav

    assert "贾维斯今日简报" in rendered["/"]
    assert "今天怎么看?" in rendered["/"]
    assert "为什么?" in rendered["/"]
    assert "能不能信?" in rendered["/"]
    assert "关注哪些资产?" in rendered["/"]
    assert "专家是否一致?" in rendered["/"]
    assert "风险边界和观察条件" in rendered["/"]
    assert "三条理由" in rendered["/"]
    assert "运行健康" in rendered["/"]
    assert "数据采集" in rendered["/"]
    assert "指标计算" in rendered["/"]
    assert "市场快照" in rendered["/"]
    assert "模型预测" in rendered["/"]
    assert "回测评分" in rendered["/"]
    assert "每日建议" in rendered["/"]
    assert "运行监控" in rendered["/"]
    assert "恢复提示" in rendered["/"]
    assert "风险设置" in rendered["/"]
    assert "打开机会池" in rendered["/"]
    assert "打开证据页" in rendered["/"]
    assert "Jarvis 每日简报" in rendered["/jarvis"]
    assert "今日关注方向" in rendered["/jarvis"]
    assert "模型预测" in rendered["/jarvis"]
    assert "专家观点" in rendered["/jarvis"]
    assert "综合建议" in rendered["/jarvis"] or "均衡观察" in rendered["/jarvis"]
    assert "风险与边界" in rendered["/jarvis"]
    assert "证据入口" in rendered["/jarvis"]
    assert 'href="/predictions"' in rendered["/jarvis"]
    assert 'href="/backtests"' in rendered["/jarvis"]
    assert 'href="/experts"' in rendered["/jarvis"]
    assert "最近研究脉络" in rendered["/"]
    assert "数据新鲜度" in rendered["/"]
    assert "当前数据库" in rendered["/"]
    assert "近期优先关注" in rendered["/"]
    assert "market-signal market-up" in rendered["/"]
    assert "上涨" in rendered["/"]
    assert "机会池筛选" in rendered["/opportunities"]
    assert "产品与资产入口" in rendered["/opportunities"]
    assert "主题机会" in rendered["/opportunities"]
    assert "资产级预测" in rendered["/opportunities"]
    assert "基金候选" in rendered["/opportunities"]
    assert 'href="/categories"' in rendered["/opportunities"]
    assert "证据入口" in rendered["/evidence"]
    assert "回测与模型健康" in rendered["/evidence"]
    assert "市场与资金流" in rendered["/evidence"]
    assert "数据覆盖" in rendered["/evidence"]
    assert "产品分类" in rendered["/categories"]
    assert "固收/现金代理" in rendered["/categories"]
    assert "科技" in rendered["/categories"]
    assert "主题配置" in rendered["/themes"]
    assert "主题总览" in rendered["/themes"]
    assert "代表标的" in rendered["/themes"]
    assert "预测覆盖" in rendered["/themes"]
    market_category = render_route(db_path, "/categories", {"category": ["market_indicator"]})
    assert "查看市场指标" in market_category
    assert 'href="/market"' in market_category
    assert "筛选条件" in rendered["/funds"]
    assert "行业/主题" in rendered["/funds"]
    assert "筛选结果" in rendered["/funds"]
    assert "基金持仓观测" in rendered["/funds"]
    assert "持仓穿透主题暴露" in rendered["/funds"]
    assert "2024年4季度股票投资明细" in rendered["/funds"]
    assert "贵州茅台" in rendered["/funds"]
    assert "消费" in rendered["/funds"]
    assert "8.20%" in rendered["/funds"]
    assert "科技" in rendered["/funds"]
    assert "market-signal market-down" in rendered["/funds"]
    assert "下跌" in rendered["/funds"]
    assert "涨幅曲线" in rendered["/data"]
    assert "range-chip active" in rendered["/data"]
    assert 'type="date" name="start_date"' in rendered["/data"]
    assert "axis-label x-label" in rendered["/data"]
    assert "curve-point" in rendered["/data"]
    assert "curve-tooltip" in rendered["/data"]
    assert "curve-capture" in rendered["/data"]
    assert "point-guide-x" in rendered["/data"]
    assert "point-guide-y" in rendered["/data"]
    assert "point-hit" not in rendered["/data"]
    assert "curve-readout" not in rendered["/data"]
    assert 'data-role="date"' in rendered["/data"]
    assert "资产概览" in rendered["/data"]
    assert "主题识别" in rendered["/data"]
    assert "技术明细" in rendered["/data"]
    assert "行情与量化指标" in rendered["/data"]
    assert "行情 / 净值历史" in rendered["/data"]
    assert "量化指标" in rendered["/data"]
    assert "tab-link active" in rendered["/data"]
    assert 'data-tab-panel="history" role="tabpanel"' in rendered["/data"]
    assert 'data-tab-panel="features" role="tabpanel"' in rendered["/data"]
    feature_tab = render_route(db_path, "/data", {"asset_id": ["1"], "table_tab": ["features"]})
    tab_section = feature_tab.split("<h2>行情与量化指标</h2>", 1)[1].split("<h2>技术明细</h2>", 1)[0]
    assert "量化指标" in feature_tab
    assert "feature_date" in feature_tab
    assert "return_20d" in feature_tab
    assert 'data-tab-target="features"' in tab_section
    assert 'data-tab-url="/data?asset_id=1&amp;table_tab=features"' in tab_section
    assert 'href="/data?asset_id=1&amp;table_tab=features"' not in tab_section
    assert 'aria-selected="true" data-tab-target="features"' in tab_section
    assert 'tab-panel active" data-tab-panel="features"' in tab_section
    gated_html = render_route(db_path, "/jarvis", {})
    assert "信心门" in gated_html or "模型预测" in gated_html
    assert "validation_status" in gated_html
    assert "risk_gate" in gated_html
    assert "模型预测" in rendered["/predictions"]
    assert "资产级预测卡片" in rendered["/predictions"]
    assert "原始模型预测" in rendered["/predictions"]
    assert "5日" in rendered["/predictions"]
    assert "20日" in rendered["/predictions"]
    assert "60日" in rendered["/predictions"]
    assert "消费" in rendered["/predictions"]
    assert "market-signal market-up" in rendered["/predictions"]
    assert "回测任务" in rendered["/backtests"]
    assert "模型健康" in rendered["/backtests"]
    assert "baseline_mean_v1" in rendered["/backtests"]
    assert "每日建议" in rendered["/advice"]
    assert "目标波动率配置" in rendered["/advice"]
    assert "相关性风险预算" in rendered["/advice"]
    assert "波动率证据" in rendered["/advice"]
    assert "相关性证据" in rendered["/advice"]
    assert "模拟组合" in rendered["/portfolios"]
    assert "专家委员会" in rendered["/experts"]
    assert "专家总览" in rendered["/experts"]
    assert "专家收益对比" in rendered["/experts"]
    assert "总览投资 / 收益曲线" not in rendered["/experts"]
    assert 'href="/experts?expert=' in rendered["/experts"]
    assert "查看详情" in rendered["/experts"]
    assert "最新计划与执行" not in rendered["/experts"]
    assert "<table" not in rendered["/experts"]
    assert "手机通信" in rendered["/communication"]
    assert "通信状态" in rendered["/communication"]
    assert "iMessage 设置健康" in rendered["/communication"]
    assert "Allowlist 收件人" in rendered["/communication"]
    assert "最近 outbound messages" in rendered["/communication"]
    assert "+13***5678" in rendered["/communication"]
    assert "+13800135678" not in rendered["/communication"]
    assert "连续研究记录" in rendered["/timeline"]
    assert "每日建议" in rendered["/timeline"]
    assert "模型预测" in rendered["/timeline"]
    assert "回测评分" in rendered["/timeline"]
    assert "任务健康" in rendered["/timeline"]
    assert 'href="/advice?advice_id=' in rendered["/timeline"]
    assert 'href="/predictions"' in rendered["/timeline"]
    assert "缺失" in rendered["/timeline"]
    assert "市场指标" in rendered["/market"]
    assert "市场快照" in rendered["/market"]
    assert "资金流观测" in rendered["/market"]
    assert "主力净流入对象" in rendered["/market"]
    assert "贵州茅台" in rendered["/market"]
    assert "宏观观测" in rendered["/market"]
    assert "美国10年期国债收益率" in rendered["/market"]
    assert "市场快照历史" in rendered["/market"]
    assert "资金流历史" in rendered["/market"]
    assert "风险设置" in rendered["/settings"]
    assert "任务日志" in rendered["/logs"]
    for html in rendered.values():
        assert "<!doctype html>" in html
        assert "贾维斯理财助理" in html
        assert "viewport" in html


def test_dashboard_run_health_surfaces_failed_stage(tmp_path):
    db_path = prepare_web_db(tmp_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO task_logs(task_name, run_date, status, message, error)
            VALUES ('daily_advice_generation', '2026-05-23', 'failed', 'advice failed', 'fixture failure')
            """
        )

    html = render_route(db_path, "/", {})

    assert "每日建议" in html
    assert "运行异常" in html
    assert "advice failed" not in html
    assert "缺建议会缺少当天风险口径" in html
    assert "恢复提示：运行 advice generate" in html


def test_advice_page_can_select_history_and_link_focus_assets(tmp_path):
    db_path = prepare_web_db(tmp_path)
    generate_daily_advice(db_path, advice_date="20260524")

    with connect(db_path) as conn:
        old_advice = conn.execute("SELECT id FROM daily_advice WHERE advice_date = '2026-05-23'").fetchone()
        asset = conn.execute("SELECT id FROM assets ORDER BY id LIMIT 1").fetchone()

    html = render_route(db_path, "/advice", {"advice_id": [str(old_advice["id"])]})

    assert "查看历史建议" in html
    assert "历史记录" in html
    assert "2026-05-23" in html
    assert 'href="/advice?advice_id=' in html
    assert f'href="/data?asset_id={asset["id"]}"' in html


def test_predictions_page_groups_repeated_horizons_by_asset(tmp_path):
    db_path = prepare_web_db(tmp_path)

    html = render_route(db_path, "/predictions", {})
    card_section = html.split("<h2>资产级预测卡片</h2>", 1)[1].split("<h2>技术明细</h2>", 1)[0]

    assert card_section.count("<h3>沪深300ETF</h3>") == 1
    assert "5日" in card_section
    assert "20日" in card_section
    assert "60日" in card_section
    assert "上涨" in card_section
    assert "排名" in card_section
    assert "同类" in card_section
    assert "风险调整" in card_section
    assert "校验" in card_section
    assert any(label in card_section for label in ["一致向上", "分歧观察", "中长期转强", "中长期转弱", "高下行风险"])
    assert "原始模型预测" in html
    assert "rank_score" in html
    assert "validation_status" in html


def test_table_heavy_pages_use_progressive_disclosure(tmp_path):
    db_path = prepare_web_db(tmp_path)

    backtests = render_route(db_path, "/backtests", {})
    advice = render_route(db_path, "/advice", {})
    settings = render_route(db_path, "/settings", {})
    logs = render_route(db_path, "/logs", {})

    assert "模型健康" in backtests
    assert "分周期评分" in backtests
    assert "Rank IC" in backtests
    assert "分桶" in backtests
    assert "治理状态" in backtests
    assert "Jarvis主结论" in backtests
    assert "bucket_spread" in backtests
    assert "information_coefficient" in backtests
    assert "回测任务原始字段" in backtests
    assert "历史预测评分原始行" in backtests
    assert backtests.index("模型健康") < backtests.index("技术明细")

    assert "证据入口" in advice
    assert "预测证据" in advice
    assert "回测证据" in advice
    assert "原始建议 JSON" in advice
    assert "source_prediction_ids" in advice
    assert advice.index("证据入口") < advice.index("原始建议 JSON")

    assert "当前风险画像" in settings
    assert "活跃风险设置" in settings
    assert "系统调度" in settings
    assert "调度 Watermarks" in settings
    assert "已保存设置字段" in settings
    assert settings.index("当前风险画像") < settings.index("活跃风险设置") < settings.index("技术明细")

    assert "运行健康摘要" in logs
    assert "原始任务日志" in logs
    assert logs.index("运行健康摘要") < logs.index("技术明细")


def test_settings_page_shows_scheduler_backoff_and_latest_runs(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    monkeypatch.setattr(service, "_news_provider", lambda: _FakeNewsProvider())
    db_path = prepare_web_db(tmp_path)
    initialize_scheduler(db_path)
    run_scheduler_job(db_path, "news_hourly_incremental")
    record_provider_failure(db_path, "akshare", "HTTP 429 rate limit")

    settings = render_route(db_path, "/settings", {})

    assert "系统调度" in settings
    assert "今日任务" in settings
    assert "news_hourly_incremental" in settings
    assert "execution_mode" in settings
    assert "real_provider" in settings
    assert "Provider Backoff" in settings
    assert "HTTP 429 rate limit" in settings


def test_settings_page_surfaces_scheduler_failed_deferred_and_missed_states(tmp_path, monkeypatch):
    from datetime import datetime

    import investment_forecasting.scheduler.service as service

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime.fromisoformat("2026-05-25T10:30:00")
            return current if tz is None else current.replace(tzinfo=tz)

    monkeypatch.setattr(service, "datetime", FixedDatetime)
    db_path = prepare_web_db(tmp_path)
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_runs(job_key, scheduled_at, started_at, finished_at, status, error)
            VALUES (
                'news_hourly_incremental', '2026-05-25T08:05:00',
                '2026-05-25 08:05:01', '2026-05-25 08:05:02',
                'failed', 'provider down'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO scheduler_runs(job_key, scheduled_at, started_at, finished_at, status, deferred_reason)
            VALUES (
                'market_context_intraday', '2026-05-25T10:00:00',
                '2026-05-25 10:00:01', '2026-05-25 10:00:02',
                'deferred', 'provider hourly budget exhausted for akshare'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO task_logs(task_name, run_date, status, message, error)
            VALUES ('scheduler_job', '2026-05-25', 'failed', 'Running scheduler job news_hourly_incremental', 'provider down')
            """
        )

    settings = render_route(db_path, "/settings", {})

    assert "今日任务" in settings
    assert "news_hourly_incremental" in settings
    assert "market_context_intraday" in settings
    assert "failed" in settings
    assert "deferred" in settings
    assert "missed" in settings
    assert "provider down" in settings
    assert "provider hourly budget exhausted for akshare" in settings
    assert "未跑" in settings


def test_timeline_shows_latest_three_advice_dates_and_missing_states(tmp_path):
    db_path = prepare_web_db(tmp_path)
    generate_daily_advice(db_path, advice_date="20260524")
    generate_daily_advice(db_path, advice_date="20260525")

    html = render_route(db_path, "/timeline", {})
    dashboard = render_route(db_path, "/", {})

    assert "2026-05-25" in html
    assert "2026-05-24" in html
    assert "2026-05-23" in html
    assert html.index("2026-05-25") < html.index("2026-05-24") < html.index("2026-05-23")
    assert "市场快照" in html
    assert "运行 market snapshot" in html
    assert "运行 forecast run" in html
    assert "运行 backtest run" in html
    assert "查看完整研究时间线" in dashboard


def test_category_navigation_groups_assets_and_data_page_prioritizes_summary(tmp_path):
    db_path = prepare_web_db(tmp_path)

    categories = render_route(db_path, "/categories", {"category": ["fixed_income_cash"]})
    dashboard = render_route(db_path, "/", {})
    data = render_route(db_path, "/data", {})
    themes = render_route(db_path, "/themes", {"theme": ["technology"]})

    assert "产品分类" in categories
    assert "固收/现金代理 摘要" in categories
    assert "国债ETF" in categories
    assert 'href="/data?asset_id=' in categories
    assert 'href="/opportunities?type=fixed_income_cash"' in dashboard or 'href="/opportunities"' in dashboard
    assert "资产概览" in data
    assert "当前分类" in data
    assert "完整资产表" in data
    assert data.index("资产概览") < data.index("技术明细")
    assert "主题配置" in themes
    assert "科技 代表标的" in themes
    assert "科技成长股票" in themes
    assert "名称/类型包含" in themes


def test_fund_screening_filters_and_presets(tmp_path):
    db_path = prepare_web_db(tmp_path)

    filtered = render_route(
        db_path,
        "/funds",
        {
            "fund_type": ["混合型"],
            "manager": ["张"],
            "min_scale": ["20"],
            "has_fee": ["1"],
        },
    )
    conservative = render_route(db_path, "/funds", {"preset": ["conservative"]})
    technology = render_route(db_path, "/funds", {"theme": ["technology"]})
    missing_meta = render_route(db_path, "/funds", {"manager": ["不存在"]})
    all_funds = render_route(db_path, "/funds", {})

    assert "当前条件命中 1" in filtered
    assert "华夏成长混合" in filtered
    assert "科技成长股票" not in filtered
    assert "20日收益样本不足" in filtered
    assert "保守预设" in conservative
    assert "匹配保守预设" in conservative
    assert "当前条件命中 1" in technology
    assert "科技成长股票" in technology
    assert "华夏成长混合" not in technology
    assert "没有基金满足当前筛选" in missing_meta
    assert "基金类型待补充" in all_funds
    assert "费率待补充" in all_funds


def test_experts_page_empty_active_and_retired_states(tmp_path):
    db_path = tmp_path / "experts-web.sqlite3"
    init_db(db_path)

    empty_html = render_route(db_path, "/experts", {})
    assert "还没有专家记录" in empty_html

    seed_expert_web_state(db_path, include_retired=True)
    html = render_route(db_path, "/experts", {})

    assert "专家委员会" in html
    assert "活跃专家" in html
    assert "管仲" in html
    assert "资产" in html
    assert "专家总览" in html
    assert "专家收益对比" in html
    assert "权益曲线与基准" not in html
    assert "总览投资 / 收益曲线" not in html
    overview_curve_html = html.split("<h2>专家收益对比</h2>", 1)[1].split("<h2>复盘与经验</h2>", 1)[0]
    assert "<table" not in overview_curve_html
    assert "<svg" not in overview_curve_html
    assert 'data-echarts="expert-comparison"' in overview_curve_html
    assert '"returnValue":' in overview_curve_html
    assert "benchmark_excess" not in overview_curve_html
    assert "benchmark_return" not in overview_curve_html
    assert "<table" not in html
    assert 'href="/experts?expert=' in html
    assert "查看详情" in html
    assert "最新计划与执行" not in html
    assert "评分" in html
    assert "已清退" in html
    assert "失败经验" in html
    assert "原始评分记录" not in html
    assert "原始复盘记录" not in html

    detail_html = render_route(db_path, "/experts", {"expert": ["guan_zhong"]})
    assert "管仲详情" in detail_html
    assert "返回专家总览" in detail_html
    assert "专家档案" in detail_html
    assert "完整时间系" in detail_html
    assert "投资计划与执行" in detail_html
    assert "投资计划" in detail_html
    assert "当前投资" in detail_html
    assert "收益曲线" in detail_html
    assert "收益与资产序列" not in detail_html
    return_curve_html = detail_html.split("<h2>收益曲线</h2>", 1)[1].split("<h2>分析与反思</h2>", 1)[0]
    assert "<table" not in return_curve_html
    assert "valuation_date" not in return_curve_html
    assert 'data-echarts="expert-return"' in return_curve_html
    assert '"totalValue":' in return_curve_html
    assert "分析与反思" in detail_html
    assert "reason" in detail_html
    assert "reflection" in detail_html
    assert "总资产" in detail_html
    assert "已投资" in detail_html
    assert "最新计划与执行" not in detail_html


def test_expert_return_curve_keeps_points_inside_plot_area():
    html = expert_return_curve(
        [
            {"valuation_date": "2026-05-23", "cash": 500000, "positions_value": 0, "total_value": 500000},
            {"valuation_date": "2026-05-24", "cash": 500000, "positions_value": 0, "total_value": 500000},
            {"valuation_date": "2026-05-25", "cash": 450000, "positions_value": 53048.15, "total_value": 503048.15},
            {"valuation_date": "2026-05-26", "cash": 445000, "positions_value": 59172.4, "total_value": 504172.4},
            {"valuation_date": "2026-05-27", "cash": 445000, "positions_value": 59172.4, "total_value": 504172.4},
        ],
        500000,
    )

    assert "<svg" not in html
    assert 'data-echarts="expert-return"' in html
    assert html.count('"totalValue":') == 5
    assert '"cashValue":445000.0' in html
    assert '"positionsValue":59172.4' in html
    assert '"returnLabel":"+0.83%"' in html
    assert "+0.83%" in html
    chart_json = html.split('<script type="application/json" class="echarts-data">', 1)[1].split("</script>", 1)[0]
    assert "&lt;span" not in chart_json
    assert '<span class="market' not in chart_json
    assert "05-23" in html
    assert "05-27" in html


def test_portfolios_page_shows_holdings_transactions_and_equity_curve(tmp_path):
    db_path = prepare_web_db(tmp_path)
    with connect(db_path) as conn:
        asset = conn.execute("SELECT id FROM assets WHERE code = '510300'").fetchone()
        portfolio_id = create_virtual_portfolio(
            conn,
            owner_type="user",
            owner_id=1,
            name="用户研究组合",
            initial_capital=100_000,
        )
        record_virtual_order(
            conn,
            portfolio_id=portfolio_id,
            trade_date="2026-01-07",
            side="buy",
            asset_id=asset["id"],
            quantity=10,
            fee=1,
            reason="验证组合页面。",
        )
        value_virtual_portfolio(conn, portfolio_id=portfolio_id, valuation_date="2026-01-07")

    html = render_route(db_path, "/portfolios", {})

    assert "模拟组合" in html
    assert "组合概览" in html
    assert "权益曲线" in html
    assert "当前持仓" in html
    assert "交易与估值记录" in html
    assert "用户研究组合" in html
    assert "510300" in html
    assert "交易记录" in html
    assert "估值记录" in html


def test_communication_page_can_record_dry_run_without_exposing_raw_recipient(tmp_path):
    db_path = prepare_web_db(tmp_path)
    seed_communication_web_state(db_path)

    html = render_route(db_path, "/communication", {"dry_run_test": ["1"], "recipient_key": ["owner_phone"]})

    with connect(db_path) as conn:
        message = conn.execute("SELECT * FROM outbound_messages WHERE template_key = 'webui_dry_run_test'").fetchone()

    assert "已记录干跑测试" in html
    assert "dry_run" in html
    assert message["status"] == "dry_run"
    assert "不会触发真实手机发送" in html
    assert "+13***5678" in html
    assert "+13800135678" not in html


def test_communication_page_surfaces_terminal_statuses_and_recent_errors(tmp_path):
    db_path = prepare_web_db(tmp_path)
    seed_communication_web_state(db_path)

    with connect(db_path) as conn:
        recipient = conn.execute("SELECT * FROM communication_recipients WHERE recipient_key = 'owner_phone'").fetchone()
        raw_address = recipient["address"]
        rows = [
            ("jarvis_daily_summary", "sent", None, "2026-05-24 08:10:00", "2026-05-24 08:10:10"),
            ("daily_workflow_failure", "failed", "Messages send failed", "2026-05-24 08:11:00", None),
            (
                "provider_warning",
                "permission_required",
                "Messages permission missing",
                "2026-05-24 08:12:00",
                None,
            ),
        ]
        for template_key, status, error, requested_at, sent_at in rows:
            conn.execute(
                """
                INSERT INTO outbound_messages(
                    channel, recipient_id, recipient_key, template_key, subject, body,
                    severity, payload_summary, idempotency_key, status,
                    adapter_result_json, error, requested_at, sent_at
                )
                VALUES (
                    'imessage', ?, 'owner_phone', ?, 'TASK-098 communication state',
                    '通信链路状态验证，仅供研究辅助。', 'warning', ?,
                    ?, ?, '{"status":"test"}', ?, ?, ?
                )
                """,
                (
                    recipient["id"],
                    template_key,
                    f"{template_key} {status}",
                    f"web-fixture-{template_key}-{status}",
                    status,
                    error,
                    requested_at,
                    sent_at,
                ),
            )

    html = render_route(db_path, "/communication", {})

    assert "近期有失败" in html
    assert "最近错误数" in html
    assert "dry_run" in html
    assert "sent" in html
    assert "failed" in html
    assert "permission_required" in html
    assert "Messages send failed" in html
    assert "Messages permission missing" in html
    assert "2026-05-24 08:10:10" in html
    assert "+13***5678" in html
    assert raw_address not in html


def test_settings_page_saves_active_preference_and_advice_uses_it(tmp_path):
    db_path = prepare_web_db(tmp_path)

    html = render_route(
        db_path,
        "/settings",
        {
            "save": ["1"],
            "profile_name": ["稳健账户"],
            "risk_profile": ["conservative"],
            "investment_horizon_days": ["60"],
            "max_equity_pct": ["0.30"],
            "min_cash_pct": ["0.25"],
            "notes": ["低波动优先"],
        },
    )
    generate_daily_advice(db_path, advice_date="20260524")

    with connect(db_path) as conn:
        advice = conn.execute("SELECT * FROM daily_advice WHERE advice_date = '2026-05-24'").fetchone()

    assert "已保存风险设置" in html
    assert "稳健账户" in html
    assert "权益上限 30%" in advice["assumptions"]
    assert "稳健账户" in advice["market_summary"]


def seed_expert_web_state(db_path, include_retired: bool = False) -> None:
    initialize_default_experts(db_path)
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        experts = conn.execute("SELECT * FROM experts ORDER BY expert_key").fetchall()
        for index, expert in enumerate(experts):
            portfolio = conn.execute(
                "SELECT * FROM virtual_portfolios WHERE owner_type = 'expert' AND owner_id = ?",
                (expert["id"],),
            ).fetchone()
            total_value = 500_000 + index * 12_000
            conn.execute(
                """
                INSERT INTO virtual_valuations(
                    portfolio_id, valuation_date, cash, positions_value,
                    total_value, missing_prices_json, details_json
                )
                VALUES (?, '2026-05-23', ?, ?, ?, '[]', '{}')
                """,
                (portfolio["id"], 180_000, total_value - 180_000, total_value),
            )

            conn.execute(
                """
                INSERT INTO expert_plans(
                    expert_id, portfolio_id, plan_date, action, target_asset_id,
                    target_weight, target_amount, rationale, evidence_json,
                    risk_checks_json, risk_warnings, execution_status
                )
                VALUES (?, ?, '2026-05-23', 'no_trade', NULL, 0, 0, ?, ?, '{}', ?, 'no_trade')
                """,
                (
                    expert["id"],
                    portfolio["id"],
                    f"{expert['name']}选择保持观察。",
                    '{"prediction_id": 1, "asset": {"id": 1}}',
                    "仅用于虚拟研究组合模拟。",
                ),
            )
            conn.execute(
                """
                INSERT INTO expert_scorecards(
                    expert_id, portfolio_id, score_date, window_days,
                    valuation_count, mature_enough, portfolio_return,
                    benchmark_return, benchmark_excess, max_drawdown,
                    volatility, cash_drag, turnover, win_rate,
                    evidence_completeness, mandate_adherence, overall_score,
                    details_json
                )
                VALUES (?, ?, '2026-05-23', 20, 3, 1, ?, 0.01, ?, -0.02, 0.01, 0.36, 0.03, 0.6, 1.0, 0.9, ?, '{}')
                """,
                (expert["id"], portfolio["id"], index * 0.02, index * 0.02 - 0.01, 78 - index),
            )
            conn.execute(
                """
                INSERT INTO expert_reviews(
                    expert_id, scorecard_id, review_date, decision,
                    previous_lifecycle_state, new_lifecycle_state, rationale,
                    evidence_json
                )
                VALUES (?, NULL, '2026-05-23', 'keep', 'active', 'active', ?, '{}')
                """,
                (expert["id"], f"{expert['name']}维持观察。"),
            )
        if include_retired:
            retired = dict(experts[0])
            upsert_expert(
                conn,
                {
                    **retired,
                    "expert_key": "retired_test_expert",
                    "name": "失败经验专家",
                    "lifecycle_state": "retired",
                },
            )
            retired_id = conn.execute("SELECT id FROM experts WHERE expert_key = 'retired_test_expert'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO expert_lessons(
                    expert_id, review_id, lesson_date, lesson_type, summary,
                    overweighted_signals, ignored_signals, failed_controls,
                    avoid_hiring_patterns
                )
                VALUES (?, NULL, '2026-05-23', 'failure', '失败经验：过度追逐单一信号。',
                        'momentum', 'drawdown', 'cash control', '避免招聘复制单一动量风格。')
                """,
                (retired_id,),
            )


def seed_communication_web_state(db_path) -> None:
    with connect(db_path) as conn:
        upsert_communication_adapter_config(
            conn,
            {
                "channel": "imessage",
                "enabled": 1,
                "dry_run_default": 1,
                "setup_status": "verified",
                "last_verified_at": "2026-05-23 08:00:00",
            },
        )
        upsert_communication_recipient(
            conn,
            {
                "recipient_key": "owner_phone",
                "display_name": "Owner",
                "channel": "imessage",
                "address": "+13800135678",
                "allowlisted": 1,
                "enabled": 1,
                "rate_limit_per_hour": 10,
            },
        )
        conn.execute(
            """
            INSERT INTO outbound_messages(
                channel, recipient_key, template_key, subject, body,
                severity, payload_summary, idempotency_key, status,
                adapter_result_json
            )
            VALUES (
                'imessage', 'owner_phone', 'daily_workflow_success',
                'Daily research ready', '研究摘要，仅供研究辅助。',
                'info', 'daily success', 'web-fixture-message',
                'dry_run', '{"status":"dry_run","details":{}}'
            )
            """
        )


class _FakeNewsProvider:
    source = "fake"

    def news(self, *, source: str, start_datetime: str, end_datetime: str):
        return [
            {
                "id": "fake-web-news-1",
                "title": "系统调度测试新闻",
                "content": "系统调度测试新闻，市场情绪回暖。",
                "published_at": end_datetime,
                "url": "https://example.test/news/1",
            }
        ]
