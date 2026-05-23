from __future__ import annotations

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.db import connect, init_db, upsert_asset, upsert_expert, upsert_fund_info, upsert_price_daily
from investment_forecasting.experts.roster import initialize_default_experts
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot
from investment_forecasting.web.app import render_route
from tests.test_daily_workflow import seed_asset_with_prices


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
    seed_typed_asset(db_path, "600519", "贵州茅台", "stock", [1500, 1510, 1520, 1505, 1530, 1540, 1550])
    calculate_features_for_db(db_path)
    calculate_market_snapshot(db_path, snapshot_date="20260523")
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)
    generate_daily_advice(db_path, advice_date="20260523")
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

    assert "总览" in html
    assert "数据状态" in html
    assert "当前数据库" in html
    assert "没有资产或行情数据" in html
    assert "暂无建议" in html
    assert "暂无日志" in html


def test_workbench_pages_render_with_data(tmp_path):
    db_path = prepare_web_db(tmp_path)

    seed_expert_web_state(db_path)
    pages = ["/", "/timeline", "/categories", "/data", "/funds", "/predictions", "/backtests", "/advice", "/experts", "/settings", "/logs"]
    rendered = {page: render_route(db_path, page, {}) for page in pages}

    assert "市场状态" in rendered["/"]
    assert "研究时间线" in rendered["/"]
    assert "数据状态" in rendered["/"]
    assert "当前数据库" in rendered["/"]
    assert "近期优先关注" in rendered["/"]
    assert "产品分类" in rendered["/categories"]
    assert "固收/现金代理" in rendered["/categories"]
    assert "筛选条件" in rendered["/funds"]
    assert "筛选结果" in rendered["/funds"]
    assert "涨幅曲线" in rendered["/data"]
    assert "资产概览" in rendered["/data"]
    assert "技术明细" in rendered["/data"]
    assert "行情 / 净值历史" in rendered["/data"]
    assert "模型预测" in rendered["/predictions"]
    assert "回测任务" in rendered["/backtests"]
    assert "每日建议" in rendered["/advice"]
    assert "专家委员会" in rendered["/experts"]
    assert "最新计划与执行" in rendered["/experts"]
    assert "权益曲线与基准" in rendered["/experts"]
    assert "技术明细" in rendered["/experts"]
    assert "连续研究记录" in rendered["/timeline"]
    assert "每日建议" in rendered["/timeline"]
    assert "模型预测" in rendered["/timeline"]
    assert "回测评分" in rendered["/timeline"]
    assert "任务健康" in rendered["/timeline"]
    assert 'href="/advice?advice_id=' in rendered["/timeline"]
    assert 'href="/predictions"' in rendered["/timeline"]
    assert "缺失" in rendered["/timeline"]
    assert "风险设置" in rendered["/settings"]
    assert "任务日志" in rendered["/logs"]
    for html in rendered.values():
        assert "<!doctype html>" in html
        assert "投资预测工作台" in html
        assert "viewport" in html


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

    assert "产品分类" in categories
    assert "固收/现金代理 摘要" in categories
    assert "国债ETF" in categories
    assert 'href="/data?asset_id=' in categories
    assert 'href="/categories?category=fixed_income_cash"' in dashboard
    assert "资产概览" in data
    assert "当前分类" in data
    assert "完整资产表" in data
    assert data.index("资产概览") < data.index("技术明细")


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
    missing_meta = render_route(db_path, "/funds", {"manager": ["不存在"]})
    all_funds = render_route(db_path, "/funds", {})

    assert "当前条件命中 1" in filtered
    assert "华夏成长混合" in filtered
    assert "科技成长股票" not in filtered
    assert "20日收益样本不足" in filtered
    assert "保守预设" in conservative
    assert "匹配保守预设" in conservative
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
    assert "稳健防守专家" in html
    assert "当前资产" in html
    assert "最新计划与执行" in html
    assert "权益曲线与基准" in html
    assert "综合评分" in html
    assert "已清退" in html
    assert "失败经验" in html
    assert "原始评分记录" in html
    assert "原始复盘记录" in html


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
