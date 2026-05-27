from __future__ import annotations

import argparse
import html
import json
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from investment_forecasting.communication.imessage import system_preflight
from investment_forecasting.communication.service import CommunicationError, send_outbound_message
from investment_forecasting.data.classification import classify_asset_theme, theme_options
from investment_forecasting.db import active_user_preference, connect, init_db, latest_capital_flow_observations, latest_fund_holdings, list_user_preferences, upsert_user_preference
from investment_forecasting.experts.roster import OBSOLETE_STYLE_NAMED_EXPERT_SOURCE
from investment_forecasting.scheduler import scheduler_status


NAV_ITEMS = [
    ("/", "今日简报"),
    ("/opportunities", "机会池"),
    ("/experts", "专家团"),
    ("/evidence", "证据"),
    ("/settings", "设置"),
]


def run_web_server(db_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    init_db(db_path)
    handler = make_handler(Path(db_path))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Investment Forecasting WebUI: http://{host}:{port}")
    server.serve_forever()


def make_handler(db_path: Path) -> type[BaseHTTPRequestHandler]:
    class WorkbenchHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._send_route(include_body=True)

        def do_HEAD(self) -> None:
            self._send_route(include_body=False)

        def _send_route(self, include_body: bool) -> None:
            parsed = urlparse(self.path)
            try:
                body = render_route(db_path, parsed.path, parse_qs(parsed.query))
                self.send_response(200)
            except KeyError:
                body = render_page("Not Found", "<section><h1>Not Found</h1><p>The requested workbench page does not exist.</p></section>", parsed.path)
                self.send_response(404)
            except Exception as exc:
                body = render_page("Error", f"<section><h1>Error</h1><p>{escape(str(exc))}</p></section>", parsed.path)
                self.send_response(500)
            encoded = body.encode("utf-8")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if include_body:
                self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return WorkbenchHandler


def render_route(db_path: Path, path: str, query: dict[str, list[str]]) -> str:
    routes = {
        "/": render_dashboard,
        "/jarvis": render_jarvis,
        "/opportunities": render_opportunities,
        "/timeline": render_timeline,
        "/market": render_market,
        "/categories": render_categories,
        "/themes": render_themes,
        "/data": render_data,
        "/funds": render_funds,
        "/predictions": render_predictions,
        "/backtests": render_backtests,
        "/advice": render_advice,
        "/portfolios": render_portfolios,
        "/experts": render_experts,
        "/evidence": render_evidence,
        "/communication": render_communication,
        "/settings": render_settings,
        "/logs": render_logs,
    }
    if path not in routes:
        raise KeyError(path)
    return routes[path](db_path, query)


def render_dashboard(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        latest_jarvis = conn.execute("SELECT * FROM jarvis_daily_briefs ORDER BY brief_date DESC, id DESC LIMIT 1").fetchone()
        latest_advice = conn.execute("SELECT * FROM daily_advice ORDER BY advice_date DESC, id DESC LIMIT 1").fetchone()
        environment = conn.execute("SELECT * FROM market_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1").fetchone()
        preference = active_user_preference(conn)
        data_status = database_status(conn, db_path)
        prediction_summary = conn.execute(
            """
            SELECT MAX(prediction_date) AS prediction_date, COUNT(*) AS count,
                   AVG(expected_return) AS avg_expected_return,
                   AVG(downside_risk) AS avg_downside_risk,
                   AVG(confidence) AS avg_confidence
            FROM model_predictions
            """
        ).fetchone()
        recommendations = latest_recommendations(conn, limit=8)
        timeline_rows = build_timeline_rows(conn, limit=3)
        run_health = dashboard_run_health(conn, data_status)
    body = today_brief_page(latest_jarvis, latest_advice, environment, prediction_summary, preference, run_health, data_status, recommendations, timeline_rows)
    return render_page("今日简报", body, "/")


def render_timeline(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        rows = build_timeline_rows(conn, limit=12)
    body = timeline_panel(rows)
    return render_page("研究时间线", section("连续研究记录", body), "/timeline")


def render_jarvis(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        history = conn.execute(
            """
            SELECT id, brief_date, version, one_line_stance, source, updated_at
            FROM jarvis_daily_briefs
            ORDER BY brief_date DESC, id DESC
            LIMIT 120
            """
        ).fetchall()
        selected_id = int(_first_query_value(query, "brief_id", history[0]["id"] if history else 0) or 0)
        rows = conn.execute(
            """
            SELECT *
            FROM jarvis_daily_briefs
            WHERE id = COALESCE(NULLIF(?, 0), id)
            ORDER BY brief_date DESC, id DESC
            LIMIT 1
            """,
            (selected_id,),
        ).fetchall()
    body = jarvis_selector(history, selected_id)
    body += "".join(jarvis_brief_view(row) for row in rows) if rows else empty("还没有 Jarvis 简报；运行 `investment-forecasting jarvis generate` 后会显示。")
    body += section("历史 Jarvis 简报", jarvis_history_table(history))
    return render_page("Jarvis", body, "/jarvis")


def render_opportunities(db_path: Path, query: dict[str, list[str]]) -> str:
    selected_type = str(_first_query_value(query, "type", "all") or "all")
    risk = str(_first_query_value(query, "risk", "active") or "active")
    valid_types = {"all", "fund", "etf", "stock", "index", "fixed_income_cash"}
    if selected_type not in valid_types:
        selected_type = "all"
    with connect(db_path) as conn:
        active_preference = active_user_preference(conn)
        categories = build_category_summaries(conn)
        theme_rows = theme_asset_rows(conn)
        prediction_rows = opportunity_prediction_rows(conn, selected_type)
        funds = opportunity_fund_rows(conn, selected_type)
        holdings = latest_fund_holdings(conn, limit=60)
    preference_label = active_preference["profile_name"] if active_preference else "默认风险画像"
    body = section("机会池筛选", opportunity_filter_panel(selected_type, risk, preference_label))
    body += section("产品与资产入口", opportunity_category_panel(categories, selected_type))
    body += section("主题机会", theme_overview_panel(build_theme_summaries(theme_rows), None))
    body += section("资产级预测", asset_prediction_cards(prediction_rows))
    if selected_type in {"all", "fund"}:
        preset = risk if risk in {"conservative", "balanced", "aggressive"} else ""
        filtered_funds = filter_funds(funds, {"preset": preset})
        body += section("基金候选", fund_results_panel(filtered_funds, funds, {"preset": preset}))
        body += section("持仓穿透", fund_holdings_panel(holdings, fund_ids={int(row["id"]) for row in filtered_funds[:30]}))
    body += section(
        "技术明细",
        collapsible(
            "旧页面与原始入口",
            """
            <div class="link-grid">
              <a href="/categories">产品分类</a>
              <a href="/themes">主题配置</a>
              <a href="/funds">基金筛选</a>
              <a href="/data">数据与曲线</a>
              <a href="/predictions">预测</a>
            </div>
            """,
        ),
    )
    return render_page("机会池", body, "/opportunities")


def render_market(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        snapshots = conn.execute(
            """
            SELECT *
            FROM market_snapshots
            ORDER BY snapshot_date DESC, id DESC
            LIMIT 30
            """
        ).fetchall()
        macro_latest = conn.execute(
            """
            SELECT m.series_id, m.observation_date, m.value, m.source
            FROM macro_observations m
            JOIN (
                SELECT series_id, MAX(observation_date) AS observation_date
                FROM macro_observations
                GROUP BY series_id
            ) latest
              ON latest.series_id = m.series_id
             AND latest.observation_date = m.observation_date
            ORDER BY m.series_id
            """
        ).fetchall()
        macro_history = conn.execute(
            """
            SELECT series_id, observation_date, value, source
            FROM macro_observations
            ORDER BY observation_date DESC, series_id
            LIMIT 200
            """
        ).fetchall()
        capital_flows = latest_capital_flow_observations(conn, limit=40)
        capital_flow_history = conn.execute(
            """
            SELECT flow_date, scope, subject_code, subject_name, main_net_inflow,
                   main_net_inflow_pct, super_large_net_inflow, large_net_inflow,
                   medium_net_inflow, small_net_inflow, source
            FROM capital_flow_observations
            ORDER BY flow_date DESC, id DESC
            LIMIT 200
            """
        ).fetchall()
    latest_snapshot = snapshots[0] if snapshots else None
    body = section("市场快照", market_snapshot_panel(latest_snapshot))
    body += section("资金流观测", capital_flow_panel(capital_flows))
    body += section("宏观观测", macro_latest_panel(macro_latest))
    body += section("历史记录", market_history_panel(snapshots, macro_history, capital_flow_history))
    return render_page("市场指标", body, "/market")


def render_categories(db_path: Path, query: dict[str, list[str]]) -> str:
    selected_category = str(_first_query_value(query, "category", "") or "")
    with connect(db_path) as conn:
        summaries = build_category_summaries(conn)
        if selected_category and selected_category not in {item["key"] for item in summaries}:
            selected_category = ""
        selected = next((item for item in summaries if item["key"] == selected_category), summaries[0] if summaries else None)
        assets = category_assets(conn, selected["key"], limit=120) if selected else []
    body = category_nav_panel(summaries)
    if selected:
        body += section(f"{selected['label']} 摘要", category_summary_panel(selected))
        body += section(f"{selected['label']} 标的", category_asset_table(selected, assets))
    else:
        body += empty("还没有可分类的资产；请先采集资产、行情和特征数据。")
    return render_page("产品分类", body, "/categories")


def render_themes(db_path: Path, query: dict[str, list[str]]) -> str:
    selected_theme = str(_first_query_value(query, "theme", "") or "")
    with connect(db_path) as conn:
        rows = theme_asset_rows(conn)
    summaries = build_theme_summaries(rows)
    if selected_theme and selected_theme not in {item["theme_key"] for item in summaries}:
        selected_theme = ""
    selected = next((item for item in summaries if item["theme_key"] == selected_theme), summaries[0] if summaries else None)
    body = section("主题总览", theme_overview_panel(summaries, selected))
    if selected:
        theme_rows = [row for row in rows if row["theme_key"] == selected["theme_key"]]
        body += section(f"{selected['theme_label']} 代表标的", theme_asset_table(theme_rows))
    else:
        body += section("主题明细", empty("还没有可聚合的主题资产；请先采集资产、行情和特征数据。"))
    return render_page("主题配置", body, "/themes")


def render_data(db_path: Path, query: dict[str, list[str]]) -> str:
    table_tab = str(_first_query_value(query, "table_tab", "history") or "history")
    if table_tab not in {"history", "features"}:
        table_tab = "history"
    with connect(db_path) as conn:
        assets = conn.execute("SELECT * FROM assets ORDER BY asset_type, code").fetchall()
        selected_id = int(query.get("asset_id", [assets[0]["id"] if assets else 0])[0] or 0)
        date_bounds = conn.execute(
            "SELECT MIN(trade_date) AS start_date, MAX(trade_date) AS end_date FROM price_daily WHERE asset_id = ?",
            (selected_id,),
        ).fetchone()
        date_window = data_curve_window(query, date_bounds)
        selected_asset = conn.execute(
            """
            SELECT a.*, f.feature_date, f.return_20d, f.max_drawdown_60d,
                   f.sharpe_60d, f.market_state
            FROM assets a
            LEFT JOIN features_daily f ON f.id = (
                SELECT id FROM features_daily
                WHERE asset_id = a.id
                ORDER BY feature_date DESC
                LIMIT 1
            )
            WHERE a.id = ?
            """,
            (selected_id,),
        ).fetchone()
        selected_prediction = conn.execute(
            """
            SELECT prediction_date, horizon_days, expected_return, up_probability,
                   downside_risk, confidence
            FROM model_predictions
            WHERE asset_id = ?
            ORDER BY prediction_date DESC, horizon_days
            LIMIT 1
            """,
            (selected_id,),
        ).fetchone()
        history = conn.execute(
            """
            SELECT trade_date, close, adjusted_close, nav, volume, amount, pct_change, source
            FROM price_daily
            WHERE asset_id = ?
              AND (? IS NULL OR trade_date >= ?)
              AND (? IS NULL OR trade_date <= ?)
            ORDER BY trade_date DESC
            """,
            (selected_id, date_window["start"], date_window["start"], date_window["end"], date_window["end"]),
        ).fetchall()
        category = asset_category(selected_asset) if selected_asset else PRODUCT_CATEGORIES["unknown"]
        peers = category_assets(conn, category["key"], limit=8) if selected_asset else []
        features = conn.execute(
            """
            SELECT feature_date, return_1d, return_20d, volatility_20d,
                   max_drawdown_60d, sharpe_60d, calmar_60d, win_rate_60d,
                   market_state, source
            FROM features_daily
            WHERE asset_id = ?
            ORDER BY feature_date DESC
            LIMIT 60
            """,
            (selected_id,),
        ).fetchall()
    selector = asset_selector(
        assets,
        selected_id,
        "/data",
        hidden={
            "table_tab": table_tab,
            "range": _first_query_value(query, "range"),
            "start_date": _first_query_value(query, "start_date"),
            "end_date": _first_query_value(query, "end_date"),
        },
    )
    chart_rows = list(reversed(history))
    tab_content = data_table_tab_panels(
        history,
        features,
        active_tab=table_tab,
    )
    body = section("资产概览", selector + selected_asset_summary(selected_asset, selected_prediction, category) + category_context_panel(category, peers))
    body += section("涨幅曲线", return_curve(chart_rows, asset_id=selected_id, date_window=date_window))
    body += section("行情与量化指标", data_table_tabs(query, selected_id, table_tab) + tab_content)
    body += section("技术明细", collapsible("完整资产表", table(assets, ["id", "code", "name", "asset_type", "market", "status", "source"])))
    return render_page("数据与曲线", body, "/data")


def render_funds(db_path: Path, query: dict[str, list[str]]) -> str:
    filters = fund_filters_from_query(query)
    with connect(db_path) as conn:
        active_preference = active_user_preference(conn)
        funds = conn.execute(
            """
            SELECT a.id, a.code, a.name, f.feature_date, f.return_20d,
                   f.max_drawdown_60d, f.sharpe_60d, f.win_rate_60d, f.market_state,
                   i.fund_type, i.manager, i.scale, i.purchase_fee,
                   i.management_fee, i.custody_fee, i.fund_company
            FROM assets a
            LEFT JOIN fund_info i ON i.asset_id = a.id
            LEFT JOIN features_daily f ON f.id = (
                SELECT id FROM features_daily
                WHERE asset_id = a.id
                ORDER BY feature_date DESC
                LIMIT 1
            )
            WHERE a.asset_type = 'fund'
            ORDER BY f.return_20d DESC NULLS LAST, a.code
            """
        ).fetchall()
        holdings = latest_fund_holdings(conn, limit=80)
    filtered = filter_funds(funds, filters)
    body = fund_filter_panel(filters, funds, active_preference)
    body += section("筛选结果", fund_results_panel(filtered, funds, filters))
    body += section("基金持仓观测", fund_holdings_panel(holdings, fund_ids={int(row["id"]) for row in filtered}))
    body += section("技术明细", collapsible("原始基金字段", table(fund_display_rows(filtered), ["code", "name", "theme", "fund_type", "manager", "scale", "purchase_fee", "feature_date", "return_20d", "max_drawdown_60d", "sharpe_60d", "win_rate_60d", "market_state", "explanation"], escape_cells=False)))
    return render_page("基金筛选", body, "/funds")


def render_predictions(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.asset_id, a.code, a.name, a.asset_type, p.prediction_date, p.horizon_days,
                   p.up_probability, p.expected_return, p.expected_return_low,
                   p.expected_return_high, p.downside_risk, p.confidence,
                   p.model_version, p.input_window_start, p.input_window_end,
                   r.rank_score, r.rank_position, r.rank_count,
                   r.same_category_rank, r.same_category_count,
                   r.risk_adjusted_score, r.validation_status, r.degraded_reason
            FROM model_predictions p
            LEFT JOIN assets a ON a.id = p.asset_id
            LEFT JOIN model_prediction_reliability r ON r.prediction_id = p.id
            ORDER BY p.prediction_date DESC, a.code, p.horizon_days
            LIMIT 300
            """
        ).fetchall()
    cards = asset_prediction_cards(rows)
    body = section("资产级预测卡片", cards)
    body += section(
        "技术明细",
        collapsible("原始模型预测", table(rows, ["id", "code", "name", "prediction_date", "horizon_days", "up_probability", "expected_return", "expected_return_low", "expected_return_high", "downside_risk", "confidence", "rank_score", "same_category_rank", "risk_adjusted_score", "validation_status", "degraded_reason", "model_version", "input_window_start", "input_window_end"])),
    )
    return render_page("预测", body, "/predictions")


def render_backtests(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        monitoring = conn.execute(
            """
            SELECT *
            FROM model_monitoring_reports
            WHERE report_date = (SELECT MAX(report_date) FROM model_monitoring_reports)
            ORDER BY CASE status WHEN 'degraded' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, model_version
            """
        ).fetchall()
        runs = conn.execute("SELECT * FROM backtest_runs ORDER BY created_at DESC, id DESC LIMIT 80").fetchall()
        results = conn.execute(
            """
            SELECT r.id, r.run_id, a.code, r.prediction_date, r.horizon_days,
                   r.predicted_return, r.actual_return, r.predicted_direction,
                   r.actual_direction, r.prediction_score, r.risk_score,
                   r.advice_score, r.overall_score
            FROM backtest_results r
            LEFT JOIN assets a ON a.id = r.asset_id
            ORDER BY r.prediction_date DESC, r.id DESC
            LIMIT 200
            """
        ).fetchall()
    run_rows = [decode_metrics(row) for row in runs]
    body = section("模型健康", model_monitoring_panel(monitoring) + backtest_health_panel(run_rows, results))
    body += section("分周期评分", backtest_horizon_cards(run_rows))
    body += section(
        "技术明细",
        collapsible("回测任务原始字段", table(run_rows, ["id", "model_version", "asset_scope", "start_date", "end_date", "horizon_days", "count", "validation_status", "information_coefficient", "rank_ic", "bucket_spread", "direction_accuracy", "mean_return_error", "risk_hit_rate", "mean_benchmark_excess", "mean_drawdown_control", "mean_overall_score"]))
        + collapsible("历史预测评分原始行", table(results, ["id", "run_id", "code", "prediction_date", "horizon_days", "predicted_return", "actual_return", "predicted_direction", "actual_direction", "prediction_score", "risk_score", "advice_score", "overall_score"])),
    )
    return render_page("回测评分", body, "/backtests")


def render_advice(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        history = conn.execute(
            """
            SELECT id, advice_date, risk_level, model_version, overall_score
            FROM daily_advice
            ORDER BY advice_date DESC, id DESC
            LIMIT 120
            """
        ).fetchall()
        selected_id = int(_first_query_value(query, "advice_id", history[0]["id"] if history else 0) or 0)
        rows = conn.execute(
            """
            SELECT *
            FROM daily_advice
            WHERE id = COALESCE(NULLIF(?, 0), id)
            ORDER BY advice_date DESC, id DESC
            LIMIT 1
            """,
            (selected_id,),
        ).fetchall()
    content = ""
    for row in rows:
        allocation = json.loads(row["allocation_json"]) if row["allocation_json"] else {}
        content += f"""
        <article class="advice-block">
          <div class="advice-head">
            <h2>{escape(row['advice_date'])}</h2>
            <span class="badge">{escape(row['risk_level'])}</span>
            <span class="muted">{escape(row['model_version'] or '')}</span>
          </div>
          <p>{escape(row['market_summary'])}</p>
          <div class="profile-grid">
            {profile_panel('激进型', row['aggressive_advice'])}
            {profile_panel('中等型', row['balanced_advice'])}
            {profile_panel('保守型', row['conservative_advice'])}
          </div>
          <h3>关键假设</h3><p>{escape(row['assumptions'])}</p>
          <h3>风险提示</h3><p>{escape(row['risk_warnings'])}</p>
          {target_volatility_panel(allocation.get('target_volatility') or {})}
          {risk_budget_panel(allocation.get('risk_budget') or {})}
          {recommendation_panel(allocation.get('focus_assets', []))}
          <h3>证据入口</h3>
          {advice_evidence_cards(allocation)}
          {collapsible("原始建议 JSON", f"<pre>{escape(json.dumps(allocation, ensure_ascii=False, indent=2))}</pre>")}
        </article>
        """
    body = advice_selector(history, selected_id)
    body += content or empty("还没有建议记录。")
    body += advice_history_table(history)
    return render_page("每日建议", section("每日建议", body), "/advice")


def render_evidence(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        prediction_rows = conn.execute(
            """
            SELECT p.id, p.asset_id, a.code, a.name, a.asset_type, p.prediction_date, p.horizon_days,
                   p.up_probability, p.expected_return, p.expected_return_low,
                   p.expected_return_high, p.downside_risk, p.confidence,
                   p.model_version, p.input_window_start, p.input_window_end
            FROM model_predictions p
            LEFT JOIN assets a ON a.id = p.asset_id
            ORDER BY p.prediction_date DESC, a.code, p.horizon_days
            LIMIT 120
            """
        ).fetchall()
        monitoring = conn.execute(
            """
            SELECT *
            FROM model_monitoring_reports
            WHERE report_date = (SELECT MAX(report_date) FROM model_monitoring_reports)
            ORDER BY CASE status WHEN 'degraded' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, model_version
            """
        ).fetchall()
        runs = conn.execute("SELECT * FROM backtest_runs ORDER BY created_at DESC, id DESC LIMIT 30").fetchall()
        results = conn.execute(
            """
            SELECT r.id, r.run_id, a.code, r.prediction_date, r.horizon_days,
                   r.predicted_return, r.actual_return, r.predicted_direction,
                   r.actual_direction, r.prediction_score, r.risk_score,
                   r.advice_score, r.overall_score
            FROM backtest_results r
            LEFT JOIN assets a ON a.id = r.asset_id
            ORDER BY r.prediction_date DESC, r.id DESC
            LIMIT 120
            """
        ).fetchall()
        snapshots = conn.execute("SELECT * FROM market_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 10").fetchall()
        macro_latest = conn.execute(
            """
            SELECT m.series_id, m.observation_date, m.value, m.source
            FROM macro_observations m
            JOIN (
                SELECT series_id, MAX(observation_date) AS observation_date
                FROM macro_observations
                GROUP BY series_id
            ) latest
              ON latest.series_id = m.series_id
             AND latest.observation_date = m.observation_date
            ORDER BY m.series_id
            """
        ).fetchall()
        capital_flows = latest_capital_flow_observations(conn, limit=20)
        data_status = database_status(conn, db_path)
    run_rows = [decode_metrics(row) for row in runs]
    body = section("证据入口", evidence_hub_links(data_status))
    body += section("模型预测", asset_prediction_cards(prediction_rows))
    body += section("回测与模型健康", model_monitoring_panel(monitoring) + backtest_health_panel(run_rows, results))
    body += section("市场与资金流", market_snapshot_panel(snapshots[0] if snapshots else None) + capital_flow_panel(capital_flows) + macro_latest_panel(macro_latest))
    body += section("数据覆盖", data_status_panel(data_status))
    body += section(
        "技术明细",
        collapsible("预测原始行", table(prediction_rows, ["id", "code", "name", "prediction_date", "horizon_days", "up_probability", "expected_return", "downside_risk", "confidence", "model_version"]))
        + collapsible("回测原始行", table(results, ["id", "run_id", "code", "prediction_date", "horizon_days", "predicted_return", "actual_return", "prediction_score", "risk_score", "advice_score", "overall_score"]))
        + collapsible("旧页面入口", '<div class="link-grid"><a href="/market">市场指标</a><a href="/data">数据与曲线</a><a href="/predictions">预测</a><a href="/backtests">回测评分</a><a href="/timeline">研究时间线</a></div>'),
    )
    return render_page("证据", body, "/evidence")


def render_settings(db_path: Path, query: dict[str, list[str]]) -> str:
    init_db(db_path)
    saved_message = ""
    if _first_query_value(query, "save") == "1":
        preference = _preference_from_query(query)
        with connect(db_path) as conn:
            preference_id = upsert_user_preference(conn, preference)
        saved_message = f'<div class="notice">已保存风险设置 #{preference_id}。重新生成每日建议后会应用该设置。</div>'

    with connect(db_path) as conn:
        active = active_user_preference(conn)
        preferences = list_user_preferences(conn)
        data_status = database_status(conn, db_path)
        run_health = dashboard_run_health(conn, data_status)
        adapters = _communication_adapters(conn)
        recipients = _communication_recipients(conn)
        messages = _communication_messages(conn, limit=20)
        log_rows = conn.execute(
            """
            SELECT id, task_name, run_date, started_at, finished_at, status,
                   duration_ms, message, error
            FROM task_logs
            ORDER BY started_at DESC, id DESC
            LIMIT 80
            """
        ).fetchall()
    scheduler = scheduler_status(db_path)

    form_values = dict(active) if active else {
        "profile_name": "默认账户",
        "risk_profile": "balanced",
        "investment_horizon_days": 20,
        "max_equity_pct": 0.6,
        "min_cash_pct": 0.1,
        "notes": "",
    }
    body = saved_message + section("当前风险画像", active_preference_summary(form_values))
    body += settings_form(form_values)
    body += section("通知与通信健康", communication_health_panel(adapters, recipients, messages) + communication_adapter_panel(adapters) + communication_recipient_panel(recipients))
    body += section("数据更新状态", data_status_panel(data_status))
    body += section("系统健康", scheduler_health_panel(scheduler) + run_health_panel(run_health) + log_failure_guidance(log_rows))
    body += section(
        "技术明细",
        collapsible("已保存设置字段", table(preferences, ["profile_name", "risk_profile", "investment_horizon_days", "max_equity_pct", "min_cash_pct", "is_active", "updated_at"]))
        + collapsible("最近任务日志", table(log_rows, ["id", "task_name", "run_date", "started_at", "finished_at", "status", "duration_ms", "message", "error"]))
        + collapsible("旧页面入口", '<div class="link-grid"><a href="/communication">手机通信</a><a href="/logs">任务日志</a></div>'),
    )
    return render_page("设置", body, "/settings")


def render_portfolios(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        portfolios = portfolio_overview_rows(conn)
        selected_id = int(_first_query_value(query, "portfolio_id", portfolios[0]["id"] if portfolios else 0) or 0)
        selected = next((row for row in portfolios if int(row["id"]) == selected_id), None)
        positions = portfolio_positions(conn, selected_id) if selected else []
        transactions = portfolio_transactions(conn, selected_id) if selected else []
        valuations = portfolio_valuations(conn, selected_id) if selected else []
    if not portfolios:
        body = empty("还没有模拟组合；运行 `investment-forecasting portfolio create` 后会显示。")
        return render_page("模拟组合", section("模拟组合", body), "/portfolios")
    body = section("组合概览", portfolio_selector(portfolios, selected_id) + portfolio_summary(selected))
    body += section("权益曲线", portfolio_equity_curve(valuations, selected["initial_capital"]))
    body += section("当前持仓", portfolio_position_table(positions))
    body += section("交易与估值记录", portfolio_activity_panel(transactions, valuations))
    return render_page("模拟组合", body, "/portfolios")


def render_experts(db_path: Path, query: dict[str, list[str]]) -> str:
    selected_expert_key = str(_first_query_value(query, "expert", "") or "")
    with connect(db_path) as conn:
        experts = expert_overview_rows(conn)
        lessons = expert_lesson_rows(conn)
        equity_rows = expert_equity_rows(conn)
        selected_details = expert_detail_rows(conn, expert_key=selected_expert_key) if selected_expert_key else []
    if not experts:
        body = section("专家委员会", empty("还没有专家记录；请先运行 experts init。"))
        return render_page("专家委员会", body, "/experts")

    if selected_expert_key:
        if selected_details:
            expert_name = selected_details[0]["expert"]["name"]
            body = '<div class="expert-detail-page"><p class="muted"><a href="/experts">返回专家总览</a></p>' + expert_detail_page(selected_details[0]) + "</div>"
            return render_page(f"{expert_name}详情", body, "/experts")
        body = section("专家详情", '<p class="muted"><a href="/experts">返回专家总览</a></p>' + empty("没有找到该专家，可能已被过滤或尚未初始化。"))
        return render_page("专家详情", body, "/experts")

    body = section("专家总览", expert_cards(experts))
    body += section("专家收益对比", expert_overview_investment_panel(equity_rows))
    body += section("复盘与经验", expert_lessons_panel(lessons))
    return render_page("专家委员会", body, "/experts")


def render_logs(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, task_name, run_date, started_at, finished_at, status,
                   duration_ms, message, error
            FROM task_logs
            ORDER BY started_at DESC, id DESC
            LIMIT 200
            """
        ).fetchall()
        data_status = database_status(conn, db_path)
        run_health = dashboard_run_health(conn, data_status)
    body = section("运行健康摘要", run_health_panel(run_health) + log_failure_guidance(rows))
    body += section("技术明细", collapsible("原始任务日志", table(rows, ["id", "task_name", "run_date", "started_at", "finished_at", "status", "duration_ms", "message", "error"])))
    return render_page("任务日志", body, "/logs")


def render_communication(db_path: Path, query: dict[str, list[str]]) -> str:
    notice = ""
    with connect(db_path) as conn:
        test_recipient = _first_query_value(query, "recipient_key")
        if _first_query_value(query, "dry_run_test") and test_recipient:
            try:
                message = send_outbound_message(
                    conn,
                    channel=str(_first_query_value(query, "channel", "imessage") or "imessage"),
                    recipient_key=str(test_recipient),
                    template_key="webui_dry_run_test",
                    subject="Investment Forecasting WebUI dry-run test",
                    body="投资研究系统 WebUI 干跑测试消息，仅用于验证通信链路，不构成投资建议。",
                    severity="info",
                    payload_summary="WebUI dry-run test message",
                    idempotency_key=f"webui:dry_run_test:{test_recipient}",
                    dry_run=True,
                )
                notice = f'<div class="notice">已记录干跑测试：{escape(message["status"])}，不会触发真实手机发送。</div>'
            except CommunicationError as exc:
                notice = f'<div class="notice warn">干跑测试未通过：{escape(str(exc))}</div>'
        adapters = _communication_adapters(conn)
        recipients = _communication_recipients(conn)
        messages = _communication_messages(conn, limit=60)
        recent_errors = [row for row in messages if row.get("status") in {"failed", "permission_required", "recipient_not_allowed", "rate_limited"}][:8]
    body = notice
    body += section("通信状态", communication_health_panel(adapters, recipients, messages))
    body += section("iMessage 设置健康", communication_adapter_panel(adapters))
    body += section("Allowlist 收件人", communication_recipient_panel(recipients))
    body += section("干跑测试", communication_dry_run_form(recipients))
    body += section("最近 outbound messages", communication_messages_panel(messages, recent_errors))
    body += section(
        "技术明细",
        collapsible(
            "脱敏收件人与最近消息字段",
            table(_communication_technical_rows(recipients, messages), ["kind", "key", "channel", "status", "masked_address", "template_key", "requested_at", "error"]),
        ),
    )
    return render_page("手机通信", body, "/communication")


def _communication_adapters(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT cfg.*,
               om.status AS last_status,
               om.error AS last_error,
               om.requested_at AS last_requested_at,
               om.template_key AS last_template_key
        FROM communication_adapter_configs cfg
        LEFT JOIN outbound_messages om ON om.id = (
            SELECT id
            FROM outbound_messages
            WHERE channel = cfg.channel
            ORDER BY requested_at DESC, id DESC
            LIMIT 1
        )
        ORDER BY cfg.channel
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _communication_recipients(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT cr.*,
               om.status AS last_status,
               om.requested_at AS last_requested_at,
               om.error AS last_error
        FROM communication_recipients cr
        LEFT JOIN outbound_messages om ON om.id = (
            SELECT id
            FROM outbound_messages
            WHERE recipient_key = cr.recipient_key
            ORDER BY requested_at DESC, id DESC
            LIMIT 1
        )
        ORDER BY cr.channel, cr.recipient_key
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["masked_address"] = mask_recipient_address(item.get("address"))
        result.append(item)
    return result


def _communication_messages(conn: Any, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT om.id, om.channel, om.recipient_key, cr.display_name,
               om.template_key, om.subject, om.severity, om.payload_summary,
               om.status, om.error, om.requested_at, om.sent_at
        FROM outbound_messages om
        LEFT JOIN communication_recipients cr ON cr.id = om.recipient_id
        ORDER BY om.requested_at DESC, om.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def communication_health_panel(adapters: list[dict[str, Any]], recipients: list[dict[str, Any]], messages: list[dict[str, Any]]) -> str:
    imessage = next((row for row in adapters if row.get("channel") == "imessage"), None)
    enabled_recipients = [row for row in recipients if row.get("allowlisted") and row.get("enabled")]
    last = messages[0] if messages else None
    failing = [row for row in messages[:20] if row.get("status") in {"failed", "permission_required"}]
    health = "可干跑" if enabled_recipients else "未配置收件人"
    if not imessage or not imessage.get("enabled"):
        health = "adapter 未启用"
    elif failing:
        health = "近期有失败"
    return stat_grid(
        [
            ("总体状态", health),
            ("Adapter 数", len(adapters)),
            ("Allowlist 收件人", len(enabled_recipients)),
            ("最近发送状态", last.get("status") if last else "暂无"),
            ("最近模板", last.get("template_key") if last else "暂无"),
            ("最近错误数", len(failing)),
        ]
    )


def communication_adapter_panel(adapters: list[dict[str, Any]]) -> str:
    if not adapters:
        return empty("还没有通信 adapter 配置；先运行 communication configure-adapter。")
    preflight = system_preflight()
    cards = "".join(
        f"""
        <article class="score-card {'warn' if not row.get('enabled') else ''}">
          <div><span>{escape(row.get('channel'))}</span><strong>{escape(row.get('setup_status') or 'unverified')}</strong></div>
          <p>启用：{escape('是' if row.get('enabled') else '否')} · 默认：{escape('干跑' if row.get('dry_run_default') else '真实发送')}</p>
          <small>最后验证：{escape(row.get('last_verified_at') or '暂无')} · 最近发送：{escape(row.get('last_status') or '暂无')}</small>
          <em>{escape(row.get('last_error') or row.get('last_template_key') or '暂无错误')}</em>
        </article>
        """
        for row in adapters
    )
    checks = "".join(
        f'<li>{"通过" if check["ok"] else "待处理"}：{escape(check["name"])} · {escape(check["detail"])}</li>'
        for check in preflight["checks"]
    )
    return f'<div class="score-card-grid">{cards}</div><div class="summary"><h3>本机 iMessage 预检</h3><ul>{checks}</ul></div>'


def communication_recipient_panel(recipients: list[dict[str, Any]]) -> str:
    if not recipients:
        return empty("还没有收件人；先通过 CLI 显式 allowlist 后再发送通知。")
    rows = [
        {
            "recipient_key": row["recipient_key"],
            "display_name": row["display_name"],
            "channel": row["channel"],
            "masked_address": row["masked_address"],
            "allowlisted": "是" if row["allowlisted"] else "否",
            "enabled": "是" if row["enabled"] else "否",
            "min_severity": row["min_severity"],
            "rate_limit_per_hour": row["rate_limit_per_hour"],
            "quiet_hours": _quiet_hours_label(row),
            "last_status": row.get("last_status") or "暂无",
        }
        for row in recipients
    ]
    return table(rows, ["recipient_key", "display_name", "channel", "masked_address", "allowlisted", "enabled", "min_severity", "rate_limit_per_hour", "quiet_hours", "last_status"])


def communication_dry_run_form(recipients: list[dict[str, Any]]) -> str:
    allowed = [row for row in recipients if row.get("allowlisted") and row.get("enabled")]
    if not allowed:
        return empty("没有可干跑测试的 allowlisted 收件人。")
    options = "".join(
        f'<option value="{escape(row["recipient_key"])}">{escape(row["display_name"])} · {escape(row["recipient_key"])} · {escape(row["masked_address"])}</option>'
        for row in allowed
    )
    return f"""
    <form class="toolbar" method="get" action="/communication">
      <input type="hidden" name="dry_run_test" value="1">
      <select name="recipient_key">{options}</select>
      <button type="submit">发送干跑测试</button>
    </form>
    <p class="muted">干跑测试只写入 outbound_messages，状态为 dry_run，不会调用 Messages 或真实发送到手机。</p>
    """


def communication_messages_panel(messages: list[dict[str, Any]], recent_errors: list[dict[str, Any]]) -> str:
    if not messages:
        return empty("还没有 outbound message 记录；干跑测试或工作流通知后会显示。")
    rows = [
        {
            "id": row["id"],
            "channel": row["channel"],
            "recipient_key": row["recipient_key"],
            "display_name": row.get("display_name") or "",
            "template_key": row["template_key"],
            "severity": row["severity"],
            "status": row["status"],
            "payload_summary": row.get("payload_summary") or "",
            "requested_at": row["requested_at"],
            "sent_at": row.get("sent_at") or "",
            "error": row.get("error") or "",
        }
        for row in messages[:30]
    ]
    error_panel = ""
    if recent_errors:
        cards = "".join(
            f"""
            <article class="failure-card">
              <div><span>{escape(row.get('template_key'))}</span><strong>{escape(row.get('status'))}</strong></div>
              <p>{escape(row.get('error') or '没有错误详情')}</p>
              <em>{escape(row.get('requested_at') or '')}</em>
            </article>
            """
            for row in recent_errors
        )
        error_panel = f'<div class="failure-grid">{cards}</div>'
    return error_panel + table(rows, ["id", "channel", "recipient_key", "display_name", "template_key", "severity", "status", "payload_summary", "requested_at", "sent_at", "error"])


def _communication_technical_rows(recipients: list[dict[str, Any]], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "kind": "recipient",
            "key": row["recipient_key"],
            "channel": row["channel"],
            "status": "allowlisted" if row["allowlisted"] and row["enabled"] else "disabled",
            "masked_address": row["masked_address"],
            "template_key": "",
            "requested_at": row.get("last_requested_at") or "",
            "error": row.get("last_error") or "",
        }
        for row in recipients
    ]
    rows.extend(
        {
            "kind": "message",
            "key": row["recipient_key"],
            "channel": row["channel"],
            "status": row["status"],
            "masked_address": "",
            "template_key": row["template_key"],
            "requested_at": row["requested_at"],
            "error": row.get("error") or "",
        }
        for row in messages[:20]
    )
    return rows


def mask_recipient_address(value: Any) -> str:
    text = str(value or "")
    if not text:
        return "未设置"
    if "@" in text:
        name, domain = text.split("@", 1)
        prefix = name[:2] if len(name) > 2 else name[:1]
        return f"{prefix}***@{domain}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 7:
        return f"{text[:3]}***{text[-4:]}"
    return text[:2] + "***"


def _quiet_hours_label(row: dict[str, Any]) -> str:
    start = row.get("quiet_hours_start")
    end = row.get("quiet_hours_end")
    return f"{start}-{end}" if start and end else "未设置"


def backtest_health_panel(run_rows: list[dict[str, Any]], result_rows: Any) -> str:
    if not run_rows:
        return empty("还没有回测记录；运行 backtest run 后会显示模型健康、周期评分和原始结果。")
    latest = run_rows[0]
    score = latest.get("mean_overall_score")
    count = int(latest.get("count") or 0)
    state = backtest_health_state(score, count)
    notice = ""
    if state["level"] != "ok":
        notice = f'<div class="notice warn">{escape(state["message"])}</div>'
    return (
        notice
        + stat_grid(
            [
                ("模型版本", latest.get("model_version") or "暂无"),
                ("样本窗口", f"{latest.get('start_date')} 至 {latest.get('end_date')}"),
                ("样本数", count),
                ("方向准确率", percent(latest.get("direction_accuracy"))),
                ("IC", latest.get("information_coefficient")),
                ("Rank IC", latest.get("rank_ic")),
                ("分桶价差", market_percent(latest.get("bucket_spread"))),
                ("风险命中率", percent(latest.get("risk_hit_rate"))),
                ("综合评分", latest.get("mean_overall_score")),
            ]
        )
        + f'<p class="muted">最新回测覆盖 {escape(len(list(result_rows or [])))} 条历史预测评分；原始行已放入技术明细。</p>'
    )


def model_monitoring_panel(rows: Any) -> str:
    rows = list(rows or [])
    if not rows:
        return '<div class="notice warn">还没有模型监控报告；运行 monitoring run 后会显示评分漂移、数据陈旧和模型退化状态。</div>'
    cards = []
    for row in rows:
        warnings = _json_list(row["warnings_json"])
        governance = _monitoring_metric(row, "governance") or {}
        message = "模型健康正常。" if not warnings else "；".join(_monitoring_warning_text(item) for item in warnings[:3])
        governance_text = governance.get("governance_state") or "unknown"
        blockers = governance.get("promotion_blockers") or []
        blocker_text = " · 阻断 " + "、".join(str(item) for item in blockers[:3]) if blockers else ""
        cards.append(
            f"""
            <article class="score-card {escape(row['status'])}">
              <div><span>{escape(row['model_version'])}</span><strong>{escape(row['status'])}</strong></div>
              <small>报告 {escape(row['report_date'])} · 预测 {escape(row['latest_prediction_date'] or '暂无')} · 回测 {escape(row['latest_backtest_end_date'] or '暂无')}</small>
              <p>预测 {escape(format_stat(row['mean_prediction_score']))} · 风险 {escape(format_stat(row['mean_risk_score']))} · Rank IC {escape(format_stat(_monitoring_metric(row, 'mean_rank_ic')))} · 分桶 {market_percent(_monitoring_metric(row, 'mean_bucket_spread'))}</p>
              <p>治理状态 {escape(governance_text)} · Jarvis主结论 {'允许' if governance.get('jarvis_primary_allowed') else '不允许'}{escape(blocker_text)}</p>
              <em>{escape(message)}</em>
            </article>
            """
        )
    return '<div class="score-card-grid">' + "".join(cards) + "</div>"


def _monitoring_warning_text(item: dict[str, Any]) -> str:
    code = item.get("code")
    value = item.get("value")
    labels = {
        "stale_predictions": "预测数据陈旧",
        "stale_backtests": "回测数据陈旧",
        "low_overall_score": "综合评分偏低",
        "low_prediction_score": "预测评分偏低",
        "low_risk_score": "风险评分偏低",
        "negative_benchmark_excess": "基准超额为负",
        "score_drift": "评分出现下滑",
        "insufficient_validation_sample": "验证样本不足",
        "negative_rank_ic": "Rank IC 为负",
        "negative_bucket_spread": "分桶价差为负",
    }
    return f"{labels.get(code, str(code))}: {format_cell(value)}"


def _monitoring_metric(row: Any, key: str) -> Any:
    metrics = {}
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except (json.JSONDecodeError, KeyError, TypeError):
        metrics = {}
    return metrics.get(key)


def _json_list(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def backtest_health_state(score: Any, count: int) -> dict[str, str]:
    if score is None or count <= 0:
        return {"level": "missing", "message": "回测样本不足，模型健康需要降权理解。"}
    value = float(score)
    if count < 20:
        return {"level": "warn", "message": "回测样本偏少，先看方向和风险是否稳定，再扩大解释范围。"}
    if value < 60:
        return {"level": "warn", "message": "综合评分偏弱，当前模型处于降级观察状态。"}
    return {"level": "ok", "message": "模型健康可用于研究参考。"}


def backtest_horizon_cards(run_rows: list[dict[str, Any]]) -> str:
    if not run_rows:
        return empty("还没有分周期评分。")
    latest_by_horizon: dict[int, dict[str, Any]] = {}
    for row in run_rows:
        horizon = int(row.get("horizon_days") or 0)
        if horizon and horizon not in latest_by_horizon:
            latest_by_horizon[horizon] = row
    cards = "".join(backtest_horizon_card(horizon, row) for horizon, row in sorted(latest_by_horizon.items()))
    return f'<div class="score-card-grid">{cards}</div>'


def backtest_horizon_card(horizon: int, row: dict[str, Any]) -> str:
    state = backtest_health_state(row.get("mean_overall_score"), int(row.get("count") or 0))
    return f"""
    <article class="score-card {escape(state['level'])}">
      <div><span>{escape(horizon)}日</span><strong>{format_stat(row.get('mean_overall_score'))}</strong></div>
      <small>{escape(row.get('model_version') or '暂无模型')} · 样本 {escape(row.get('count') or 0)}</small>
      <p>Rank IC {escape(format_stat(row.get('rank_ic')))} · 分桶 {market_percent(row.get('bucket_spread'))} · IC {escape(format_stat(row.get('information_coefficient')))}</p>
      <p>方向 {escape(percent(row.get('direction_accuracy')))} · 风险 {escape(percent(row.get('risk_hit_rate')))} · 误差 {escape(format_stat(row.get('mean_return_error')))}</p>
      <em>{escape(state['message'])}</em>
    </article>
    """


def advice_evidence_cards(allocation: dict[str, Any]) -> str:
    evidence = allocation.get("evidence") or {}
    focus_assets = allocation.get("focus_assets") or []
    target_volatility = allocation.get("target_volatility") or {}
    chips = [
        evidence_chip("预测证据", len(evidence.get("source_prediction_ids") or []), "/predictions", "用于候选资产与方向判断"),
        evidence_chip("回测证据", len(evidence.get("backtest_run_ids") or []), "/backtests", "用于模型可信度与风险校验"),
        evidence_chip("市场快照", "已连接" if evidence.get("market_snapshot_id") else "缺失", "/", "用于市场宽度和情绪判断"),
        evidence_chip("资金流证据", len(evidence.get("capital_flow_ids") or []), "/market", "用于流动性和拥挤度辅助判断"),
        evidence_chip("波动率证据", len(evidence.get("target_volatility_feature_ids") or []), "/data", "用于目标波动率配置约束"),
        evidence_chip("相关性证据", len(evidence.get("risk_budget_asset_ids") or []), "/data", "用于风险预算和分散度检查"),
        evidence_chip("关注资产", len(focus_assets), "/data", "用于下一步逐项检查"),
    ]
    return '<div class="evidence-chip-grid">' + "".join(chips) + "</div>"


def target_volatility_panel(proposal: dict[str, Any]) -> str:
    if not proposal:
        return ""
    weights = proposal.get("proposed_weights") or {}
    constraints = proposal.get("constraints") or {}
    evidence = proposal.get("evidence") or {}
    notes = proposal.get("notes") or []
    assets = proposal.get("selected_assets") or []
    content = stat_grid(
        [
            ("状态", proposal.get("status") or "暂无"),
            ("目标年化波动", plain_percent(constraints.get("target_annual_volatility"))),
            ("权益建议", plain_percent(weights.get("equity"))),
            ("固收建议", plain_percent(weights.get("fixed_income"))),
            ("现金建议", plain_percent(weights.get("cash"))),
            ("风险样本", evidence.get("asset_count") or 0),
        ]
    )
    if notes:
        content += '<p class="muted">' + escape(" ".join(notes)) + "</p>"
    if assets:
        rows = [
            {
                "name": item.get("name") or item.get("code"),
                "bucket": item.get("bucket"),
                "annualized_volatility": plain_percent(item.get("annualized_volatility")),
                "max_drawdown_60d": plain_percent(item.get("max_drawdown_60d"), signed=True),
                "return_20d": plain_percent(item.get("return_20d"), signed=True),
            }
            for item in assets
        ]
        content += table(rows, ["name", "bucket", "annualized_volatility", "max_drawdown_60d", "return_20d"])
    return "<h3>目标波动率配置</h3>" + content


def risk_budget_panel(proposal: dict[str, Any]) -> str:
    if not proposal:
        return ""
    risk_budget = proposal.get("risk_budget") or {}
    correlation = proposal.get("correlation") or {}
    evidence = proposal.get("evidence") or {}
    notes = proposal.get("notes") or []
    content = stat_grid(
        [
            ("状态", proposal.get("status") or "暂无"),
            ("成对相关样本", correlation.get("pair_count") or 0),
            ("平均绝对相关", format_stat(correlation.get("average_abs_correlation"))),
            ("权益风险贡献", plain_percent(risk_budget.get("equity"))),
            ("固收风险贡献", plain_percent(risk_budget.get("fixed_income"))),
            ("价格观测", evidence.get("price_observation_count") or 0),
        ]
    )
    if notes:
        content += '<p class="muted">' + escape(" ".join(notes)) + "</p>"
    asset_rows = proposal.get("asset_risk") or []
    if asset_rows:
        rows = [
            {
                "name": item.get("name") or item.get("code"),
                "bucket": item.get("bucket"),
                "asset_weight": plain_percent(item.get("asset_weight")),
                "annualized_volatility": plain_percent(item.get("annualized_volatility")),
                "correlation_load": format_stat(item.get("correlation_load")),
                "risk_score": format_stat(item.get("risk_score")),
            }
            for item in asset_rows[:8]
        ]
        content += table(rows, ["name", "bucket", "asset_weight", "annualized_volatility", "correlation_load", "risk_score"])
    return "<h3>相关性风险预算</h3>" + content


def evidence_chip(label: str, value: Any, href: str, hint: str) -> str:
    return f"""
    <a class="evidence-chip" href="{escape(href)}">
      <span>{escape(label)}</span>
      <strong>{escape(value)}</strong>
      <small>{escape(hint)}</small>
    </a>
    """


def active_preference_summary(values: dict[str, Any]) -> str:
    return (
        stat_grid(
            [
                ("账户", values.get("profile_name") or "默认账户"),
                ("风险偏好", _risk_profile_label(values.get("risk_profile"))),
                ("关注周期", f"{values.get('investment_horizon_days')} 天"),
                ("权益上限", plain_percent(values.get("max_equity_pct"))),
                ("现金底线", plain_percent(values.get("min_cash_pct"))),
                ("备注", values.get("notes") or "暂无"),
            ]
        )
        + '<p class="muted">下一次生成每日建议时，会按这个画像约束权益/现金仓位和关注周期。</p>'
    )


def log_failure_guidance(rows: Any) -> str:
    rows = list(rows or [])
    failures = [row for row in rows if row["status"] == "failed"]
    latest = rows[0] if rows else None
    summary = stat_grid(
        [
            ("最近任务", latest["task_name"] if latest else "暂无"),
            ("最近状态", latest["status"] if latest else "暂无"),
            ("失败数量", len(failures)),
            ("日志数量", len(rows)),
        ]
    )
    if not rows:
        return summary + empty("还没有任务日志；运行 daily run 或 CLI 命令后会记录状态。")
    if not failures:
        return summary + '<p class="muted">未发现失败任务；原始日志保留在技术明细中。</p>'
    cards = "".join(log_failure_card(row) for row in failures[:6])
    return summary + f'<div class="failure-grid">{cards}</div>'


def log_failure_card(row: Any) -> str:
    return f"""
    <article class="failure-card">
      <div><span>{escape(row['run_date'])}</span><strong>{escape(row['task_name'])}</strong></div>
      <p>{escape(row['error'] or row['message'] or '任务失败但没有错误详情。')}</p>
      <em>恢复提示：查看该任务输入、数据源和最近一次成功记录，修复后重新运行对应 CLI 或 daily run。</em>
    </article>
    """


def portfolio_overview_rows(conn: Any) -> list[Any]:
    return conn.execute(
        """
        SELECT vp.*, vv.valuation_date, vv.cash AS valuation_cash,
               vv.positions_value, vv.total_value
        FROM virtual_portfolios vp
        LEFT JOIN virtual_valuations vv ON vv.id = (
            SELECT id FROM virtual_valuations
            WHERE portfolio_id = vp.id
            ORDER BY valuation_date DESC, id DESC
            LIMIT 1
        )
        ORDER BY vp.owner_type, vp.id
        """
    ).fetchall()


def portfolio_positions(conn: Any, portfolio_id: int) -> list[Any]:
    return conn.execute(
        """
        SELECT a.code, a.name, a.asset_type, p.quantity, p.average_cost,
               price.trade_date AS price_date, price.price_value AS latest_price,
               p.quantity * price.price_value AS market_value
        FROM virtual_positions p
        JOIN assets a ON a.id = p.asset_id
        LEFT JOIN (
            SELECT pd.asset_id, pd.trade_date, COALESCE(pd.close, pd.nav, pd.adjusted_close) AS price_value
            FROM price_daily pd
            WHERE COALESCE(pd.close, pd.nav, pd.adjusted_close) IS NOT NULL
        ) price ON price.asset_id = p.asset_id
              AND price.trade_date = (
                SELECT MAX(trade_date)
                FROM price_daily
                WHERE asset_id = p.asset_id
                  AND COALESCE(close, nav, adjusted_close) IS NOT NULL
              )
        WHERE p.portfolio_id = ? AND p.quantity > 0
        ORDER BY market_value DESC NULLS LAST, a.code
        """,
        (portfolio_id,),
    ).fetchall()


def portfolio_transactions(conn: Any, portfolio_id: int) -> list[Any]:
    return conn.execute(
        """
        SELECT vt.id, vt.trade_date, vt.side, a.code, a.name, vt.quantity,
               vt.price, vt.price_date, vt.gross_amount, vt.fee,
               vt.cash_delta, vt.status, vt.reason
        FROM virtual_transactions vt
        LEFT JOIN assets a ON a.id = vt.asset_id
        WHERE vt.portfolio_id = ?
        ORDER BY vt.trade_date DESC, vt.id DESC
        LIMIT 80
        """,
        (portfolio_id,),
    ).fetchall()


def portfolio_valuations(conn: Any, portfolio_id: int) -> list[Any]:
    return conn.execute(
        """
        SELECT valuation_date, cash, positions_value, total_value, missing_prices_json
        FROM virtual_valuations
        WHERE portfolio_id = ?
        ORDER BY valuation_date ASC, id ASC
        LIMIT 240
        """,
        (portfolio_id,),
    ).fetchall()


def portfolio_selector(portfolios: list[Any], selected_id: int) -> str:
    options = "".join(
        f'<option value="{row["id"]}" {"selected" if row["id"] == selected_id else ""}>{escape(row["name"])} · {escape(row["owner_type"])} #{escape(row["owner_id"] or "-")}</option>'
        for row in portfolios
    )
    return f'<form class="toolbar" method="get" action="/portfolios"><select name="portfolio_id">{options}</select><button type="submit">查看</button></form>'


def portfolio_summary(row: Any) -> str:
    if not row:
        return empty("没有选中的模拟组合。")
    total_value = row["total_value"] if row["total_value"] is not None else row["cash"]
    current_return = _portfolio_return_from_values(row["initial_capital"], total_value)
    return stat_grid(
        [
            ("组合名称", row["name"]),
            ("归属", f"{row['owner_type']} #{row['owner_id'] or '-'}"),
            ("初始资产", money(row["initial_capital"])),
            ("现金", money(row["cash"])),
            ("总资产", money(total_value)),
            ("当前收益", current_return),
            ("最近估值", row["valuation_date"] or "暂无"),
            ("状态", row["status"]),
        ]
    )


def portfolio_position_table(rows: list[Any]) -> str:
    if not rows:
        return empty("当前没有持仓，资金仍在现金中。")
    return table(rows, ["code", "name", "asset_type", "quantity", "average_cost", "price_date", "latest_price", "market_value"])


def portfolio_activity_panel(transactions: list[Any], valuations: list[Any]) -> str:
    transaction_table = table(transactions, ["id", "trade_date", "side", "code", "name", "quantity", "price", "price_date", "gross_amount", "fee", "cash_delta", "status", "reason"])
    valuation_table = table(valuations, ["valuation_date", "cash", "positions_value", "total_value", "missing_prices_json"])
    return collapsible("交易记录", transaction_table) + collapsible("估值记录", valuation_table)


def portfolio_equity_curve(rows: list[Any], initial_capital: Any) -> str:
    if not rows or not initial_capital:
        return empty("还没有估值记录；运行 `investment-forecasting portfolio value` 后会显示权益曲线。")
    values = [float(row["total_value"]) for row in rows if row["total_value"] is not None]
    labels = [row["valuation_date"] for row in rows if row["total_value"] is not None]
    if len(values) < 1:
        return empty("还没有有效估值记录。")
    returns = [(value / float(initial_capital)) - 1.0 for value in values]
    low = min(min(returns), 0.0)
    high = max(max(returns), 0.0)
    span = high - low or 1.0
    width = 720
    height = 220
    points = []
    for index, value in enumerate(returns):
        x = (index / max(len(returns) - 1, 1) * width) if len(returns) > 1 else width / 2
        y = height - ((value - low) / span * height)
        points.append(f"{x:.1f},{y:.1f}")
    zero_y = height - ((0 - low) / span * height)
    latest_return = returns[-1]
    return f"""
    <div class="curve-card">
      <div class="curve-meta">
        <span>{escape(labels[0])} 至 {escape(labels[-1])}</span>
        <strong>{market_percent(latest_return)}</strong>
      </div>
      <svg class="curve" viewBox="0 0 {width} {height}" role="img" aria-label="组合权益曲线">
        <line x1="0" y1="{zero_y:.1f}" x2="{width}" y2="{zero_y:.1f}"></line>
        <polyline points="{' '.join(points)}"></polyline>
      </svg>
    </div>
    """


def jarvis_dashboard_entry(row: Any | None) -> str:
    if row is None:
        return empty("还没有 Jarvis 简报；生成后这里会成为第一眼的每日研究入口。")
    return f"""
    <a class="jarvis-entry" href="/jarvis?brief_id={escape(row['id'])}">
      <div>
        <span>{escape(row['brief_date'])} · {escape(row['version'])}</span>
        <strong>{escape(row['one_line_stance'])}</strong>
      </div>
      <b>查看 Jarvis</b>
    </a>
    """


def jarvis_selector(history: list[Any], selected_id: int) -> str:
    if not history:
        return ""
    options = "".join(
        f'<option value="{row["id"]}" {"selected" if row["id"] == selected_id else ""}>{escape(row["brief_date"])} · {escape(row["one_line_stance"])} · {escape(row["version"])}</option>'
        for row in history
    )
    return f"""
    <form class="toolbar" method="get" action="/jarvis">
      <select name="brief_id">{options}</select>
      <button type="submit">查看</button>
    </form>
    """


def jarvis_brief_view(row: Any) -> str:
    brief = decode_jarvis_row(row)
    stale = brief["stale_evidence"]
    missing = brief["missing_evidence"]
    alert = ""
    if missing:
        alert += '<div class="notice warn">存在缺失证据，当前简报应降权理解。</div>'
    if stale:
        alert += '<div class="notice warn">存在过期证据，请等待最新运行结果确认。</div>'
    body = f"""
    <article class="jarvis-brief">
      <div class="jarvis-hero">
        <div>
          <span>{escape(brief['brief_date'])} · {escape(brief['version'])}</span>
          <h2>{escape(brief['one_line_stance'])}</h2>
          <h3>综合建议</h3>
          <p>{escape(brief['combined_recommendation'])}</p>
        </div>
        <strong>{escape(brief['model_summary'].get('status', 'unknown'))}</strong>
      </div>
      {alert}
      {jarvis_focus_panel(brief['focus_directions'])}
      {jarvis_model_panel(brief['model_summary'])}
      {jarvis_expert_panel(brief['expert_summary'])}
      {jarvis_evidence_links(brief)}
      <h3>风险与边界</h3>
      <p>{escape(brief['risk_warnings'])}</p>
      {collapsible("缺失与过期证据", jarvis_warning_tables(missing, stale))}
      {collapsible("原始 Jarvis JSON", f"<pre>{escape(json.dumps(brief, ensure_ascii=False, indent=2))}</pre>")}
    </article>
    """
    return section("Jarvis 每日简报", body)


def decode_jarvis_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "brief_date": row["brief_date"],
        "version": row["version"],
        "focus_directions": json.loads(row["focus_directions_json"]),
        "one_line_stance": row["one_line_stance"],
        "model_summary": json.loads(row["model_summary_json"]),
        "expert_summary": json.loads(row["expert_summary_json"]),
        "combined_recommendation": row["combined_recommendation"],
        "risk_warnings": row["risk_warnings"],
        "evidence": json.loads(row["evidence_json"]),
        "missing_evidence": json.loads(row["missing_evidence_json"]),
        "stale_evidence": json.loads(row["stale_evidence_json"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def jarvis_focus_panel(rows: list[dict[str, Any]]) -> str:
    cards = "".join(
        f"""
        <div class="jarvis-focus-card">
          <span>今日关注方向</span>
          <strong>{escape(row.get('direction', '观察'))}</strong>
          <p>{escape(row.get('reason', '等待更多证据。'))}</p>
        </div>
        """
        for row in rows
    )
    return f'<div class="jarvis-focus-grid">{cards}</div>' if cards else empty("还没有关注方向。")


def jarvis_model_panel(model: dict[str, Any]) -> str:
    forecasts = model.get("top_forecasts") or []
    gates = model.get("confidence_gates") or []
    forecast_rows = [
        {
            "asset": f"{item.get('asset_code') or ''} {item.get('asset_name') or ''}".strip(),
            "horizon_days": item.get("horizon_days"),
            "expected_return": item.get("expected_return"),
            "downside_risk": item.get("downside_risk"),
            "confidence": percent(item.get("confidence")),
            "validation_status": item.get("validation_status"),
            "rank_ic": item.get("recent_rank_ic"),
            "bucket_spread": market_percent(item.get("bucket_spread")),
            "risk_gate": "观察" if item.get("watch_only") else "通过",
        }
        for item in forecasts
    ]
    disagreement = model.get("disagreement") or {}
    body = stat_grid(
        [
            ("模型状态", model.get("status")),
            ("预测日期", model.get("prediction_date")),
            ("平均预期收益", model.get("average_expected_return")),
            ("平均下行风险", model.get("average_downside_risk")),
            ("平均置信度", percent(model.get("average_confidence"))),
            ("回测均分", (model.get("model_quality") or {}).get("average_score")),
        ]
    )
    body += f'<p class="muted">分歧解释：{escape(disagreement.get("summary", "暂无显著分歧。"))}</p>'
    if gates:
        body += '<div class="notice warn"><strong>信心门</strong><ul>' + "".join(
            f"<li>{escape(item.get('asset') or item.get('gate', '信号'))}: {escape(item.get('reason', '已降级为观察信号。'))}</li>"
            for item in gates
        ) + "</ul></div>"
    body += table(forecast_rows, ["asset", "horizon_days", "expected_return", "downside_risk", "confidence", "validation_status", "rank_ic", "bucket_spread", "risk_gate"]) if forecast_rows else empty("还没有模型预测摘要。")
    return f'<div class="jarvis-subsection"><h3>模型预测</h3>{body}</div>'


def jarvis_expert_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<div class="jarvis-subsection"><h3>专家观点</h3>' + empty("还没有活跃专家观点。") + "</div>"
    cards = "".join(jarvis_expert_card(row) for row in rows)
    return f'<div class="jarvis-subsection"><h3>专家观点</h3><div class="jarvis-expert-grid">{cards}</div></div>'


def jarvis_expert_card(row: dict[str, Any]) -> str:
    href = f"/experts?expert={escape(row.get('expert_key') or '')}"
    state = row.get("lifecycle_state") or "active"
    thesis = row.get("ai_thesis") or row.get("rationale") or "暂无观点。"
    maturity_note = "样本不足，表现证据仅作观察。" if row.get("risk_state") == "样本不足" or row.get("score") is None else ""
    return f"""
    <a class="jarvis-expert-card state-{escape(state)}" href="{href}">
      <div class="expert-head">
        <div><h3>{escape(row.get('expert_name', '专家'))}</h3><span>{escape(row.get('style_label', ''))}</span></div>
        <b>{escape(lifecycle_label(state))}</b>
      </div>
      <p>{escape(thesis)}</p>
      {f'<p class="muted">{escape(maturity_note)}</p>' if maturity_note else ''}
      <div class="expert-card-metrics">
        <span><small>动作</small><b>{escape(row.get('action') or '暂无')}</b></span>
        <span><small>目标</small><b>{escape(row.get('target') or '暂无')}</b></span>
        <span><small>评分</small><b>{escape(row.get('score') if row.get('score') is not None else '暂无')}</b></span>
        <span><small>收益</small><b>{market_percent(row.get('current_return'))}</b></span>
        <span><small>回撤</small><b>{market_percent(row.get('max_drawdown'))}</b></span>
        <span><small>风险</small><b>{escape(row.get('risk_state') or '暂无')}</b></span>
      </div>
    </a>
    """


def jarvis_evidence_links(brief: dict[str, Any]) -> str:
    evidence = brief["evidence"]
    links = [
        ("/timeline", "研究时间线", len(evidence.get("task_log_ids") or [])),
        ("/predictions", "模型预测", evidence.get("model_prediction_count") or len(evidence.get("model_prediction_ids") or [])),
        ("/backtests", "回测评分", len(evidence.get("backtest_run_ids") or [])),
        ("/market", "资金流", len(evidence.get("capital_flow_ids") or [])),
        ("/experts", "专家委员会", len(evidence.get("expert_plan_ids") or [])),
        ("/logs", "任务日志", len(evidence.get("task_log_ids") or [])),
    ]
    items = "".join(f'<a href="{href}"><span>{escape(label)}</span><strong>{escape(count)}</strong></a>' for href, label, count in links)
    return f'<div class="jarvis-subsection"><h3>证据入口</h3><div class="jarvis-evidence-links">{items}</div></div>'


def jarvis_warning_tables(missing: list[dict[str, Any]], stale: list[dict[str, Any]]) -> str:
    body = "<h3>缺失证据</h3>" + (table(missing, ["source", "expert", "reason"]) if missing else empty("没有缺失证据。"))
    body += "<h3>过期证据</h3>" + (table(stale, ["source", "last_date", "age_days"]) if stale else empty("没有过期证据。"))
    return body


def jarvis_history_table(history: list[Any]) -> str:
    rows = [
        {
            "brief_date": f'<a href="/jarvis?brief_id={row["id"]}">{escape(row["brief_date"])}</a>',
            "one_line_stance": escape(row["one_line_stance"]),
            "version": escape(row["version"]),
            "source": escape(row["source"]),
            "updated_at": escape(row["updated_at"]),
        }
        for row in history
    ]
    return table(rows, ["brief_date", "one_line_stance", "version", "source", "updated_at"], escape_cells=False) if rows else empty("还没有历史 Jarvis 简报。")


def today_brief_page(
    jarvis: Any | None,
    advice: Any | None,
    market: Any | None,
    predictions: Any,
    preference: Any | None,
    run_health: list[dict[str, Any]],
    data_status: dict[str, Any],
    recommendations: Any,
    timeline_rows: list[dict[str, Any]],
) -> str:
    brief = decode_jarvis_row(jarvis) if jarvis else None
    body = section("今天怎么看?", today_judgement_panel(brief, advice, market, predictions, preference, run_health))
    body += section("为什么?", today_reason_panel(brief, advice, market, predictions, preference))
    body += section("能不能信?", today_trust_panel(brief, data_status, run_health, predictions))
    body += section("关注哪些资产?", today_focus_panel(brief, recommendations))
    body += section("专家是否一致?", today_expert_consensus_panel(brief))
    body += section("风险边界和观察条件", today_risk_panel(brief, market, predictions, run_health))
    body += section("证据和技术入口", today_evidence_panel(brief, data_status, timeline_rows))
    return body


def today_judgement_panel(
    brief: dict[str, Any] | None,
    advice: Any | None,
    market: Any | None,
    predictions: Any,
    preference: Any | None,
    run_health: list[dict[str, Any]],
) -> str:
    stance = brief["one_line_stance"] if brief else _dashboard_stance(None, advice, market)
    recommendation = brief["combined_recommendation"] if brief else _dashboard_watch_condition(None, market, predictions, run_health)
    status = (brief["model_summary"].get("status") if brief else "waiting") or "waiting"
    date = brief["brief_date"] if brief else "等待生成"
    return f"""
    <article class="today-hero">
      <div>
        <span>贾维斯今日简报 · {escape(date)}</span>
        <h2>{escape(stance)}</h2>
        <p>{escape(recommendation)}</p>
        <small>{escape(_dashboard_preference_text(preference))}</small>
      </div>
      <strong>{escape(status)}</strong>
    </article>
    """


def today_reason_panel(brief: dict[str, Any] | None, advice: Any | None, market: Any | None, predictions: Any, preference: Any | None) -> str:
    reasons = _dashboard_reasons_from_brief(brief, advice, market, predictions, preference)
    items = "".join(f"<li>{escape(reason)}</li>" for reason in reasons[:3])
    return f'<div class="today-reasons"><strong>三条理由</strong><ol>{items}</ol></div>'


def today_trust_panel(brief: dict[str, Any] | None, data_status: dict[str, Any], run_health: list[dict[str, Any]], predictions: Any) -> str:
    stale = brief["stale_evidence"] if brief else []
    missing = brief["missing_evidence"] if brief else []
    weak = [stage for stage in run_health if stage["status"] in {"bad", "missing", "warn"}]
    trust_text = "证据可用，但仍需按研究辅助理解。"
    if missing:
        trust_text = "存在缺失证据，今日判断需要降权。"
    elif stale:
        trust_text = "存在过期证据，等待最新运行后再提高信任度。"
    elif weak:
        trust_text = f"{weak[0]['label']}状态为{weak[0]['status_label']}，先看恢复提示。"
    cards = stat_grid(
        [
            ("可信度口径", trust_text),
            ("缺失证据", len(missing)),
            ("过期证据", len(stale)),
            ("预测覆盖", int(predictions["count"] or 0) if predictions else 0),
            ("最新行情", data_status["latest"]["price_date"] or "暂无"),
            ("最新建议", data_status["latest"]["advice_date"] or "暂无"),
        ]
    )
    return cards + run_health_panel(run_health)


def today_focus_panel(brief: dict[str, Any] | None, recommendations: Any) -> str:
    content = jarvis_focus_panel(brief["focus_directions"]) if brief else empty("还没有 Jarvis 关注方向；生成简报后会显示今天优先观察的资产和主题。")
    content += '<p class="muted"><a href="/opportunities">打开机会池，按产品类型和风险偏好继续筛选。</a></p>'
    content += recommendation_panel(recommendations)
    return content


def today_expert_consensus_panel(brief: dict[str, Any] | None) -> str:
    if not brief:
        return empty("还没有专家共识摘要；生成 Jarvis 简报后会把专家观点放在这里。")
    experts = brief["expert_summary"]
    actions = sorted({row.get("action") or "暂无" for row in experts})
    disagreement = (brief["model_summary"].get("disagreement") or {}).get("summary") or "暂无显著分歧。"
    consensus = "专家动作一致" if len(actions) == 1 and experts else "专家存在分歧" if experts else "暂无活跃专家观点"
    return stat_grid(
        [
            ("专家数量", len(experts)),
            ("一致性", consensus),
            ("动作集合", " / ".join(actions) if actions else "暂无"),
            ("分歧摘要", disagreement),
        ]
    ) + jarvis_expert_panel(experts)


def today_risk_panel(brief: dict[str, Any] | None, market: Any | None, predictions: Any, run_health: list[dict[str, Any]]) -> str:
    risk = brief["risk_warnings"] if brief else "仅作本地投资研究辅助；缺少 Jarvis 简报时不要扩大风险暴露。"
    watch = _dashboard_watch_condition(None if brief is None else {"focus_directions_json": json.dumps(brief["focus_directions"], ensure_ascii=False)}, market, predictions, run_health)
    return f"""
    <div class="risk-block">
      <p>{escape(risk)}</p>
      <p><strong>观察条件：</strong>{escape(watch.replace('观察条件：', ''))}</p>
    </div>
    """


def today_evidence_panel(brief: dict[str, Any] | None, data_status: dict[str, Any], timeline_rows: list[dict[str, Any]]) -> str:
    content = jarvis_evidence_links(brief) if brief else evidence_hub_links(data_status)
    content += '<p class="muted"><a href="/evidence">打开证据页查看模型、回测、市场、数据覆盖和原始技术明细。</a></p>'
    content += collapsible("数据新鲜度", data_status_panel(data_status))
    content += collapsible("最近研究脉络", timeline_preview(timeline_rows))
    if brief:
        content += collapsible("缺失与过期证据", jarvis_warning_tables(brief["missing_evidence"], brief["stale_evidence"]))
    return content


def dashboard_daily_brief(
    jarvis: Any | None,
    advice: Any | None,
    market: Any | None,
    predictions: Any,
    preference: Any | None,
    run_health: list[dict[str, Any]],
) -> str:
    stance = _dashboard_stance(jarvis, advice, market)
    reasons = _dashboard_reasons(jarvis, advice, market, predictions, preference)
    watch = _dashboard_watch_condition(jarvis, market, predictions, run_health)
    preference_text = _dashboard_preference_text(preference)
    reason_items = "".join(f"<li>{escape(reason)}</li>" for reason in reasons[:3])
    return f"""
    <div class="dashboard-brief">
      <div class="dashboard-brief-main">
        <span>贾维斯今日简报</span>
        <h2>{escape(stance)}</h2>
        <p>{escape(watch)}</p>
        <small>{escape(preference_text)}</small>
      </div>
      <div class="dashboard-brief-reasons">
        <strong>三条理由</strong>
        <ol>{reason_items}</ol>
      </div>
    </div>
    """


def _dashboard_stance(jarvis: Any | None, advice: Any | None, market: Any | None) -> str:
    if jarvis:
        return str(jarvis["one_line_stance"])
    if advice:
        risk_level = _risk_level_label(advice["risk_level"])
        return f"{risk_level}，等待 Jarvis 综合"
    if market:
        return f"市场{_market_sentiment_label(market['sentiment'])}，等待建议生成"
    return "等待数据入库"


def _dashboard_reasons(jarvis: Any | None, advice: Any | None, market: Any | None, predictions: Any, preference: Any | None) -> list[str]:
    reasons: list[str] = []
    if jarvis:
        try:
            focus = json.loads(jarvis["focus_directions_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            focus = []
        reasons.extend(f"{item.get('direction', '关注方向')}：{item.get('reason', '等待证据确认')}" for item in focus[:2])
    if market:
        reasons.append(f"市场快照偏{_market_sentiment_label(market['sentiment'])}，上涨宽度 {plain_percent(market['breadth'])}。")
    if predictions and predictions["count"]:
        reasons.append(f"模型覆盖 {int(predictions['count'])} 条预测，平均预期收益 {plain_percent(predictions['avg_expected_return'], signed=True)}。")
    if preference:
        reasons.append(f"风险偏好为 {preference['profile_name']}，权益上限 {plain_percent(preference['max_equity_pct'])}，现金底线 {plain_percent(preference['min_cash_pct'])}。")
    if advice:
        reasons.append(f"最新每日建议口径为 {_risk_level_label(advice['risk_level'])}。")
    return (reasons + ["缺少足够证据时，优先补齐数据、预测和回测。"])[:3]


def _dashboard_reasons_from_brief(brief: dict[str, Any] | None, advice: Any | None, market: Any | None, predictions: Any, preference: Any | None) -> list[str]:
    if brief:
        focus = brief["focus_directions"]
        reasons = [f"{item.get('direction', '关注方向')}：{item.get('reason', '等待证据确认')}" for item in focus[:2]]
        model = brief["model_summary"]
        if model.get("status") != "missing":
            reasons.append(
                f"模型平均预期收益 {plain_percent(model.get('average_expected_return'), signed=True)}，"
                f"平均下行风险 {plain_percent(model.get('average_downside_risk'))}，置信度 {percent(model.get('average_confidence'))}。"
            )
        experts = brief["expert_summary"]
        if experts:
            actions = " / ".join(sorted({row.get("action") or "暂无" for row in experts}))
            reasons.append(f"{len(experts)} 名专家已纳入，动作集合：{actions}。")
        if brief["missing_evidence"]:
            reasons.append("存在缺失证据，今日结论需要保守解释。")
        return (reasons + ["缺少足够证据时，优先补齐数据、预测和回测。"])[:3]
    return _dashboard_reasons(None, advice, market, predictions, preference)


def _dashboard_watch_condition(jarvis: Any | None, market: Any | None, predictions: Any, run_health: list[dict[str, Any]]) -> str:
    weak_stage = next((stage for stage in run_health if stage["status"] in {"bad", "missing"}), None)
    if weak_stage:
        return f"观察条件：先处理{weak_stage['label']}，否则{weak_stage['impact']}"
    if jarvis:
        try:
            focus = json.loads(jarvis["focus_directions_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            focus = []
        if focus:
            return f"观察条件：{focus[0].get('direction', '重点方向')} 若证据转弱或任务失败，需要降权处理。"
    if market and market["sentiment"] in {"risk_off", "weak"}:
        return "观察条件：市场快照偏弱时，先看回撤和流动性是否修复。"
    if predictions and predictions["count"]:
        return "观察条件：若预测均值转负或下行风险扩大，降低进攻解释强度。"
    return "观察条件：先完成数据采集、特征、预测、回测和每日建议。"


def _dashboard_preference_text(preference: Any | None) -> str:
    if not preference:
        return "风险设置：使用默认均衡偏好。"
    return (
        f"风险设置：{preference['profile_name']}，{_risk_profile_label(preference['risk_profile'])}，"
        f"{preference['investment_horizon_days']} 天，权益上限 {plain_percent(preference['max_equity_pct'])}，"
        f"现金底线 {plain_percent(preference['min_cash_pct'])}。"
    )


def _risk_profile_label(value: Any) -> str:
    return {"conservative": "稳健", "balanced": "均衡", "aggressive": "积极"}.get(str(value or ""), str(value or "均衡"))


def _risk_level_label(value: Any) -> str:
    return {
        "risk_on": "偏积极",
        "neutral": "均衡观察",
        "risk_off": "偏防守",
        "high_risk": "高风险防守",
        "low_risk": "低风险观察",
    }.get(str(value or ""), str(value or "观察"))


def _market_sentiment_label(value: Any) -> str:
    return {"risk_on": "积极", "neutral": "均衡", "risk_off": "防守", "weak": "偏弱"}.get(str(value or ""), str(value or "未知"))


RUN_HEALTH_STAGES = [
    {
        "key": "ingest",
        "label": "数据采集",
        "latest_key": "price_date",
        "count_key": "price_daily",
        "impact": "缺行情会影响特征、预测和估值。",
        "recovery": "运行 ingest mvp 或检查数据源。",
    },
    {
        "key": "features",
        "label": "指标计算",
        "latest_key": "feature_date",
        "count_key": "features_daily",
        "impact": "缺指标会影响筛选、市场状态和专家计划。",
        "recovery": "运行 features calculate。",
    },
    {
        "key": "market",
        "label": "市场快照",
        "latest_key": "snapshot_date",
        "count_key": "market_snapshots",
        "impact": "缺市场环境会削弱风险判断。",
        "recovery": "运行 market snapshot。",
    },
    {
        "key": "forecast",
        "label": "模型预测",
        "latest_key": "prediction_date",
        "count_key": "model_predictions",
        "impact": "缺预测会让关注标的排序失效。",
        "recovery": "运行 forecast run。",
    },
    {
        "key": "backtest",
        "label": "回测评分",
        "latest_key": "backtest_date",
        "count_key": "backtest_runs",
        "impact": "缺回测会降低模型可信度。",
        "recovery": "运行 backtest run。",
    },
    {
        "key": "advice",
        "label": "每日建议",
        "latest_key": "advice_date",
        "count_key": "daily_advice",
        "impact": "缺建议会缺少当天风险口径。",
        "recovery": "运行 advice generate。",
    },
    {
        "key": "monitoring",
        "label": "运行监控",
        "latest_key": "model_monitoring_date",
        "count_key": "model_monitoring_reports",
        "impact": "缺模型监控会难以及时发现评分漂移、退化或数据陈旧。",
        "recovery": "运行 monitoring run 或 daily run。",
    },
]


def dashboard_run_health(conn: Any, data_status: dict[str, Any]) -> list[dict[str, Any]]:
    counts = {
        **data_status["counts"],
        "backtest_runs": _count_rows(conn, "backtest_runs"),
        "task_logs": _count_rows(conn, "task_logs"),
        "model_monitoring_reports": _count_rows(conn, "model_monitoring_reports"),
    }
    latest = {
        **data_status["latest"],
        "snapshot_date": _max_value(conn, "market_snapshots", "snapshot_date"),
        "backtest_date": _max_value(conn, "backtest_runs", "end_date"),
        "task_log_date": _max_value(conn, "task_logs", "run_date"),
        "model_monitoring_date": _max_value(conn, "model_monitoring_reports", "report_date"),
    }
    task_summary = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
          SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count
        FROM task_logs
        WHERE run_date = (SELECT MAX(run_date) FROM task_logs)
        """
    ).fetchone()
    latest_tasks = latest_run_health_tasks(conn)
    return [_run_health_stage(stage, counts, latest, task_summary, latest_tasks.get(stage["key"])) for stage in RUN_HEALTH_STAGES]


RUN_HEALTH_TASK_STAGE = {
    "akshare_ingest_mvp": "ingest",
    "feature_calculation": "features",
    "market_snapshot": "market",
    "forecast_run": "forecast",
    "backtest_run": "backtest",
    "daily_advice_generation": "advice",
    "daily_workflow": "monitoring",
    "model_monitoring": "monitoring",
    "jarvis_brief_generation": "monitoring",
    "expert_daily_planning": "monitoring",
    "expert_scoring_review": "monitoring",
}


def latest_run_health_tasks(conn: Any) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT task_name, run_date, status, error, message
        FROM task_logs
        ORDER BY run_date DESC, id DESC
        LIMIT 120
        """
    ).fetchall()
    latest: dict[str, Any] = {}
    for row in rows:
        stage = RUN_HEALTH_TASK_STAGE.get(str(row["task_name"] or ""))
        if stage and stage not in latest:
            latest[stage] = row
    return latest


def _run_health_stage(stage: dict[str, str], counts: dict[str, Any], latest: dict[str, Any], task_summary: Any, task: Any | None) -> dict[str, Any]:
    count = int(counts.get(stage["count_key"]) or 0)
    last_date = latest.get(stage["latest_key"])
    status = "ok" if count > 0 and last_date else "missing"
    label = "正常" if status == "ok" else "缺失"
    task_status = str(task["status"] or "") if task else ""
    if task_status == "failed":
        status, label = "bad", "运行异常"
    elif task_status == "running":
        status, label = "warn", "运行中"
    if stage["key"] == "monitoring" and count > 0:
        failed = int(_safe_get(task_summary, "failed_count") or 0)
        running = int(_safe_get(task_summary, "running_count") or 0)
        if failed:
            status, label = "bad", "运行异常"
        elif running:
            status, label = "warn", "运行中"
        elif status != "bad":
            status, label = "ok", "正常"
    evidence = f"最近 {last_date or '暂无'} · 记录 {count}"
    if task:
        evidence += f" · 任务 {task['task_name']} {task_status or '未知'}"
    return {
        **stage,
        "count": count,
        "last_date": last_date,
        "status": status,
        "status_label": label,
        "evidence": evidence,
    }


def scheduler_health_panel(status: dict[str, Any]) -> str:
    jobs = status.get("jobs", [])
    latest_runs = status.get("latest_runs", {})
    watermarks = status.get("watermarks", [])
    rate_limits = status.get("provider_rate_limits", [])
    today = status.get("today", {})
    latest_success = [run for run in latest_runs.values() if run and run.get("status") == "success"]
    deferred = [run for run in latest_runs.values() if run and run.get("status") == "deferred"]
    failed = [run for run in latest_runs.values() if run and run.get("status") == "failed"]
    active_backoff = [row for row in rate_limits if row.get("backoff_until")]
    summary = stat_grid(
        [
            ("调度任务", len(jobs)),
            ("成功任务", len(latest_success)),
            ("延后任务", len(deferred)),
            ("Provider Backoff", len(active_backoff)),
        ]
    )
    run_rows = [
        {
            "job_key": key,
            "status": run.get("status") if run else "暂无",
            "execution_mode": run.get("execution_mode") if run else "",
            "scheduled_at": run.get("scheduled_at") if run else "",
            "deferred_reason": run.get("deferred_reason") if run else "",
            "updated_counts": json.dumps(run.get("updated_counts", {}), ensure_ascii=False) if run else "{}",
        }
        for key, run in latest_runs.items()
    ]
    health_class = "bad" if failed else ("warn" if deferred or active_backoff else "ok")
    headline = "调度正常" if health_class == "ok" else ("调度延后" if health_class == "warn" else "调度异常")
    panel = f'<div class="notice {health_class}"><strong>系统调度：</strong>{escape(headline)}。市场/资讯增量由本系统调度，不依赖 Codex app automation。</div>'
    panel += summary
    panel += scheduler_today_panel(today)
    panel += collapsible("最近调度运行", table(run_rows, ["job_key", "status", "execution_mode", "scheduled_at", "deferred_reason", "updated_counts"]))
    panel += collapsible("调度 Watermarks", table(watermarks, ["job_key", "provider_key", "source_key", "scope_key", "last_success_cursor", "last_attempted_cursor"]))
    panel += collapsible("Provider Backoff", table(rate_limits, ["provider_key", "backoff_until", "hourly_count", "daily_count", "failure_count", "last_failure_reason"]))
    return panel


def scheduler_today_panel(today: dict[str, Any]) -> str:
    items = today.get("items", [])
    failures = today.get("task_log_failures", [])
    counts = today.get("counts", {})
    status = today.get("overall_status", "ok")
    label = "今日调度正常" if status == "ok" else ("今日调度需关注" if status == "warn" else "今日调度异常")
    cards = stat_grid(
        [
            ("已成功", counts.get("success", 0)),
            ("失败", counts.get("failed", 0)),
            ("延后", counts.get("deferred", 0)),
            ("未跑", counts.get("missed", 0)),
        ]
    )
    rows = [
        {
            "job_key": item["job_key"],
            "status": item["status"],
            "due": f"{item['run_count']}/{item['due_count']}",
            "missed": item["missed_count"],
            "next_expected_at": item.get("next_expected_at") or "",
            "reason": item["reason"],
        }
        for item in items
    ]
    body = f'<div class="notice {escape(status)}"><strong>今日任务：</strong>{escape(label)} · {escape(today.get("date", ""))}</div>'
    body += cards
    body += table(rows, ["job_key", "status", "due", "missed", "next_expected_at", "reason"]) if rows else empty("今天没有调度任务。")
    if failures:
        body += collapsible("今日失败任务日志", table(failures, ["id", "task_name", "run_date", "started_at", "status", "message", "error"]))
    return body


def run_health_panel(stages: list[dict[str, Any]]) -> str:
    cards = "".join(run_health_card(stage) for stage in stages)
    return f'<div class="run-health"><h3>运行健康</h3><div class="run-health-grid">{cards}</div></div>'


def run_health_card(stage: dict[str, Any]) -> str:
    return f"""
    <div class="run-health-card {escape(stage['status'])}">
      <div><span>{escape(stage['label'])}</span><strong>{escape(stage['status_label'])}</strong></div>
      <small>{escape(stage['evidence'])}</small>
      <p>{escape(stage['impact'])}</p>
      <em>恢复提示：{escape(stage['recovery'])}</em>
    </div>
    """


def render_page(title: str, body: str, active_path: str) -> str:
    nav = "".join(
        f'<a class="{"active" if path == active_path else ""}" href="{path}">{label}</a>'
        for path, label in NAV_ITEMS
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · Investment Forecasting</title>
  <style>{CSS}</style>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head>
<body>
  <aside class="sidebar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 36 36" role="img" focusable="false">
          <path class="mark-orbit" d="M7 23c4-9 10-13 22-14" />
          <path class="mark-line" d="M9 24l6-6 5 4 8-10" />
          <circle class="mark-dot" cx="28" cy="12" r="2.4" />
          <text x="10.5" y="25.5">J</text>
        </svg>
      </span>
      <span><strong>贾维斯理财助理</strong><small>本地研究 · 风险边界 · 证据链</small></span>
    </div>
    <nav>{nav}</nav>
  </aside>
  <main>
    <header><h1>{escape(title)}</h1><p>用本地研究数据、模型证据和专家复盘辅助理解市场与风险边界，不承诺收益。</p></header>
    {body}
  </main>
  <script>{JS}</script>
</body>
</html>"""


def section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


PRODUCT_CATEGORIES = {
    "fund": {"key": "fund", "label": "公募基金", "description": "开放式基金、偏股/混合/指数增强等基金产品。"},
    "etf": {"key": "etf", "label": "ETF", "description": "宽基、行业、主题和跨境 ETF。"},
    "index": {"key": "index", "label": "市场指数", "description": "用于观察市场环境和基准走势的指数。"},
    "stock": {"key": "stock", "label": "股票", "description": "A 股个股，用于观察权益资产机会和风险。"},
    "fixed_income_cash": {"key": "fixed_income_cash", "label": "固收/现金代理", "description": "债券、货币、现金管理和低波动代理标的。"},
    "market_indicator": {"key": "market_indicator", "label": "宏观/市场指标", "description": "市场快照和宏观观测，不对应单一可交易资产。"},
    "unknown": {"key": "unknown", "label": "其他资产", "description": "暂未归入主要产品分类的资产。"},
}


def build_category_summaries(conn: Any) -> list[dict[str, Any]]:
    asset_rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, a.asset_type,
               f.feature_date, f.return_20d, f.max_drawdown_60d, f.sharpe_60d,
               p.prediction_date, p.expected_return
        FROM assets a
        LEFT JOIN features_daily f ON f.id = (
            SELECT id FROM features_daily
            WHERE asset_id = a.id
            ORDER BY feature_date DESC
            LIMIT 1
        )
        LEFT JOIN model_predictions p ON p.id = (
            SELECT id FROM model_predictions
            WHERE asset_id = a.id
            ORDER BY prediction_date DESC, horizon_days
            LIMIT 1
        )
        """
    ).fetchall()
    grouped: dict[str, list[Any]] = {}
    for row in asset_rows:
        category = asset_category(row)
        grouped.setdefault(category["key"], []).append(row)

    summaries = []
    for key in ["fund", "etf", "fixed_income_cash", "index", "stock", "market_indicator", "unknown"]:
        category = PRODUCT_CATEGORIES[key]
        if key == "market_indicator":
            macro_count = _count_rows(conn, "macro_observations")
            snapshot_count = _count_rows(conn, "market_snapshots")
            capital_flow_count = _count_rows(conn, "capital_flow_observations")
            latest_macro = _max_value(conn, "macro_observations", "observation_date")
            latest_snapshot = _max_value(conn, "market_snapshots", "snapshot_date")
            latest_capital_flow = _max_value(conn, "capital_flow_observations", "flow_date")
            summaries.append(
                {
                    **category,
                    "count": snapshot_count + macro_count + capital_flow_count,
                    "asset_count": 0,
                    "latest_date": latest_snapshot or latest_macro or latest_capital_flow,
                    "avg_return_20d": None,
                    "avg_drawdown_60d": None,
                    "prediction_count": 0,
                    "href": f"/categories?category={key}",
                }
            )
            continue
        rows = grouped.get(key, [])
        if not rows and key == "unknown":
            continue
        summaries.append(
            {
                **category,
                "count": len(rows),
                "asset_count": len(rows),
                "latest_date": max((row["feature_date"] for row in rows if row["feature_date"]), default=None),
                "avg_return_20d": _average(row["return_20d"] for row in rows),
                "avg_drawdown_60d": _average(row["max_drawdown_60d"] for row in rows),
                "prediction_count": sum(1 for row in rows if row["prediction_date"]),
                "href": f"/categories?category={key}",
            }
        )
    return summaries


def opportunity_filter_panel(selected_type: str, risk: str, preference_label: str) -> str:
    type_options = [
        ("all", "全部"),
        ("fund", "公募基金"),
        ("etf", "ETF"),
        ("stock", "股票"),
        ("index", "指数"),
        ("fixed_income_cash", "固收/现金"),
    ]
    risk_options = [
        ("active", f"当前设置：{preference_label}"),
        ("conservative", "保守"),
        ("balanced", "均衡"),
        ("aggressive", "进取"),
    ]
    return f"""
    <form class="filter-form" method="get" action="/opportunities">
      <label>产品类型<select name="type">{select_options(type_options, selected_type)}</select></label>
      <label>风险偏好<select name="risk">{select_options(risk_options, risk)}</select></label>
      <button type="submit">更新机会池</button>
    </form>
    <p class="muted">机会池只展示已有证据和当前风险画像下的观察方向；排序与解释来自入库预测、风险指标、基金元数据和主题标签。</p>
    """


def opportunity_category_panel(summaries: list[dict[str, Any]], selected_type: str) -> str:
    cards = []
    for item in summaries:
        key = item["key"]
        if key == "market_indicator":
            continue
        active = " active" if key == selected_type else ""
        href = f"/opportunities?type={escape(key)}"
        cards.append(
            f"""
            <a class="category-card{active}" href="{href}">
              <span>{escape(item['label'])}</span>
              <strong>{escape(str(item['asset_count']))}</strong>
              <em>{escape(item['description'])}</em>
              <small>进入后可继续查看预测、主题、基金和数据证据</small>
            </a>
            """
        )
    return '<div class="category-grid">' + "".join(cards) + "</div>" if cards else empty("还没有可展示的资产分类。")


def opportunity_prediction_rows(conn: Any, selected_type: str) -> list[Any]:
    rows = conn.execute(
        """
        SELECT p.id, p.asset_id, a.code, a.name, a.asset_type, p.prediction_date, p.horizon_days,
               p.up_probability, p.expected_return, p.expected_return_low,
               p.expected_return_high, p.downside_risk, p.confidence,
               p.model_version, p.input_window_start, p.input_window_end,
               r.rank_score, r.rank_position, r.rank_count,
               r.same_category_rank, r.same_category_count,
               r.risk_adjusted_score, r.validation_status, r.degraded_reason
        FROM model_predictions p
        LEFT JOIN assets a ON a.id = p.asset_id
        LEFT JOIN model_prediction_reliability r ON r.prediction_id = p.id
        ORDER BY p.prediction_date DESC, a.code, p.horizon_days
        LIMIT 300
        """
    ).fetchall()
    if selected_type == "all":
        return rows
    return [row for row in rows if asset_category(row)["key"] == selected_type]


def opportunity_fund_rows(conn: Any, selected_type: str) -> list[dict[str, Any]]:
    if selected_type not in {"all", "fund"}:
        return []
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, f.feature_date, f.return_20d,
               f.max_drawdown_60d, f.sharpe_60d, f.win_rate_60d, f.market_state,
               i.fund_type, i.manager, i.scale, i.purchase_fee,
               i.management_fee, i.custody_fee, i.fund_company
        FROM assets a
        LEFT JOIN fund_info i ON i.asset_id = a.id
        LEFT JOIN features_daily f ON f.id = (
            SELECT id FROM features_daily
            WHERE asset_id = a.id
            ORDER BY feature_date DESC
            LIMIT 1
        )
        WHERE a.asset_type = 'fund'
        ORDER BY f.return_20d DESC NULLS LAST, a.code
        """
    ).fetchall()
    return [dict(row) for row in rows]


def evidence_hub_links(data_status: dict[str, Any]) -> str:
    counts = data_status["counts"]
    links = [
        ("/predictions", "模型预测", counts["model_predictions"], "候选资产方向、概率、置信度"),
        ("/backtests", "回测评分", counts.get("backtest_results", 0), "历史命中率、误差和模型健康"),
        ("/market", "市场/资金流", counts["market_snapshots"], "市场快照、宏观、资金流证据"),
        ("/data", "数据与曲线", counts["price_daily"], "价格、净值、涨幅曲线和特征"),
        ("/timeline", "研究时间线", counts.get("task_logs", 0), "每次研究运行和缺失阶段"),
    ]
    cards = "".join(evidence_chip(label, value, href, hint) for href, label, value, hint in links)
    return '<div class="evidence-chip-grid">' + cards + "</div>"


def asset_category(row: Any) -> dict[str, str]:
    if not row:
        return PRODUCT_CATEGORIES["unknown"]
    asset_type = str(_safe_get(row, "asset_type") or "").lower()
    name = str(_safe_get(row, "name") or "")
    code = str(_safe_get(row, "code") or "")
    if asset_type in {"etf", "fund"} and _is_fixed_income_or_cash_proxy(code, name):
        return PRODUCT_CATEGORIES["fixed_income_cash"]
    if asset_type in PRODUCT_CATEGORIES:
        return PRODUCT_CATEGORIES[asset_type]
    return PRODUCT_CATEGORIES["unknown"]


def _is_fixed_income_or_cash_proxy(code: str, name: str) -> bool:
    text = f"{code} {name}".lower()
    keywords = ["债", "国债", "短债", "可转债", "货币", "现金", "日利", "同业存单", "存单", "bond", "cash"]
    return code.startswith("511") or any(keyword.lower() in text for keyword in keywords)


def category_assets(conn: Any, category_key: str, limit: int = 120) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, a.asset_type, a.market,
               f.feature_date, f.return_20d, f.max_drawdown_60d, f.sharpe_60d,
               f.market_state,
               p.prediction_date, p.expected_return, p.up_probability, p.confidence
        FROM assets a
        LEFT JOIN features_daily f ON f.id = (
            SELECT id FROM features_daily
            WHERE asset_id = a.id
            ORDER BY feature_date DESC
            LIMIT 1
        )
        LEFT JOIN model_predictions p ON p.id = (
            SELECT id FROM model_predictions
            WHERE asset_id = a.id
            ORDER BY prediction_date DESC, horizon_days
            LIMIT 1
        )
        ORDER BY f.return_20d DESC NULLS LAST, a.asset_type, a.code
        """
    ).fetchall()
    filtered = [
        dict(row) | {"category": asset_category(row)["label"], "theme": asset_theme(row)["label"]}
        for row in rows
        if asset_category(row)["key"] == category_key
    ]
    return filtered[:limit]


def category_nav_panel(summaries: list[dict[str, Any]], compact: bool = False) -> str:
    if not summaries:
        return empty("还没有可分类的资产。")
    cards = "".join(category_card(item, compact=compact) for item in summaries)
    return f'<div class="category-grid {"compact" if compact else ""}">{cards}</div>'


def category_card(item: dict[str, Any], compact: bool = False) -> str:
    metrics = "" if compact else (
        f'<small>最新 {escape(item["latest_date"] or "暂无")} · 20日均值 {market_percent(item["avg_return_20d"])} · 回撤 {market_percent(item["avg_drawdown_60d"])}</small>'
    )
    return f"""
    <a class="category-card" href="{escape(item['href'])}">
      <span>{escape(item['label'])}</span>
      <strong>{escape(item['count'])}</strong>
      <em>{escape(item['description'])}</em>
      {metrics}
    </a>
    """


def category_summary_panel(item: dict[str, Any]) -> str:
    return (
        stat_grid(
            [
                ("分类", item["label"]),
                ("资产/观测", item["count"]),
                ("预测覆盖", item["prediction_count"]),
                ("最新日期", item["latest_date"] or "暂无"),
                ("20日收益均值", item["avg_return_20d"]),
                ("60日回撤均值", item["avg_drawdown_60d"]),
            ]
        )
        + f'<p class="muted">{escape(item["description"])}</p>'
    )


def category_asset_table(category: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if category["key"] == "market_indicator":
        return f'<p class="muted">宏观和市场快照已拆成独立指标页。</p><p><a class="preset-link" href="/market">查看市场指标</a></p>'
    if not rows:
        return empty(f"当前没有归入{category['label']}的资产。")
    linked = []
    for row in rows:
        linked.append(
            {
                **row,
                "code": f'<a href="/data?asset_id={row["id"]}">{escape(row["code"])}</a>',
            }
        )
    return table(
        linked,
        ["code", "name", "asset_type", "theme", "feature_date", "return_20d", "max_drawdown_60d", "sharpe_60d", "market_state", "expected_return", "up_probability", "confidence"],
        escape_cells=False,
    )


def asset_theme(row: Any) -> dict[str, str]:
    return classify_asset_theme(
        code=_safe_get(row, "code"),
        name=_safe_get(row, "name"),
        asset_type=_safe_get(row, "asset_type"),
        fund_type=_safe_get(row, "fund_type"),
    )


def theme_asset_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, a.asset_type, a.market,
               i.fund_type,
               f.feature_date, f.return_20d, f.max_drawdown_60d, f.sharpe_60d,
               f.market_state,
               p.prediction_date, p.expected_return, p.up_probability, p.confidence
        FROM assets a
        LEFT JOIN fund_info i ON i.asset_id = a.id
        LEFT JOIN features_daily f ON f.id = (
            SELECT id FROM features_daily
            WHERE asset_id = a.id
            ORDER BY feature_date DESC
            LIMIT 1
        )
        LEFT JOIN model_predictions p ON p.id = (
            SELECT id FROM model_predictions
            WHERE asset_id = a.id
            ORDER BY prediction_date DESC, horizon_days
            LIMIT 1
        )
        ORDER BY f.return_20d DESC NULLS LAST, a.asset_type, a.code
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        theme = asset_theme(item)
        category = asset_category(item)
        result.append({**item, "theme_key": theme["key"], "theme_label": theme["label"], "theme_reason": theme["reason"], "category": category["label"]})
    return result


def build_theme_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["theme_key"], []).append(row)
    summaries = []
    for key, items in grouped.items():
        summaries.append(
            {
                "theme_key": key,
                "theme_label": items[0]["theme_label"],
                "asset_count": len(items),
                "prediction_count": sum(1 for item in items if item.get("prediction_date")),
                "latest_date": max((item["feature_date"] for item in items if item.get("feature_date")), default=None),
                "avg_return_20d": _average(item.get("return_20d") for item in items),
                "avg_drawdown_60d": _average(item.get("max_drawdown_60d") for item in items),
                "avg_expected_return": _average(item.get("expected_return") for item in items),
                "best_asset": _best_theme_asset(items),
                "href": f"/themes?theme={key}",
            }
        )
    return sorted(summaries, key=lambda item: (item["avg_expected_return"] is not None, item["avg_expected_return"] or item["avg_return_20d"] or -999, item["asset_count"]), reverse=True)


def _best_theme_asset(rows: list[dict[str, Any]]) -> str:
    scored = [row for row in rows if row.get("return_20d") is not None]
    if not scored:
        return "暂无"
    best = max(scored, key=lambda item: float(item.get("return_20d") or 0.0))
    return f"{best['code']} {best['name']}"


def theme_overview_panel(summaries: list[dict[str, Any]], selected: dict[str, Any] | None) -> str:
    if not summaries:
        return empty("还没有可聚合的主题配置。")
    selected_key = selected["theme_key"] if selected else ""
    cards = "".join(theme_card(item, selected_key) for item in summaries)
    return '<div class="category-grid">' + cards + "</div>"


def theme_card(item: dict[str, Any], selected_key: str = "") -> str:
    active = " active" if item["theme_key"] == selected_key else ""
    return f"""
    <a class="category-card{active}" href="{escape(item['href'])}">
      <span>{escape(item['theme_label'])}</span>
      <strong>{escape(item['asset_count'])}</strong>
      <em>预测覆盖 {escape(item['prediction_count'])} · 最新 {escape(item['latest_date'] or '暂无')}</em>
      <small>20日均值 {market_percent(item['avg_return_20d'])} · 预期 {market_percent(item['avg_expected_return'])} · 回撤 {market_percent(item['avg_drawdown_60d'])}</small>
    </a>
    """


def theme_asset_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("当前主题没有可展示资产。")
    display_rows = []
    for row in sorted(rows, key=lambda item: (item.get("expected_return") is not None, item.get("expected_return") or item.get("return_20d") or -999), reverse=True)[:80]:
        display_rows.append(
            {
                **row,
                "code": f'<a href="/data?asset_id={row["id"]}">{escape(row["code"])}</a>',
                "theme_reason": row.get("theme_reason") or "暂无",
            }
        )
    return table(
        display_rows,
        ["code", "name", "asset_type", "category", "feature_date", "return_20d", "max_drawdown_60d", "expected_return", "up_probability", "confidence", "theme_reason"],
        escape_cells=False,
    )


def market_snapshot_panel(row: Any | None) -> str:
    if row is None:
        return empty("还没有市场快照；运行 `investment-forecasting market snapshot --db data/investment_forecasting.sqlite3 --date YYYYMMDD` 后会显示。")
    details = _json_payload(row["details_json"])
    assets = details.get("assets", []) if isinstance(details, dict) else []
    summary = stat_grid(
        [
            ("快照日期", row["snapshot_date"]),
            ("市场情绪", _market_sentiment_label(row["sentiment"])),
            ("指数收益趋势", row["index_trend"]),
            ("上涨宽度", percent(row["breadth"])),
            ("成交热度", row["liquidity_heat"]),
            ("股债强弱", row["stock_bond_proxy"]),
        ]
    )
    movers = market_snapshot_asset_movers(assets)
    component_text = ""
    components = details.get("components", {}) if isinstance(details, dict) else {}
    if components:
        component_text = '<p class="muted">口径：' + escape("；".join(str(value) for value in components.values())) + "</p>"
    return summary + component_text + movers


def market_snapshot_asset_movers(assets: list[Any]) -> str:
    rows = []
    for item in assets:
        if not isinstance(item, dict) or item.get("return_20d") is None:
            continue
        rows.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "asset_type": item.get("asset_type"),
                "theme": asset_theme(item)["label"],
                "feature_date": item.get("feature_date"),
                "return_20d": item.get("return_20d"),
                "max_drawdown_60d": item.get("max_drawdown_60d"),
                "market_state": item.get("market_state"),
            }
        )
    if not rows:
        return empty("市场快照没有可展示的资产分项。")
    strongest = sorted(rows, key=lambda item: float(item["return_20d"]), reverse=True)[:5]
    weakest = sorted(rows, key=lambda item: float(item["return_20d"]))[:5]
    return (
        "<h3>强弱分布</h3>"
        + table(strongest + weakest, ["code", "name", "asset_type", "theme", "feature_date", "return_20d", "max_drawdown_60d", "market_state"])
    )


def macro_latest_panel(rows: list[Any]) -> str:
    if not rows:
        return empty("还没有宏观观测；运行 `investment-forecasting ingest macro --db data/investment_forecasting.sqlite3 --series DGS10,T10YIE,DTWEXBGS` 后会显示。")
    display_rows = [
        {
            "series_id": row["series_id"],
            "label": macro_series_label(row["series_id"]),
            "observation_date": row["observation_date"],
            "value": row["value"],
            "source": row["source"],
        }
        for row in rows
    ]
    return table(display_rows, ["series_id", "label", "observation_date", "value", "source"])


def capital_flow_panel(rows: list[Any]) -> str:
    if not rows:
        return empty("还没有资金流观测；运行 `investment-forecasting ingest capital-flow --db data/investment_forecasting.sqlite3 --scope stock --asset-codes 600519` 后会显示。")
    display_rows = [
        {
            "flow_date": row["flow_date"],
            "scope": capital_flow_scope_label(row["scope"]),
            "subject": row["subject_name"],
            "code": row["subject_code"],
            "main_net_inflow": row["main_net_inflow"],
            "main_net_inflow_pct": row["main_net_inflow_pct"],
            "super_large_net_inflow": row["super_large_net_inflow"],
            "large_net_inflow": row["large_net_inflow"],
            "medium_net_inflow": row["medium_net_inflow"],
            "small_net_inflow": row["small_net_inflow"],
            "pct_change": row["pct_change"],
            "source": row["source"],
        }
        for row in rows
    ]
    summary = stat_grid(
        [
            ("观测对象", len(rows)),
            ("最近日期", rows[0]["flow_date"]),
            ("主力净流入对象", sum(1 for row in rows if (row["main_net_inflow"] or 0) > 0)),
            ("主力净流出对象", sum(1 for row in rows if (row["main_net_inflow"] or 0) < 0)),
        ]
    )
    return summary + table(
        display_rows,
        [
            "flow_date",
            "scope",
            "subject",
            "code",
            "main_net_inflow",
            "main_net_inflow_pct",
            "super_large_net_inflow",
            "large_net_inflow",
            "medium_net_inflow",
            "small_net_inflow",
            "pct_change",
            "source",
        ],
    )


def market_history_panel(snapshots: list[Any], macro_history: list[Any], capital_flow_history: list[Any] | None = None) -> str:
    capital_flow_history = capital_flow_history or []
    if not snapshots and not macro_history and not capital_flow_history:
        return empty("还没有市场或宏观历史记录。")
    body = ""
    if snapshots:
        body += collapsible("市场快照历史", table(snapshots, ["snapshot_date", "sentiment", "index_trend", "breadth", "liquidity_heat", "stock_bond_proxy", "source"]))
    if macro_history:
        body += collapsible("宏观观测历史", table(macro_history, ["series_id", "observation_date", "value", "source"]))
    if capital_flow_history:
        body += collapsible(
            "资金流历史",
            table(
                capital_flow_history,
                [
                    "flow_date",
                    "scope",
                    "subject_code",
                    "subject_name",
                    "main_net_inflow",
                    "main_net_inflow_pct",
                    "super_large_net_inflow",
                    "large_net_inflow",
                    "medium_net_inflow",
                    "small_net_inflow",
                    "source",
                ],
            ),
        )
    return body


def macro_series_label(series_id: Any) -> str:
    labels = {
        "DGS10": "美国10年期国债收益率",
        "T10YIE": "美国10年通胀预期",
        "DTWEXBGS": "美元广义指数",
    }
    return labels.get(str(series_id), "宏观序列")


def capital_flow_scope_label(scope: Any) -> str:
    labels = {
        "market": "市场",
        "stock": "个股",
        "sector": "行业",
        "fund": "基金",
    }
    return labels.get(str(scope), str(scope))


def _json_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


FUND_PRESETS = {
    "conservative": {
        "label": "保守",
        "description": "优先低回撤、可解释、费用数据完整的基金。",
        "max_drawdown_60d_min": -0.08,
        "min_win_rate_60d": 0.45,
        "has_fee": "1",
    },
    "balanced": {
        "label": "均衡",
        "description": "在收益、回撤和胜率之间做折中。",
        "min_return_20d": 0.0,
        "max_drawdown_60d_min": -0.15,
        "min_win_rate_60d": 0.4,
    },
    "aggressive": {
        "label": "激进",
        "description": "优先近期弹性和较高 Sharpe，允许更高波动。",
        "min_return_20d": 0.08,
        "min_sharpe_60d": 1.0,
    },
}


def fund_filters_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    preset = str(_first_query_value(query, "preset", "") or "")
    filters: dict[str, Any] = {"preset": preset}
    if preset in FUND_PRESETS:
        filters.update(FUND_PRESETS[preset])
    for key in [
        "fund_type",
        "theme",
        "manager",
        "market_state",
        "has_fee",
        "min_scale",
        "max_scale",
        "min_return_20d",
        "max_drawdown_60d_min",
        "min_sharpe_60d",
        "min_win_rate_60d",
    ]:
        value = _first_query_value(query, key)
        if value not in (None, ""):
            filters[key] = value
    for key in ["min_scale", "max_scale", "min_return_20d", "max_drawdown_60d_min", "min_sharpe_60d", "min_win_rate_60d"]:
        if key in filters:
            filters[key] = _to_float(filters[key])
    return filters


def filter_funds(rows: Any, filters: dict[str, Any]) -> list[dict[str, Any]]:
    filtered = []
    for row in rows:
        item = dict(row)
        theme = asset_theme(item)
        item["theme_key"] = theme["key"]
        item["theme"] = theme["label"]
        item["theme_reason"] = theme["reason"]
        if filters.get("fund_type") and filters["fund_type"] not in str(item.get("fund_type") or ""):
            continue
        if filters.get("theme") and filters["theme"] != item["theme_key"]:
            continue
        if filters.get("manager") and filters["manager"] not in str(item.get("manager") or ""):
            continue
        if filters.get("market_state") and filters["market_state"] != str(item.get("market_state") or ""):
            continue
        if filters.get("has_fee") == "1" and item.get("purchase_fee") is None:
            continue
        if not _passes_min(item.get("scale"), filters.get("min_scale")):
            continue
        if not _passes_max(item.get("scale"), filters.get("max_scale")):
            continue
        if not _passes_min(item.get("return_20d"), filters.get("min_return_20d")):
            continue
        if not _passes_min(item.get("max_drawdown_60d"), filters.get("max_drawdown_60d_min")):
            continue
        if not _passes_min(item.get("sharpe_60d"), filters.get("min_sharpe_60d")):
            continue
        if not _passes_min(item.get("win_rate_60d"), filters.get("min_win_rate_60d")):
            continue
        item["explanation"] = fund_suitability_explanation(item, filters)
        filtered.append(item)
    return filtered


def fund_filter_panel(filters: dict[str, Any], rows: Any, active_preference: Any) -> str:
    fund_types = _distinct_non_empty(row["fund_type"] for row in rows)
    managers = _distinct_non_empty(row["manager"] for row in rows)
    states = _distinct_non_empty(row["market_state"] for row in rows)
    themes = theme_options()
    preset_links = "".join(
        f'<a class="preset-link {"active" if filters.get("preset") == key else ""}" href="/funds?preset={key}">{escape(preset["label"])}</a>'
        for key, preset in FUND_PRESETS.items()
    )
    preference_hint = ""
    if active_preference:
        preference_hint = f'<p class="muted">当前活跃偏好：{escape(active_preference["profile_name"])} · {escape(active_preference["risk_profile"])} · 关注 {escape(active_preference["investment_horizon_days"])} 天。</p>'
    return section(
        "筛选条件",
        f"""
        <div class="preset-bar">{preset_links}<a class="preset-link" href="/funds">清除</a></div>
        {preference_hint}
        <form class="filter-form" method="get" action="/funds">
          <label>基金类型<select name="fund_type"><option value="">全部</option>{select_options(fund_types, filters.get("fund_type"))}</select></label>
          <label>行业/主题<select name="theme"><option value="">全部</option>{select_options([(item["key"], item["label"]) for item in themes], filters.get("theme"))}</select></label>
          <label>基金经理<select name="manager"><option value="">全部</option>{select_options(managers, filters.get("manager"))}</select></label>
          <label>市场状态<select name="market_state"><option value="">全部</option>{select_options(states, filters.get("market_state"))}</select></label>
          <label>最小规模/亿<input name="min_scale" value="{escape(_filter_value(filters, 'min_scale'))}"></label>
          <label>最大规模/亿<input name="max_scale" value="{escape(_filter_value(filters, 'max_scale'))}"></label>
          <label>最小20日收益<input name="min_return_20d" value="{escape(_filter_value(filters, 'min_return_20d'))}"></label>
          <label>60日回撤不低于<input name="max_drawdown_60d_min" value="{escape(_filter_value(filters, 'max_drawdown_60d_min'))}"></label>
          <label>最小Sharpe<input name="min_sharpe_60d" value="{escape(_filter_value(filters, 'min_sharpe_60d'))}"></label>
          <label>最小胜率<input name="min_win_rate_60d" value="{escape(_filter_value(filters, 'min_win_rate_60d'))}"></label>
          <label class="checkbox"><input type="checkbox" name="has_fee" value="1" {"checked" if filters.get("has_fee") == "1" else ""}> 仅看有费率数据</label>
          <button type="submit">应用筛选</button>
        </form>
        """,
    )


def fund_results_panel(filtered: list[dict[str, Any]], all_rows: Any, filters: dict[str, Any]) -> str:
    total = len(list(all_rows))
    explanation = f"当前条件命中 {len(filtered)} / {total} 只基金。"
    if filters.get("preset") in FUND_PRESETS:
        preset = FUND_PRESETS[filters["preset"]]
        explanation += f" {preset['label']}预设：{preset['description']}"
    if not filtered:
        return f'<p class="muted">{escape(explanation)}</p>' + empty("没有基金满足当前筛选；可以放宽收益、回撤、规模或费率条件。")
    top = fund_display_rows(filtered[:60])
    return f'<p class="muted">{escape(explanation)}</p>' + table(top, ["code", "name", "theme", "fund_type", "manager", "scale", "purchase_fee", "return_20d", "max_drawdown_60d", "sharpe_60d", "win_rate_60d", "market_state", "explanation"], escape_cells=False)


def fund_holdings_panel(rows: list[Any], fund_ids: set[int] | None = None) -> str:
    if fund_ids is not None:
        rows = [row for row in rows if int(row["fund_asset_id"]) in fund_ids]
    if not rows:
        return empty("还没有基金持仓数据；运行 `investment-forecasting ingest fund-holdings --db data/investment_forecasting.sqlite3 --fund-codes 000001 --year 2024` 后会显示。")
    grouped_funds = {row["fund_asset_id"] for row in rows}
    latest_period = max(row["report_period"] for row in rows if row["report_period"])
    total_weight = sum(float(row["weight_pct"] or 0) for row in rows)
    summary = stat_grid(
        [
            ("覆盖基金", len(grouped_funds)),
            ("持仓行数", len(rows)),
            ("最新报告期", latest_period),
            ("样本权重合计", total_weight),
        ]
    )
    exposure = fund_holding_theme_exposure_panel(rows)
    display = [
        {
            "fund": f'{row["fund_code"]} {row["fund_name"]}',
            "report_period": row["report_period"],
            "rank": row["rank"],
            "holding": row["holding_name"],
            "holding_code": row["holding_code"],
            "weight_pct": row["weight_pct"],
            "shares": row["shares"],
            "market_value": row["market_value"],
            "linked": "已匹配资产" if row["holding_asset_id"] else "未入库资产",
            "source": row["source"],
        }
        for row in rows[:80]
    ]
    return summary + exposure + table(display, ["fund", "report_period", "rank", "holding", "holding_code", "weight_pct", "shares", "market_value", "linked", "source"])


def fund_holding_theme_exposure_panel(rows: list[Any]) -> str:
    exposures = fund_holding_theme_exposure(rows)
    if not exposures:
        return empty("持仓主题暴露暂不可计算。")
    display = [
        {
            "theme": f'<a href="/themes?theme={escape(item["theme_key"])}">{escape(item["theme"])}</a>',
            "weight": escape(plain_percent(item["weight"])),
            "funds": item["fund_count"],
            "holdings": item["holding_count"],
            "latest_period": escape(item["latest_period"] or "暂无"),
            "top_holdings": escape(item["top_holdings"]),
            "reason": escape(item["reason"]),
        }
        for item in exposures
    ]
    return "<h3>持仓穿透主题暴露</h3>" + table(display, ["theme", "weight", "funds", "holdings", "latest_period", "top_holdings", "reason"], escape_cells=False)


def fund_holding_theme_exposure(rows: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        weight = _to_float(row["weight_pct"]) or 0.0
        theme = classify_asset_theme(
            code=row["linked_holding_code"] or row["holding_code"],
            name=row["linked_holding_name"] or row["holding_name"],
            asset_type=row["linked_holding_asset_type"] or row["holding_type"],
        )
        group = grouped.setdefault(
            theme["key"],
            {
                "theme_key": theme["key"],
                "theme": theme["label"],
                "reason": theme["reason"],
                "weight": 0.0,
                "fund_ids": set(),
                "holding_count": 0,
                "latest_period": "",
                "holdings": [],
            },
        )
        group["weight"] += weight
        group["fund_ids"].add(row["fund_asset_id"])
        group["holding_count"] += 1
        if row["report_period"] and str(row["report_period"]) > str(group["latest_period"] or ""):
            group["latest_period"] = row["report_period"]
        group["holdings"].append((weight, row["holding_name"] or row["holding_code"] or "未知持仓"))
    result = []
    for item in grouped.values():
        top = sorted(item["holdings"], key=lambda holding: holding[0], reverse=True)[:3]
        result.append(
            {
                "theme_key": item["theme_key"],
                "theme": item["theme"],
                "reason": item["reason"],
                "weight": item["weight"],
                "fund_count": len(item["fund_ids"]),
                "holding_count": item["holding_count"],
                "latest_period": item["latest_period"],
                "top_holdings": "、".join(str(name) for _, name in top),
            }
        )
    return sorted(result, key=lambda item: item["weight"], reverse=True)


def fund_display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    display = []
    for row in rows:
        display.append(
            {
                **row,
                "code": f'<a href="/data?asset_id={row["id"]}">{escape(row["code"])}</a>',
                "fund_type": escape(row.get("fund_type") or "基金类型待补充"),
                "theme": escape(row.get("theme") or asset_theme(row)["label"]),
                "manager": escape(row.get("manager") or "基金经理待补充"),
                "scale": row.get("scale") if row.get("scale") is not None else "规模待补充",
                "purchase_fee": row.get("purchase_fee") if row.get("purchase_fee") is not None else "费率待补充",
                "explanation": escape(row.get("explanation") or fund_suitability_explanation(row, {})),
            }
        )
    return display


def fund_suitability_explanation(row: dict[str, Any], filters: dict[str, Any]) -> str:
    notes = []
    if row.get("return_20d") is not None:
        notes.append(f"20日收益 {plain_percent(row['return_20d'])}")
    else:
        notes.append("20日收益样本不足")
    if row.get("max_drawdown_60d") is not None:
        notes.append(f"60日回撤 {plain_percent(row['max_drawdown_60d'])}")
    else:
        notes.append("回撤数据待补充")
    if row.get("sharpe_60d") is not None:
        notes.append(f"Sharpe {format_stat(row['sharpe_60d'])}")
    if row.get("purchase_fee") is None:
        notes.append("费率数据待补充")
    if filters.get("preset") in FUND_PRESETS:
        notes.append(f"匹配{FUND_PRESETS[filters['preset']]['label']}预设")
    return "；".join(notes)


def select_options(values: list[Any], selected: Any) -> str:
    options = []
    for item in values:
        value, label = item if isinstance(item, tuple) else (item, item)
        options.append(f'<option value="{escape(value)}" {"selected" if value == selected else ""}>{escape(label)}</option>')
    return "".join(options)


def _distinct_non_empty(values: Any) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})


def _filter_value(filters: dict[str, Any], key: str) -> str:
    value = filters.get(key)
    if value is None:
        return ""
    return str(value)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _passes_min(value: Any, minimum: float | None) -> bool:
    if minimum is None:
        return True
    if value is None:
        return False
    return float(value) >= minimum


def _passes_max(value: Any, maximum: float | None) -> bool:
    if maximum is None:
        return True
    if value is None:
        return False
    return float(value) <= maximum


def selected_asset_summary(asset: Any, prediction: Any, category: dict[str, str]) -> str:
    if not asset:
        return empty("还没有可查看的资产。")
    theme = asset_theme(asset)
    prediction_text = "暂无预测"
    if prediction:
        prediction_text = f"{prediction['horizon_days']}日 {plain_percent(prediction['expected_return'])} / 上涨 {plain_percent(prediction['up_probability'])}"
    return stat_grid(
        [
            ("代码", asset["code"]),
            ("名称", asset["name"]),
            ("分类", category["label"]),
            ("主题", theme["label"]),
            ("最新指标", asset["feature_date"] or "暂无"),
            ("20日收益", asset["return_20d"]),
            ("60日回撤", asset["max_drawdown_60d"]),
            ("夏普", asset["sharpe_60d"]),
            ("市场状态", asset["market_state"] or "暂无"),
            ("最新预测", prediction_text),
        ]
    ) + f'<p class="muted">主题识别：{escape(theme["reason"])}</p>'


def category_context_panel(category: dict[str, str], peers: list[dict[str, Any]]) -> str:
    rows = [
        {
            **row,
            "code": f'<a href="/data?asset_id={row["id"]}">{escape(row["code"])}</a>',
        }
        for row in peers
    ]
    content = f'<p class="muted">当前分类：<a href="/categories?category={escape(category["key"])}">{escape(category["label"])}</a>。{escape(category["description"])}</p>'
    content += table(rows, ["code", "name", "theme", "return_20d", "max_drawdown_60d", "expected_return", "confidence"], escape_cells=False) if rows else empty("当前分类暂无同类资产。")
    return '<div class="category-context">' + content + "</div>"


def collapsible(title: str, body: str) -> str:
    return f'<details class="technical-details"><summary>{escape(title)}</summary>{body}</details>'


def _average(values: Any) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def database_status(conn: Any, db_path: Path) -> dict[str, Any]:
    counts = {
        "assets": _count_rows(conn, "assets"),
        "price_daily": _count_rows(conn, "price_daily"),
        "fund_holdings": _count_rows(conn, "fund_holdings"),
        "features_daily": _count_rows(conn, "features_daily"),
        "model_predictions": _count_rows(conn, "model_predictions"),
        "daily_advice": _count_rows(conn, "daily_advice"),
        "market_snapshots": _count_rows(conn, "market_snapshots"),
        "macro_observations": _count_rows(conn, "macro_observations"),
        "capital_flow_observations": _count_rows(conn, "capital_flow_observations"),
        "backtest_results": _count_rows(conn, "backtest_results"),
        "task_logs": _count_rows(conn, "task_logs"),
    }
    latest = {
        "price_date": _max_value(conn, "price_daily", "trade_date"),
        "feature_date": _max_value(conn, "features_daily", "feature_date"),
        "prediction_date": _max_value(conn, "model_predictions", "prediction_date"),
        "advice_date": _max_value(conn, "daily_advice", "advice_date"),
        "capital_flow_date": _max_value(conn, "capital_flow_observations", "flow_date"),
        "fund_holding_period": _max_value(conn, "fund_holdings", "report_period"),
    }
    return {"db_path": str(db_path), "counts": counts, "latest": latest}


def data_status_panel(status: dict[str, Any]) -> str:
    counts = status["counts"]
    latest = status["latest"]
    summary = stat_grid(
        [
            ("资产", counts["assets"]),
            ("行情/净值", counts["price_daily"]),
            ("基金持仓", counts["fund_holdings"]),
            ("预测", counts["model_predictions"]),
            ("每日建议", counts["daily_advice"]),
            ("资金流", counts["capital_flow_observations"]),
            ("最新行情", latest["price_date"] or "暂无"),
            ("最新持仓", latest["fund_holding_period"] or "暂无"),
            ("最新资金流", latest["capital_flow_date"] or "暂无"),
            ("最新建议", latest["advice_date"] or "暂无"),
        ]
    )
    details = f'<p class="muted">当前数据库：<code>{escape(status["db_path"])}</code></p>'
    if counts["assets"] == 0 or counts["price_daily"] == 0:
        details += empty("当前服务连接的数据库没有资产或行情数据；请先运行采集命令，或检查重启脚本使用的 DB_PATH。")
    return summary + details


def build_timeline_rows(conn: Any, limit: int = 12) -> list[dict[str, Any]]:
    dates = [
        row["run_date"]
        for row in conn.execute(
            """
            SELECT run_date
            FROM (
                SELECT advice_date AS run_date FROM daily_advice
                UNION
                SELECT snapshot_date AS run_date FROM market_snapshots
                UNION
                SELECT flow_date AS run_date FROM capital_flow_observations
                UNION
                SELECT prediction_date AS run_date FROM model_predictions
                UNION
                SELECT end_date AS run_date FROM backtest_runs
                UNION
                SELECT run_date AS run_date FROM task_logs
            )
            WHERE run_date IS NOT NULL AND run_date != ''
            ORDER BY run_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    ]
    rows = [_timeline_row(conn, run_date) for run_date in reversed(dates)]
    previous: dict[str, Any] | None = None
    for row in rows:
        row["changes"] = timeline_changes(row, previous)
        previous = row
    return list(reversed(rows))


def _timeline_row(conn: Any, run_date: str) -> dict[str, Any]:
    advice = conn.execute(
        """
        SELECT id, advice_date, risk_level, model_version, overall_score
        FROM daily_advice
        WHERE advice_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (run_date,),
    ).fetchone()
    market = conn.execute(
        """
        SELECT id, snapshot_date, sentiment, breadth, liquidity_heat
        FROM market_snapshots
        WHERE snapshot_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (run_date,),
    ).fetchone()
    predictions = conn.execute(
        """
        SELECT COUNT(*) AS count,
               AVG(expected_return) AS avg_expected_return,
               AVG(confidence) AS avg_confidence
        FROM model_predictions
        WHERE prediction_date = ?
        """,
        (run_date,),
    ).fetchone()
    backtests = conn.execute(
        """
        SELECT COUNT(*) AS run_count,
               AVG(json_extract(metrics_json, '$.mean_overall_score')) AS mean_overall_score,
               SUM(json_extract(metrics_json, '$.count')) AS result_count
        FROM backtest_runs
        WHERE end_date = ?
        """,
        (run_date,),
    ).fetchone()
    tasks = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
               SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count
        FROM task_logs
        WHERE run_date = ?
        """,
        (run_date,),
    ).fetchone()
    return {
        "run_date": run_date,
        "advice": dict(advice) if advice else None,
        "market": dict(market) if market else None,
        "predictions": dict(predictions) if predictions else {"count": 0},
        "backtests": dict(backtests) if backtests else {"run_count": 0},
        "tasks": dict(tasks) if tasks else {"total": 0},
    }


def timeline_changes(row: dict[str, Any], previous: dict[str, Any] | None) -> str:
    if previous is None:
        return "首次记录，作为后续变化基线。"
    changes = []
    current_sentiment = (row.get("market") or {}).get("sentiment")
    previous_sentiment = (previous.get("market") or {}).get("sentiment")
    if current_sentiment and previous_sentiment and current_sentiment != previous_sentiment:
        changes.append(f"市场情绪 {previous_sentiment} -> {current_sentiment}")
    current_predictions = int((row.get("predictions") or {}).get("count") or 0)
    previous_predictions = int((previous.get("predictions") or {}).get("count") or 0)
    if current_predictions != previous_predictions:
        sign = "+" if current_predictions > previous_predictions else ""
        changes.append(f"预测覆盖 {sign}{current_predictions - previous_predictions}")
    current_score = (row.get("advice") or {}).get("overall_score")
    previous_score = (previous.get("advice") or {}).get("overall_score")
    if current_score is not None and previous_score is not None:
        delta = float(current_score) - float(previous_score)
        if abs(delta) >= 0.01:
            changes.append(f"建议综合分 {delta:+.2f}")
    current_failed = int((row.get("tasks") or {}).get("failed_count") or 0)
    previous_failed = int((previous.get("tasks") or {}).get("failed_count") or 0)
    if current_failed != previous_failed:
        sign = "+" if current_failed > previous_failed else ""
        changes.append(f"失败任务 {sign}{current_failed - previous_failed}")
    return "；".join(changes) if changes else "关键指标较上一记录稳定。"


def timeline_preview(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("还没有可串联的研究记录；运行每日流程后会在这里看到建议、预测、回测和任务健康。")
    return timeline_panel(rows[:3], compact=True) + '<p class="muted"><a href="/timeline">查看完整研究时间线</a></p>'


def timeline_panel(rows: list[dict[str, Any]], compact: bool = False) -> str:
    if not rows:
        return empty("还没有研究运行记录；缺少建议、预测、回测或任务日志时会在这里显示恢复提示。")
    cards = "".join(timeline_card(row) for row in rows)
    return f'<div class="timeline {"compact" if compact else ""}">{cards}</div>'


def timeline_card(row: dict[str, Any]) -> str:
    run_date = row["run_date"]
    return f"""
    <article class="timeline-card">
      <div class="timeline-date">
        <strong>{escape(run_date)}</strong>
        <span>{escape(row['changes'])}</span>
      </div>
      <div class="timeline-grid">
        {timeline_advice_cell(row)}
        {timeline_market_cell(row)}
        {timeline_prediction_cell(row)}
        {timeline_backtest_cell(row)}
        {timeline_task_cell(row)}
      </div>
    </article>
    """


def timeline_advice_cell(row: dict[str, Any]) -> str:
    advice = row.get("advice")
    if not advice:
        return timeline_state("missing", "每日建议", "缺失", "无法形成当天行动口径；运行 advice generate。")
    content = (
        f'<a href="/advice?advice_id={advice["id"]}">{escape(advice["risk_level"])}</a>'
        f'<small>综合分 {escape(format_stat(advice["overall_score"]))} · {escape(advice["model_version"] or "")}</small>'
    )
    return timeline_state("ok", "每日建议", content, "可追溯到建议详情。", escape_content=False)


def timeline_market_cell(row: dict[str, Any]) -> str:
    market = row.get("market")
    if not market:
        return timeline_state("missing", "市场快照", "缺失", "建议缺少市场宽度/情绪上下文；运行 market snapshot。")
    content = f'{escape(market["sentiment"])}<small>宽度 {escape(percent(market["breadth"]))} · 热度 {escape(format_stat(market["liquidity_heat"]))}</small>'
    return timeline_state("ok", "市场快照", content, "市场环境已入库。", escape_content=False)


def timeline_prediction_cell(row: dict[str, Any]) -> str:
    predictions = row.get("predictions") or {}
    count = int(predictions.get("count") or 0)
    if count <= 0:
        return timeline_state("missing", "模型预测", "缺失", "建议缺少候选资产排序；运行 forecast run。")
    content = f'<a href="/predictions">{count} 条</a><small>平均收益 {market_percent(predictions.get("avg_expected_return"))} · 置信度 {escape(percent(predictions.get("avg_confidence")))}</small>'
    return timeline_state("ok", "模型预测", content, "预测覆盖可查看。", escape_content=False)


def timeline_backtest_cell(row: dict[str, Any]) -> str:
    backtests = row.get("backtests") or {}
    run_count = int(backtests.get("run_count") or 0)
    if run_count <= 0:
        return timeline_state("missing", "回测评分", "缺失", "预测质量缺少近期校验；运行 backtest run。")
    result_count = int(backtests.get("result_count") or 0)
    content = f'<a href="/backtests">{run_count} 组</a><small>{result_count} 条结果 · 均分 {escape(format_stat(backtests.get("mean_overall_score")))}</small>'
    return timeline_state("ok", "回测评分", content, "评分证据可查看。", escape_content=False)


def timeline_task_cell(row: dict[str, Any]) -> str:
    tasks = row.get("tasks") or {}
    total = int(tasks.get("total") or 0)
    failed = int(tasks.get("failed_count") or 0)
    running = int(tasks.get("running_count") or 0)
    if total <= 0:
        return timeline_state("missing", "任务健康", "缺失", "没有任务日志；需要通过工作流或 CLI 写入 task_logs。")
    state = "bad" if failed else "warn" if running else "ok"
    content = f'<a href="/logs">{escape("异常" if failed else "运行中" if running else "正常")}</a><small>成功 {int(tasks.get("success_count") or 0)} · 失败 {failed} · 运行中 {running}</small>'
    return timeline_state(state, "任务健康", content, "任务日志可查看。", escape_content=False)


def timeline_state(state: str, label: str, value: Any, hint: str, escape_content: bool = True) -> str:
    content = escape(value) if escape_content else str(value)
    return f'<div class="timeline-state {escape(state)}"><span>{escape(label)}</span><strong>{content}</strong><small>{escape(hint)}</small></div>'


def _count_rows(conn: Any, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])


def _max_value(conn: Any, table_name: str, column_name: str) -> Any:
    return conn.execute(f"SELECT MAX({column_name}) AS value FROM {table_name}").fetchone()["value"]


def latest_recommendations(conn: Any, limit: int = 8) -> list[Any]:
    return conn.execute(
        """
        SELECT p.id, p.asset_id, a.code, a.name, a.asset_type, p.prediction_date, p.horizon_days,
               p.up_probability, p.expected_return, p.downside_risk, p.confidence,
               (COALESCE(r.risk_adjusted_score, p.expected_return, 0) * 0.5
                + COALESCE(p.up_probability, 0) * 0.2
                + COALESCE(p.confidence, 0) * 0.2
                + COALESCE(p.downside_risk, 0) * 0.1) AS recommendation_score,
               r.rank_score, r.same_category_rank, r.same_category_count,
               r.risk_adjusted_score, r.validation_status
        FROM model_predictions p
        LEFT JOIN assets a ON a.id = p.asset_id
        LEFT JOIN model_prediction_reliability r ON r.prediction_id = p.id
        WHERE p.prediction_date = (SELECT MAX(prediction_date) FROM model_predictions)
          AND p.horizon_days = 20
        ORDER BY recommendation_score DESC, p.expected_return DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def stat_grid(items: list[tuple[str, Any]]) -> str:
    return '<div class="stat-grid">' + "".join(f'<div class="stat"><span>{escape(label)}</span><strong>{format_stat(value, label=label)}</strong></div>' for label, value in items) + "</div>"


def recommendation_panel(rows: Any) -> str:
    rows = list(rows or [])
    if not rows:
        return empty("暂无可排序的预测标的；请先运行 forecast run。")
    normalized = [_recommendation_row(row) for row in rows]
    cards = "".join(recommendation_card(item) for item in normalized)
    return f'<div class="recommendations"><h3>近期优先关注</h3>{cards}</div>'


def recommendation_card(item: dict[str, Any]) -> str:
    href = f"/data?asset_id={escape(item['asset_id'])}" if item.get("asset_id") else ""
    tag = "a" if href else "div"
    href_attr = f' href="{href}" title="查看{escape(item["name"])}的行情、涨幅曲线和指标"' if href else ""
    return f"""
        <{tag} class="recommendation"{href_attr}>
          <div><b>{escape(item['name'])}</b><span>{escape(item['code'])} · {escape(item['asset_type'])}</span></div>
          <strong>{market_percent(item['expected_return'])}</strong>
          <small>{escape(item['horizon_days'])}日预期 · 排名 {escape(percent(item.get('rank_score')))} · 同类 {escape(rank_text(item.get('same_category_rank'), item.get('same_category_count')))} · 校验 {escape(validation_label(item.get('validation_status')))}</small>
        </{tag}>
        """


def asset_prediction_cards(rows: Any) -> str:
    grouped = asset_prediction_view_models(rows)
    if not grouped:
        return empty("暂无可展示的资产级预测；请先运行 forecast run。")
    return '<div class="asset-prediction-grid">' + "".join(asset_prediction_card(item) for item in grouped[:60]) + "</div>"


def asset_prediction_view_models(rows: Any) -> list[dict[str, Any]]:
    groups: dict[Any, dict[str, Any]] = {}
    for row in rows:
        asset_id = _safe_get(row, "asset_id")
        key = asset_id or f"{_safe_get(row, 'code')}:{_safe_get(row, 'name')}"
        group = groups.setdefault(
            key,
            {
                "asset_id": asset_id,
                "code": _safe_get(row, "code") or f"asset:{asset_id}",
                "name": _safe_get(row, "name") or _safe_get(row, "code") or "未知资产",
                "asset_type": _safe_get(row, "asset_type") or "asset",
                "theme": asset_theme(row)["label"],
                "prediction_date": _safe_get(row, "prediction_date"),
                "model_version": _safe_get(row, "model_version"),
                "horizons": {},
            },
        )
        horizon = int(_safe_get(row, "horizon_days") or 0)
        if horizon:
            existing = group["horizons"].get(horizon)
            if existing is None or str(_safe_get(row, "prediction_date") or "") >= str(existing.get("prediction_date") or ""):
                group["horizons"][horizon] = {
                    "prediction_id": _safe_get(row, "id"),
                    "prediction_date": _safe_get(row, "prediction_date"),
                    "expected_return": _safe_get(row, "expected_return"),
                    "up_probability": _safe_get(row, "up_probability"),
                    "downside_risk": _safe_get(row, "downside_risk"),
                    "confidence": _safe_get(row, "confidence"),
                    "rank_score": _safe_get(row, "rank_score"),
                    "same_category_rank": _safe_get(row, "same_category_rank"),
                    "same_category_count": _safe_get(row, "same_category_count"),
                    "risk_adjusted_score": _safe_get(row, "risk_adjusted_score"),
                    "validation_status": _safe_get(row, "validation_status"),
                    "degraded_reason": _safe_get(row, "degraded_reason"),
                }
                group["prediction_date"] = max(str(group.get("prediction_date") or ""), str(_safe_get(row, "prediction_date") or "")) or group.get("prediction_date")
    result = []
    for group in groups.values():
        score = _asset_prediction_score(group)
        result.append({**group, "agreement": horizon_agreement_label(group["horizons"]), "score": score})
    return sorted(result, key=lambda item: item["score"], reverse=True)


def asset_prediction_card(item: dict[str, Any]) -> str:
    href = f"/data?asset_id={escape(item['asset_id'])}" if item.get("asset_id") else ""
    tag = "a" if href else "div"
    href_attr = f' href="{href}" title="查看{escape(item["name"])}的行情、涨幅曲线和指标"' if href else ""
    horizons = "".join(horizon_signal_block(horizon, item["horizons"].get(horizon)) for horizon in (5, 20, 60))
    latest = item["horizons"].get(20) or item["horizons"].get(5) or item["horizons"].get(60) or {}
    return f"""
    <{tag} class="asset-prediction-card"{href_attr}>
      <div class="asset-prediction-head">
        <div>
          <h3>{escape(item['name'])}</h3>
          <span>{escape(item['code'])} · {escape(item['asset_type'])} · {escape(item.get('theme') or '主题待识别')} · {escape(item.get('prediction_date') or '暂无日期')}</span>
        </div>
        <b class="agreement {escape(item['agreement']['state'])}">{escape(item['agreement']['label'])}</b>
      </div>
      <div class="horizon-grid">{horizons}</div>
      <p class="muted">模型 {escape(item.get('model_version') or '暂无')} · 核心置信度 {escape(percent(latest.get('confidence')))}</p>
    </{tag}>
    """


def horizon_signal_block(horizon: int, row: dict[str, Any] | None) -> str:
    if not row:
        return f"""
        <div class="horizon-signal missing">
          <span>{horizon}日</span>
          <strong>暂无</strong>
          <small>缺少预测</small>
        </div>
        """
    return f"""
    <div class="horizon-signal">
      <span>{horizon}日</span>
      <strong>{market_percent(row.get('expected_return'))}</strong>
      <small>上涨 {escape(percent(row.get('up_probability')))} · 排名 {escape(percent(row.get('rank_score')))} · 同类 {escape(rank_text(row.get('same_category_rank'), row.get('same_category_count')))}</small>
      <small>风险调整 {escape(percent(row.get('risk_adjusted_score')))} · 校验 {escape(validation_label(row.get('validation_status')))}</small>
    </div>
    """


def rank_text(rank: Any, count: Any) -> str:
    if rank is None or count is None:
        return "暂无"
    return f"{rank}/{count}"


def validation_label(status: Any) -> str:
    labels = {
        "validated": "已校验",
        "backtest_available": "有回测",
        "warning": "警告",
        "degraded": "降级",
        "unvalidated": "待校验",
    }
    return labels.get(str(status or "unvalidated"), str(status or "待校验"))


def horizon_agreement_label(horizons: dict[int, dict[str, Any]]) -> dict[str, str]:
    ordered = [horizons[horizon] for horizon in (5, 20, 60) if horizon in horizons]
    returns = [float(row["expected_return"] or 0.0) for row in ordered]
    downside = [float(row["downside_risk"] or 0.0) for row in ordered]
    if downside and min(downside) <= -0.08:
        return {"label": "高下行风险", "state": "risk"}
    if returns and all(value > 0 for value in returns):
        return {"label": "一致向上", "state": "positive"}
    if returns and all(value < 0 for value in returns):
        return {"label": "一致偏弱", "state": "negative"}
    if len(returns) >= 2 and returns[-1] > returns[0]:
        return {"label": "中长期转强", "state": "positive"}
    if len(returns) >= 2 and returns[-1] < returns[0]:
        return {"label": "中长期转弱", "state": "negative"}
    return {"label": "分歧观察", "state": "mixed"}


def _asset_prediction_score(item: dict[str, Any]) -> float:
    horizons = item["horizons"]
    preferred = horizons.get(20) or horizons.get(5) or horizons.get(60) or {}
    expected = float(preferred.get("expected_return") or 0.0)
    confidence = float(preferred.get("confidence") or 0.0)
    upside = float(preferred.get("up_probability") or 0.0)
    downside = float(preferred.get("downside_risk") or 0.0)
    coverage = len(horizons) * 0.01
    return expected * 0.55 + confidence * 0.2 + upside * 0.15 + downside * 0.1 + coverage


def _recommendation_row(row: Any) -> dict[str, Any]:
    code = _safe_get(row, "code") or _safe_get(row, "asset_code") or f"asset:{_safe_get(row, 'asset_id')}"
    name = _safe_get(row, "name") or _safe_get(row, "asset_name") or code
    return {
        "asset_id": _safe_get(row, "asset_id"),
        "code": code,
        "name": name,
        "asset_type": _safe_get(row, "asset_type") or "asset",
        "horizon_days": _safe_get(row, "horizon_days") or "-",
        "expected_return": _safe_get(row, "expected_return"),
        "up_probability": _safe_get(row, "up_probability"),
        "downside_risk": _safe_get(row, "downside_risk"),
        "confidence": _safe_get(row, "confidence"),
        "rank_score": _safe_get(row, "rank_score"),
        "same_category_rank": _safe_get(row, "same_category_rank"),
        "same_category_count": _safe_get(row, "same_category_count"),
        "risk_adjusted_score": _safe_get(row, "risk_adjusted_score"),
        "validation_status": _safe_get(row, "validation_status"),
    }


def _safe_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key] if key in row.keys() else None


def data_curve_window(query: dict[str, list[str]], bounds: Any) -> dict[str, str | None]:
    min_date = _safe_get(bounds, "start_date") if bounds else None
    max_date = _safe_get(bounds, "end_date") if bounds else None
    range_key = str(_first_query_value(query, "range", "6m") or "6m")
    if range_key not in {"1m", "3m", "6m", "1y", "all", "custom"}:
        range_key = "6m"

    end = parse_iso_date(_first_query_value(query, "end_date", max_date)) or parse_iso_date(max_date)
    start = parse_iso_date(_first_query_value(query, "start_date", None))
    if range_key != "custom":
        start = range_start_for_key(range_key, end, parse_iso_date(min_date))
    if start is None:
        start = parse_iso_date(min_date)
    if end and start and start > end:
        start, end = end, start
    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "min": min_date,
        "max": max_date,
        "range": range_key,
    }


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def range_start_for_key(range_key: str, end: date | None, minimum: date | None) -> date | None:
    if range_key == "all" or end is None:
        return minimum
    days = {"1m": 31, "3m": 93, "6m": 186, "1y": 366}.get(range_key, 186)
    start = end - timedelta(days=days)
    return max(start, minimum) if minimum else start


def _first_query_value(query: dict[str, list[str]], key: str, default: Any = None) -> Any:
    values = query.get(key)
    return values[0] if values else default


def query_url(path: str, query: dict[str, list[str]], **updates: Any) -> str:
    params: dict[str, Any] = {key: values[0] for key, values in query.items() if values}
    for key, value in updates.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = urlencode(params)
    return f"{path}?{encoded}" if encoded else path


def data_table_tabs(query: dict[str, list[str]], selected_id: int, active_tab: str) -> str:
    tabs = [
        ("history", "行情 / 净值历史"),
        ("features", "量化指标"),
    ]
    links = "".join(
        f'<button class="tab-link {"active" if key == active_tab else ""}" type="button" role="tab" aria-selected="{str(key == active_tab).lower()}" data-tab-target="{escape(key)}" data-tab-url="{escape(query_url("/data", query, asset_id=selected_id, table_tab=key))}">{escape(label)}</button>'
        for key, label in tabs
    )
    return f'<div class="tab-bar" role="tablist" aria-label="行情与量化指标切换">{links}</div>'


def data_table_tab_panels(history: Any, features: Any, *, active_tab: str) -> str:
    history_table = table(history, ["trade_date", "close", "adjusted_close", "nav", "volume", "amount", "pct_change", "source"])
    feature_table = table(features, ["feature_date", "return_1d", "return_20d", "volatility_20d", "max_drawdown_60d", "sharpe_60d", "calmar_60d", "win_rate_60d", "market_state", "source"])
    return "\n".join(
        [
            f'<div class="tab-panel {"active" if active_tab == "history" else ""}" data-tab-panel="history" role="tabpanel">{history_table}</div>',
            f'<div class="tab-panel {"active" if active_tab == "features" else ""}" data-tab-panel="features" role="tabpanel">{feature_table}</div>',
        ]
    )


def _preference_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    risk_profile = _first_query_value(query, "risk_profile", "balanced")
    if risk_profile not in {"aggressive", "balanced", "conservative"}:
        risk_profile = "balanced"
    return {
        "profile_name": str(_first_query_value(query, "profile_name", "默认账户"))[:80],
        "risk_profile": risk_profile,
        "investment_horizon_days": max(1, int(_first_query_value(query, "investment_horizon_days", 20))),
        "max_equity_pct": min(max(float(_first_query_value(query, "max_equity_pct", 0.6)), 0.0), 1.0),
        "min_cash_pct": min(max(float(_first_query_value(query, "min_cash_pct", 0.1)), 0.0), 1.0),
        "notes": str(_first_query_value(query, "notes", ""))[:500],
        "is_active": 1,
    }


def return_curve(rows: Any, *, asset_id: int | None = None, date_window: dict[str, str | None] | None = None) -> str:
    values = []
    labels = []
    for row in rows:
        price = _safe_get(row, "adjusted_close") or _safe_get(row, "close") or _safe_get(row, "nav")
        if price is None:
            continue
        values.append(float(price))
        labels.append(_safe_get(row, "trade_date"))
    if len(values) < 2 or not values[0]:
        return empty("至少需要两个有效价格/净值点才能绘制涨幅曲线。")

    returns = [(value / values[0]) - 1.0 for value in values]
    low = min(returns)
    high = max(returns)
    span = high - low or 1.0
    width = 760
    height = 260
    left = 62
    right = 18
    top = 18
    bottom = 34
    plot_width = width - left - right
    plot_height = height - top - bottom
    points = []
    hit_points = []
    for index, value in enumerate(returns):
        x = left + index / max(len(returns) - 1, 1) * plot_width
        y = top + plot_height - ((value - low) / span * plot_height)
        points.append(f"{x:.1f},{y:.1f}")
        hit_points.append(
            {
                "x": x,
                "y": y,
                "date": str(labels[index] or ""),
                "price": values[index],
                "return": value,
            }
        )

    latest_return = returns[-1]
    start_label = labels[0] or ""
    end_label = labels[-1] or ""
    zero_y = top + plot_height - ((0 - low) / span * plot_height)
    y_ticks = curve_y_ticks(low, high)
    x_ticks = curve_x_ticks(labels)
    grid = "".join(
        f'<line class="grid-line" x1="{left}" y1="{top + plot_height - ((tick - low) / span * plot_height):.1f}" x2="{left + plot_width}" y2="{top + plot_height - ((tick - low) / span * plot_height):.1f}"></line>'
        f'<text class="axis-label y-label" x="{left - 8}" y="{top + plot_height - ((tick - low) / span * plot_height) + 4:.1f}">{escape(plain_percent(tick))}</text>'
        for tick in y_ticks
    )
    x_axis = "".join(
        f'<line class="tick-line" x1="{left + (index / max(len(labels) - 1, 1) * plot_width):.1f}" y1="{top + plot_height}" x2="{left + (index / max(len(labels) - 1, 1) * plot_width):.1f}" y2="{top + plot_height + 5}"></line>'
        f'<text class="axis-label x-label" x="{left + (index / max(len(labels) - 1, 1) * plot_width):.1f}" y="{height - 8}">{escape(str(label))}</text>'
        for index, label in x_ticks
    )
    point_data = json.dumps(
        [
            {
                "date": point["date"],
                "price": f"{point['price']:.4f}",
                "returnValue": plain_percent(point["return"], signed=True),
                "x": round(point["x"], 2),
                "y": round(point["y"], 2),
            }
            for point in hit_points
        ],
        ensure_ascii=False,
    )
    point_nodes = "".join(
        f"""
        <g class="curve-point" data-index="{index}" aria-hidden="true">
          <title>{escape(point['date'])} · {point['price']:.4f} · {escape(plain_percent(point['return'], signed=True))}</title>
          <line class="point-guide point-guide-x" x1="{left}" y1="{point['y']:.1f}" x2="{left + plot_width}" y2="{point['y']:.1f}"></line>
          <line class="point-guide point-guide-y" x1="{point['x']:.1f}" y1="{top}" x2="{point['x']:.1f}" y2="{top + plot_height}"></line>
          <circle class="point-dot" cx="{point['x']:.1f}" cy="{point['y']:.1f}" r="3.2"></circle>
        </g>
        """
        for index, point in enumerate(hit_points)
    )
    controls = curve_time_controls(asset_id, date_window)
    return f"""
    <div class="curve-card interactive-curve">
      {controls}
      <div class="curve-meta">
        <span>{escape(start_label)} 至 {escape(end_label)} · {len(values)} 个交易点</span>
        <strong>{market_percent(latest_return)}</strong>
      </div>
      <svg class="curve" viewBox="0 0 {width} {height}" role="img" aria-label="涨幅曲线">
        {grid}
        <line class="zero-line" x1="{left}" y1="{zero_y:.1f}" x2="{left + plot_width}" y2="{zero_y:.1f}"></line>
        <line class="axis-line" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"></line>
        <line class="axis-line" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"></line>
        {x_axis}
        <polyline points="{' '.join(points)}"></polyline>
        {point_nodes}
        <rect class="curve-capture" x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" tabindex="0" role="slider" aria-label="按横轴选择交易点"></rect>
      </svg>
      <div class="curve-tooltip" aria-live="polite">
        <strong data-role="date">{escape(end_label)}</strong>
        <span>价格/净值 <b data-role="price">{values[-1]:.4f}</b></span>
        <span>区间涨幅 <b data-role="return">{escape(plain_percent(latest_return, signed=True))}</b></span>
      </div>
      <script>
      (() => {{
        const card = document.currentScript.closest('.interactive-curve');
        if (!card) return;
        const svg = card.querySelector('svg.curve');
        const capture = card.querySelector('.curve-capture');
        const tooltip = card.querySelector('.curve-tooltip');
        const points = {point_data};
        const plot = {{ left: {left}, top: {top}, width: {plot_width}, height: {plot_height} }};
        let selectedIndex = -1;
        const readout = {{
          date: card.querySelector('[data-role="date"]'),
          price: card.querySelector('[data-role="price"]'),
          returnValue: card.querySelector('[data-role="return"]')
        }};
        const showPoint = (index) => {{
          const data = points[index];
          if (!data) return;
          selectedIndex = index;
          card.querySelectorAll('.curve-point.selected').forEach((node) => node.classList.remove('selected'));
          const point = card.querySelector(`.curve-point[data-index="${{index}}"]`);
          if (point) point.classList.add('selected');
          readout.date.textContent = data.date || '-';
          readout.price.textContent = data.price || '-';
          readout.returnValue.textContent = data.returnValue || '-';
          const cardRect = card.getBoundingClientRect();
          const svgRect = svg.getBoundingClientRect();
          const tooltipRect = tooltip.getBoundingClientRect();
          const markerLeft = svgRect.left - cardRect.left + data.x / {width} * svgRect.width;
          const markerTop = svgRect.top - cardRect.top + data.y / {height} * svgRect.height;
          let left = markerLeft + 14;
          let top = markerTop - tooltipRect.height - 10;
          if (left + tooltipRect.width > cardRect.width - 8) left = markerLeft - tooltipRect.width - 14;
          if (top < 8) top = markerTop + 14;
          tooltip.style.left = `${{Math.max(8, left)}}px`;
          tooltip.style.top = `${{Math.max(8, top)}}px`;
          tooltip.classList.add('visible');
        }};
        const nearestIndex = (clientX) => {{
          const rect = svg.getBoundingClientRect();
          const svgX = (clientX - rect.left) / rect.width * {width};
          const ratio = Math.min(1, Math.max(0, (svgX - plot.left) / plot.width));
          return Math.round(ratio * Math.max(points.length - 1, 0));
        }};
        capture.addEventListener('mousemove', (event) => showPoint(nearestIndex(event.clientX)));
        capture.addEventListener('click', (event) => showPoint(nearestIndex(event.clientX)));
        capture.addEventListener('mouseleave', () => {{
          if (selectedIndex < 0) tooltip.classList.remove('visible');
        }});
        capture.addEventListener('keydown', (event) => {{
          if (selectedIndex < 0) selectedIndex = points.length - 1;
          if (event.key === 'ArrowLeft') {{
            event.preventDefault();
            showPoint(Math.max(0, selectedIndex - 1));
          }} else if (event.key === 'ArrowRight') {{
            event.preventDefault();
            showPoint(Math.min(points.length - 1, selectedIndex + 1));
          }}
        }});
      }})();
      </script>
    </div>
    """


def curve_time_controls(asset_id: int | None, date_window: dict[str, str | None] | None) -> str:
    if not date_window or asset_id is None:
        return ""
    active = date_window.get("range") or "6m"
    options = [("1m", "1月"), ("3m", "3月"), ("6m", "6月"), ("1y", "1年"), ("all", "全部")]
    buttons = "".join(
        f'<a class="range-chip {"active" if key == active else ""}" href="/data?asset_id={asset_id}&range={key}">{label}</a>'
        for key, label in options
    )
    return f"""
      <div class="curve-controls">
        <div class="range-chips" aria-label="时间范围">{buttons}</div>
        <form class="range-form" method="get" action="/data">
          <input type="hidden" name="asset_id" value="{asset_id}">
          <input type="hidden" name="range" value="custom">
          <label>开始<input type="date" name="start_date" value="{escape(date_window.get('start') or '')}" min="{escape(date_window.get('min') or '')}" max="{escape(date_window.get('max') or '')}"></label>
          <label>结束<input type="date" name="end_date" value="{escape(date_window.get('end') or '')}" min="{escape(date_window.get('min') or '')}" max="{escape(date_window.get('max') or '')}"></label>
          <button type="submit">应用</button>
        </form>
      </div>
    """


def curve_y_ticks(low: float, high: float) -> list[float]:
    if high == low:
        return [low]
    return [low + (high - low) * index / 4 for index in range(5)]


def curve_x_ticks(labels: list[Any]) -> list[tuple[int, Any]]:
    if not labels:
        return []
    dated = [(index, parse_iso_date(label), str(label)) for index, label in enumerate(labels)]
    valid_dates = [item[1] for item in dated if item[1] is not None]
    if len(valid_dates) < 2:
        return [(index, _compact_date_label(label)) for index, _, label in dated]
    span_days = (valid_dates[-1] - valid_dates[0]).days
    if span_days <= 10:
        indexes = [index for index, _, _ in dated]
    elif span_days <= 45:
        indexes = _first_index_per_period(dated, "week")
    elif span_days <= 400:
        indexes = _first_index_per_period(dated, "month")
    else:
        indexes = _first_index_per_period(dated, "quarter")
    indexes = sorted({0, *indexes, len(labels) - 1})
    return [(index, _compact_date_label(labels[index])) for index in indexes]


def _first_index_per_period(dated: list[tuple[int, date | None, str]], period: str) -> list[int]:
    seen: set[tuple[int, int] | tuple[int, int, int]] = set()
    indexes: list[int] = []
    for index, label_date, _ in dated:
        if label_date is None:
            continue
        if period == "week":
            iso = label_date.isocalendar()
            key: tuple[int, int] | tuple[int, int, int] = (iso.year, iso.week)
        elif period == "quarter":
            key = (label_date.year, (label_date.month - 1) // 3)
        else:
            key = (label_date.year, label_date.month)
        if key in seen:
            continue
        seen.add(key)
        indexes.append(index)
    return indexes


def _compact_date_label(value: Any) -> str:
    label_date = parse_iso_date(value)
    if label_date is None:
        return str(value)
    return label_date.strftime("%m-%d")


def table(rows: Any, columns: list[str], escape_cells: bool = True) -> str:
    rows = list(rows)
    if not rows:
        return empty("No records available.")
    head = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(
            f"<td>{format_cell(row[column] if column in row.keys() else row.get(column), column=column, escape_value=escape_cells)}</td>"
            for column in columns
        ) + "</tr>"
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def asset_selector(assets: Any, selected_id: int, path: str, hidden: dict[str, Any] | None = None) -> str:
    options = "".join(
        f'<option value="{asset["id"]}" {"selected" if asset["id"] == selected_id else ""}>{escape(asset["code"])} · {escape(asset["name"])}</option>'
        for asset in assets
    )
    hidden_inputs = "".join(
        f'<input type="hidden" name="{escape(key)}" value="{escape(value)}">'
        for key, value in (hidden or {}).items()
        if value not in (None, "")
    )
    return f'<form class="toolbar" method="get" action="{path}">{hidden_inputs}<select name="asset_id">{options}</select><button type="submit">查看</button></form>'


def advice_selector(history: Any, selected_id: int) -> str:
    rows = list(history)
    if not rows:
        return ""
    options = "".join(
        f'<option value="{row["id"]}" {"selected" if row["id"] == selected_id else ""}>{escape(row["advice_date"])} · {escape(row["risk_level"])} · {escape(row["model_version"] or "")}</option>'
        for row in rows
    )
    return f'<form class="toolbar" method="get" action="/advice"><select name="advice_id">{options}</select><button type="submit">查看历史建议</button></form>'


def advice_history_table(history: Any) -> str:
    rows = [
        {
            "advice_date": f'<a href="/advice?advice_id={row["id"]}">{escape(row["advice_date"])}</a>',
            "risk_level": escape(row["risk_level"]),
            "model_version": escape(row["model_version"] or ""),
            "overall_score": row["overall_score"],
        }
        for row in history
    ]
    return '<div class="history-list"><h3>历史记录</h3>' + table(rows, ["advice_date", "risk_level", "model_version", "overall_score"], escape_cells=False) + "</div>"


def expert_overview_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            e.*,
            vp.id AS portfolio_id,
            vp.initial_capital,
            vp.cash AS current_cash,
            vv.valuation_date,
            vv.total_value,
            vv.positions_value,
            sc.score_date,
            sc.overall_score,
            sc.portfolio_return,
            sc.benchmark_excess,
            sc.max_drawdown,
            sc.mature_enough,
            rv.decision AS latest_decision,
            rv.rationale AS review_rationale
        FROM experts e
        LEFT JOIN virtual_portfolios vp
          ON vp.owner_type = 'expert' AND vp.owner_id = e.id
        LEFT JOIN virtual_valuations vv ON vv.id = (
            SELECT id FROM virtual_valuations
            WHERE portfolio_id = vp.id
            ORDER BY valuation_date DESC, id DESC
            LIMIT 1
        )
        LEFT JOIN expert_scorecards sc ON sc.id = (
            SELECT id FROM expert_scorecards
            WHERE expert_id = e.id
            ORDER BY score_date DESC, id DESC
            LIMIT 1
        )
        LEFT JOIN expert_reviews rv ON rv.id = (
            SELECT id FROM expert_reviews
            WHERE expert_id = e.id
            ORDER BY review_date DESC, id DESC
            LIMIT 1
        )
        WHERE COALESCE(e.source, '') != ?
        ORDER BY
            CASE e.lifecycle_state
                WHEN 'active' THEN 0
                WHEN 'probation' THEN 1
                WHEN 'candidate' THEN 2
                WHEN 'retired' THEN 3
                ELSE 4
            END,
            e.expert_key
        """,
        (OBSOLETE_STYLE_NAMED_EXPERT_SOURCE,),
    ).fetchall()
    return [dict(row) for row in rows]


def latest_expert_plans(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            p.id, p.plan_date, p.action, p.target_weight, p.target_amount,
            p.execution_status, p.rationale, p.risk_warnings,
            e.name AS expert_name, e.lifecycle_state,
            a.code AS asset_code, a.name AS asset_name
        FROM expert_plans p
        JOIN experts e ON e.id = p.expert_id
        LEFT JOIN assets a ON a.id = p.target_asset_id
        WHERE p.plan_date = (SELECT MAX(plan_date) FROM expert_plans)
          AND COALESCE(e.source, '') != ?
        ORDER BY e.expert_key
        """,
        (OBSOLETE_STYLE_NAMED_EXPERT_SOURCE,),
    ).fetchall()
    return [dict(row) for row in rows]


def expert_lesson_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT l.*, e.name AS expert_name, e.style_label
        FROM expert_lessons l
        LEFT JOIN experts e ON e.id = l.expert_id
        ORDER BY l.lesson_date DESC, l.id DESC
        LIMIT 40
        """
    ).fetchall()
    return [dict(row) for row in rows]


def expert_equity_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            e.expert_key,
            e.name AS expert_name,
            vp.initial_capital,
            e.lifecycle_state,
            vv.valuation_date,
            vv.cash,
            vv.positions_value,
            vv.total_value
        FROM virtual_valuations vv
        JOIN virtual_portfolios vp ON vp.id = vv.portfolio_id
        JOIN experts e ON e.id = vp.owner_id AND vp.owner_type = 'expert'
        WHERE COALESCE(e.source, '') != ?
        ORDER BY vv.valuation_date DESC, e.expert_key
        LIMIT 120
        """,
        (OBSOLETE_STYLE_NAMED_EXPERT_SOURCE,),
    ).fetchall()
    return [dict(row) for row in rows]


def expert_detail_rows(conn: Any, expert_key: str | None = None) -> list[dict[str, Any]]:
    experts = expert_overview_rows(conn)
    if expert_key:
        experts = [expert for expert in experts if expert["expert_key"] == expert_key]
    details = []
    for expert in experts:
        portfolio_id = expert["portfolio_id"]
        plans = conn.execute(
            """
            SELECT
                p.id, p.plan_date, p.action, p.target_weight, p.target_amount,
                p.execution_status, p.rationale, p.evidence_json,
                p.risk_checks_json, p.risk_warnings,
                a.code AS asset_code, a.name AS asset_name
            FROM expert_plans p
            LEFT JOIN assets a ON a.id = p.target_asset_id
            WHERE p.expert_id = ?
            ORDER BY p.plan_date DESC, p.id DESC
            """,
            (expert["id"],),
        ).fetchall()
        valuations = []
        positions = []
        transactions = []
        if portfolio_id is not None:
            valuations = conn.execute(
                """
                SELECT valuation_date, cash, positions_value, total_value,
                       details_json
                FROM virtual_valuations
                WHERE portfolio_id = ?
                ORDER BY valuation_date ASC, id ASC
                """,
                (portfolio_id,),
            ).fetchall()
            latest_valuation = conn.execute(
                """
                SELECT details_json
                FROM virtual_valuations
                WHERE portfolio_id = ?
                ORDER BY valuation_date DESC, id DESC
                LIMIT 1
                """,
                (portfolio_id,),
            ).fetchone()
            positions = _position_details_from_valuation(latest_valuation["details_json"] if latest_valuation else "[]")
            transactions = conn.execute(
                """
                SELECT vt.trade_date, vt.side, vt.status, vt.quantity,
                       vt.price, vt.gross_amount, vt.cost_basis,
                       vt.realized_pnl, vt.reason,
                       a.code AS asset_code, a.name AS asset_name
                FROM virtual_transactions vt
                LEFT JOIN assets a ON a.id = vt.asset_id
                WHERE vt.portfolio_id = ?
                ORDER BY vt.trade_date DESC, vt.id DESC
                """,
                (portfolio_id,),
            ).fetchall()
        scorecards = conn.execute(
            """
            SELECT score_date, window_days, valuation_count, mature_enough,
                   portfolio_return, benchmark_return, benchmark_excess,
                   max_drawdown, volatility, cash_drag, turnover, win_rate,
                   evidence_completeness, mandate_adherence, overall_score,
                   details_json
            FROM expert_scorecards
            WHERE expert_id = ?
            ORDER BY score_date DESC, id DESC
            """,
            (expert["id"],),
        ).fetchall()
        reviews = conn.execute(
            """
            SELECT review_date, decision, previous_lifecycle_state,
                   new_lifecycle_state, rationale, evidence_json
            FROM expert_reviews
            WHERE expert_id = ?
            ORDER BY review_date DESC, id DESC
            """,
            (expert["id"],),
        ).fetchall()
        details.append(
            {
                "expert": expert,
                "plans": [dict(row) for row in plans],
                "valuations": [dict(row) for row in valuations],
                "positions": positions,
                "transactions": [dict(row) for row in transactions],
                "scorecards": [dict(row) for row in scorecards],
                "reviews": [dict(row) for row in reviews],
            }
        )
    return details


def _position_details_from_valuation(details_json: str) -> list[dict[str, Any]]:
    rows = json.loads(details_json or "[]")
    return [
        {
            "asset": f"{row.get('asset_code') or ''} {row.get('asset_name') or ''}".strip() or "未命名资产",
            "quantity": row.get("quantity"),
            "average_cost": money(row.get("average_cost")),
            "current_price": money(row.get("price")),
            "price_date": row.get("price_date") or "暂无",
            "cost_basis": money(row.get("cost_basis")),
            "market_value": money(row.get("value")),
            "unrealized_pnl": money(row.get("unrealized_pnl")),
            "position_return": percent(row.get("position_return")),
        }
        for row in rows
    ]


def expert_cards(rows: list[dict[str, Any]]) -> str:
    active_count = sum(1 for row in rows if row["lifecycle_state"] == "active")
    cards = "".join(expert_card(row) for row in rows)
    return (
        stat_grid(
            [
                ("活跃专家", active_count),
                ("专家总数", len(rows)),
                ("最近评分", max((row["score_date"] or "" for row in rows), default="暂无") or "暂无"),
                ("最近估值", max((row["valuation_date"] or "" for row in rows), default="暂无") or "暂无"),
            ]
        )
        + f'<div class="expert-grid">{cards}</div>'
    )


def expert_card(row: dict[str, Any]) -> str:
    state = row["lifecycle_state"]
    total_value = row["total_value"] if row["total_value"] is not None else row["initial_capital"]
    return_value = None
    if total_value is not None and row["initial_capital"]:
        return_value = (float(total_value) / float(row["initial_capital"])) - 1.0
    score = row["overall_score"]
    href = f"/experts?expert={escape(row['expert_key'])}"
    return f"""
    <a class="expert-card state-{escape(state)}" href="{href}">
      <div class="expert-head">
        <div><h3>{escape(row['name'])}</h3><span>{escape(row['style_label'])}</span></div>
        <b>{escape(lifecycle_label(state))}</b>
      </div>
      <div class="expert-card-metrics">
        <span><small>资产</small><b>{escape(money(total_value))}</b></span>
        <span><small>现金</small><b>{escape(money(row["current_cash"]))}</b></span>
        <span><small>收益</small><b>{market_percent(return_value)}</b></span>
        <span><small>评分</small><b>{escape(score if score is not None else "暂无")}</b></span>
      </div>
      <span class="detail-link">查看详情</span>
    </a>
    """


def expert_plan_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("还没有专家计划；请运行 experts run-plans。")
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                "expert_name": row["expert_name"],
                "state": lifecycle_label(row["lifecycle_state"]),
                "plan_date": row["plan_date"],
                "action": row["action"],
                "target": f"{row['asset_code'] or '无'} {row['asset_name'] or ''}".strip(),
                "target_weight": percent(row["target_weight"]),
                "target_amount": money(row["target_amount"]),
                "execution_status": row["execution_status"],
                "rationale": row["rationale"],
            }
        )
    return table(display_rows, ["expert_name", "state", "plan_date", "action", "target", "target_weight", "target_amount", "execution_status", "rationale"])


def expert_detail_panel(details: list[dict[str, Any]]) -> str:
    if not details:
        return empty("还没有专家详情；请先运行 experts init 和 experts init-portfolios。")
    return '<div class="expert-detail-list">' + "".join(expert_detail_card(detail) for detail in details) + "</div>"


def expert_detail_page(detail: dict[str, Any]) -> str:
    return (
        section("专家档案", expert_profile_summary(detail))
        + section("完整时间系", expert_full_timeline(detail))
        + section("投资计划与执行", expert_plans_and_execution(detail))
        + section("当前投资", expert_positions_table(detail["positions"]))
        + section("收益曲线", expert_return_curve(detail["valuations"], detail["expert"]["initial_capital"]))
        + section("分析与反思", expert_analysis_reflection(detail))
    )


def expert_profile_summary(detail: dict[str, Any]) -> str:
    expert = detail["expert"]
    latest_valuation = detail["valuations"][-1] if detail["valuations"] else None
    total_value = latest_valuation["total_value"] if latest_valuation else expert["total_value"] or expert["initial_capital"]
    positions_value = latest_valuation["positions_value"] if latest_valuation else expert["positions_value"]
    cash = latest_valuation["cash"] if latest_valuation else expert["current_cash"]
    invested_ratio = (float(positions_value or 0) / float(total_value)) if total_value else None
    return f"""
    <div class="expert-profile-head">
      <div>
        <h3>{escape(expert['name'])}</h3>
        <span>{escape(expert['style_label'])} · {escape(lifecycle_label(expert['lifecycle_state']))}</span>
        <p>{escape(expert['short_description'])}</p>
      </div>
      <strong>{market_percent(_portfolio_return_from_values(expert['initial_capital'], total_value))}</strong>
    </div>
    {stat_grid([
        ("总资产", money(total_value)),
        ("已投资", money(positions_value)),
        ("现金", money(cash)),
        ("投资占比", percent(invested_ratio)),
        ("最近估值", latest_valuation["valuation_date"] if latest_valuation else "暂无"),
        ("最新评分", expert["overall_score"] if expert["overall_score"] is not None else "暂无"),
    ])}
    """


def expert_detail_card(detail: dict[str, Any]) -> str:
    expert = detail["expert"]
    latest_plan = detail["plans"][0] if detail["plans"] else None
    latest_valuation = detail["valuations"][-1] if detail["valuations"] else None
    total_value = latest_valuation["total_value"] if latest_valuation else expert["total_value"] or expert["initial_capital"]
    positions_value = latest_valuation["positions_value"] if latest_valuation else expert["positions_value"]
    cash = latest_valuation["cash"] if latest_valuation else expert["current_cash"]
    invested_ratio = None
    if total_value:
        invested_ratio = float(positions_value or 0) / float(total_value)
    plan_summary = expert_latest_plan_summary(latest_plan)
    return f"""
    <article class="expert-detail state-{escape(expert['lifecycle_state'])}">
      <div class="expert-detail-head">
        <div>
          <h3>{escape(expert['name'])}</h3>
          <span>{escape(expert['style_label'])} · {escape(lifecycle_label(expert['lifecycle_state']))}</span>
        </div>
        <strong>{market_percent(_portfolio_return_from_values(expert['initial_capital'], total_value))}</strong>
      </div>
      {stat_grid([
          ("总资产", money(total_value)),
          ("已投资", money(positions_value)),
          ("现金", money(cash)),
          ("投资占比", percent(invested_ratio)),
      ])}
      <div class="expert-detail-grid">
        <div class="expert-subpanel">
          <h4>投资计划</h4>
          {plan_summary}
        </div>
        <div class="expert-subpanel">
          <h4>时间线</h4>
          {expert_timeline(detail)}
        </div>
        <div class="expert-subpanel">
          <h4>当前投资</h4>
          {expert_positions_table(detail['positions'])}
        </div>
        <div class="expert-subpanel">
          <h4>收益曲线</h4>
          {expert_return_curve(detail['valuations'], expert['initial_capital'])}
        </div>
      </div>
    </article>
    """


def expert_latest_plan_summary(row: dict[str, Any] | None) -> str:
    if row is None:
        return empty("还没有投资计划；运行 experts run-plans 后会显示。")
    target = f"{row['asset_code'] or '无'} {row['asset_name'] or ''}".strip()
    return f"""
    <div class="expert-plan-summary">
      <div><span>日期</span><strong>{escape(row['plan_date'])}</strong></div>
      <div><span>动作</span><strong>{escape(row['action'])}</strong></div>
      <div><span>目标</span><strong>{escape(target)}</strong></div>
      <div><span>金额</span><strong>{escape(money(row['target_amount']))}</strong></div>
      <p>{escape(row['rationale'])}</p>
    </div>
    """


def expert_timeline(detail: dict[str, Any]) -> str:
    events = []
    for plan in detail["plans"][:4]:
        target = f"{plan['asset_code'] or '无'} {plan['asset_name'] or ''}".strip()
        events.append(
            {
                "date": plan["plan_date"],
                "title": f"{plan['action']} · {plan['execution_status']}",
                "meta": target,
            }
        )
    for tx in detail["transactions"][:4]:
        target = f"{tx['asset_code'] or '无'} {tx['asset_name'] or ''}".strip()
        events.append(
            {
                "date": tx["trade_date"],
                "title": f"{tx['side']} · {tx['status']}",
                "meta": f"{target} {money(tx['gross_amount'])}",
            }
        )
    if not events:
        return empty("还没有计划或交易时间线。")
    unique = []
    seen = set()
    for event in sorted(events, key=lambda item: item["date"], reverse=True):
        key = (event["date"], event["title"], event["meta"])
        if key not in seen:
            unique.append(event)
            seen.add(key)
    items = "".join(
        f'<li><time>{escape(event["date"])}</time><b>{escape(event["title"])}</b><span>{escape(event["meta"])}</span></li>'
        for event in unique[:6]
    )
    return f'<ol class="expert-timeline">{items}</ol>'


def expert_full_timeline(detail: dict[str, Any]) -> str:
    events = []
    for plan in detail["plans"]:
        target = f"{plan['asset_code'] or '无'} {plan['asset_name'] or ''}".strip()
        events.append(
            {
                "date": plan["plan_date"],
                "type": "投资计划",
                "event": f"{plan['action']} / {plan['execution_status']}",
                "asset": target,
                "reason": plan["rationale"],
            }
        )
    for tx in detail["transactions"]:
        target = f"{tx['asset_code'] or '无'} {tx['asset_name'] or ''}".strip()
        events.append(
            {
                "date": tx["trade_date"],
                "type": "虚拟交易",
                "event": f"{tx['side']} / {tx['status']} / {money(tx['gross_amount'])}",
                "asset": target,
                "reason": tx["reason"] or "暂无原因",
            }
        )
    for valuation in detail["valuations"]:
        events.append(
            {
                "date": valuation["valuation_date"],
                "type": "组合估值",
                "event": f"总资产 {money(valuation['total_value'])}",
                "asset": f"已投资 {money(valuation['positions_value'])} / 现金 {money(valuation['cash'])}",
                "reason": "按已入库价格或净值重估虚拟组合。",
            }
        )
    for review in detail["reviews"]:
        events.append(
            {
                "date": review["review_date"],
                "type": "复盘反思",
                "event": review["decision"],
                "asset": f"{lifecycle_label(review['previous_lifecycle_state'] or '')} → {lifecycle_label(review['new_lifecycle_state'] or '')}",
                "reason": review["rationale"],
            }
        )
    if not events:
        return empty("还没有时间系记录。")
    rows = sorted(events, key=lambda item: (item["date"], item["type"]), reverse=True)
    return table(rows, ["date", "type", "event", "asset", "reason"])


def expert_plans_and_execution(detail: dict[str, Any]) -> str:
    if not detail["plans"] and not detail["transactions"]:
        return empty("还没有投资计划或执行记录。")
    plan_rows = []
    for plan in detail["plans"]:
        evidence = _json_summary(plan.get("evidence_json"), ["prediction_id", "market_snapshot_id"])
        risk_checks = _json_summary(plan.get("risk_checks_json"), ["drawdown_within_tolerance", "downside_within_tolerance", "confidence", "market_sentiment"])
        plan_rows.append(
            {
                "plan_date": plan["plan_date"],
                "action": plan["action"],
                "target": f"{plan['asset_code'] or '无'} {plan['asset_name'] or ''}".strip(),
                "target_weight": percent(plan["target_weight"]),
                "target_amount": money(plan["target_amount"]),
                "execution_status": plan["execution_status"],
                "reason": plan["rationale"],
                "analysis": f"证据 {evidence}；风险检查 {risk_checks}",
                "risk_warnings": plan["risk_warnings"],
            }
        )
    tx_rows = [
        {
            "trade_date": tx["trade_date"],
            "side": tx["side"],
            "status": tx["status"],
            "asset": f"{tx['asset_code'] or '无'} {tx['asset_name'] or ''}".strip(),
            "quantity": tx["quantity"],
            "price": tx["price"] if tx["price"] is not None else "暂无",
            "amount": money(tx["gross_amount"]),
            "cost_basis": money(tx["cost_basis"]),
            "realized_pnl": money(tx["realized_pnl"]),
            "reason": tx["reason"] or "暂无原因",
        }
        for tx in detail["transactions"]
    ]
    body = ""
    if plan_rows:
        body += "<h3>投资计划</h3>" + table(plan_rows, ["plan_date", "action", "target", "target_weight", "target_amount", "execution_status", "reason", "analysis", "risk_warnings"])
    if tx_rows:
        body += "<h3>执行记录</h3>" + table(tx_rows, ["trade_date", "side", "status", "asset", "quantity", "price", "amount", "cost_basis", "realized_pnl", "reason"])
    return body


def expert_analysis_reflection(detail: dict[str, Any]) -> str:
    score_rows = [
        {
            "score_date": row["score_date"],
            "window_days": row["window_days"],
            "valuation_count": row["valuation_count"],
            "portfolio_return": row["portfolio_return"],
            "benchmark_excess": row["benchmark_excess"],
            "max_drawdown": row["max_drawdown"],
            "cash_drag": row["cash_drag"],
            "turnover": percent(row["turnover"]),
            "overall_score": row["overall_score"] if row["overall_score"] is not None else "暂无",
            "analysis": _json_summary(row.get("details_json"), ["valuation_dates", "mature_enough"]),
        }
        for row in detail["scorecards"]
    ]
    review_rows = [
        {
            "review_date": row["review_date"],
            "decision": row["decision"],
            "state_change": f"{lifecycle_label(row['previous_lifecycle_state'] or '')} → {lifecycle_label(row['new_lifecycle_state'] or '')}",
            "reflection": row["rationale"],
        }
        for row in detail["reviews"]
    ]
    body = ""
    body += "<h3>评分分析</h3>" + (table(score_rows, ["score_date", "window_days", "valuation_count", "portfolio_return", "benchmark_excess", "max_drawdown", "cash_drag", "turnover", "overall_score", "analysis"]) if score_rows else empty("还没有评分分析。"))
    body += "<h3>复盘反思</h3>" + (table(review_rows, ["review_date", "decision", "state_change", "reflection"]) if review_rows else empty("还没有复盘反思。"))
    return body


def _json_summary(raw: Any, keys: list[str]) -> str:
    if not raw:
        return "暂无"
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return str(raw)
    parts = []
    for key in keys:
        if key in payload:
            parts.append(f"{key}={payload[key]}")
    if not parts:
        parts = [f"{key}={value}" for key, value in list(payload.items())[:4]]
    return "; ".join(parts) if parts else "暂无"


def expert_positions_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("当前没有持仓，资金仍在现金中。")
    return table(rows, ["asset", "quantity", "average_cost", "current_price", "price_date", "cost_basis", "market_value", "unrealized_pnl", "position_return"])


def expert_overview_investment_panel(rows: list[dict[str, Any]]) -> str:
    series = expert_return_series(rows)
    if not series:
        return empty("还没有专家组合估值；运行计划或评分后会显示专家收益对比。")
    return expert_comparison_curve(series)


def expert_return_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["expert_key"]
        group = grouped.setdefault(
            key,
            {
                "expert_key": key,
                "expert_name": row["expert_name"],
                "initial_capital": row["initial_capital"],
                "points": [],
            },
        )
        group["points"].append(dict(row))
    result = []
    for group in grouped.values():
        points = sorted(group["points"], key=lambda item: item["valuation_date"])
        initial_capital = group["initial_capital"] or (points[0]["total_value"] if points else None)
        if not initial_capital:
            continue
        returns = [
            {
                "valuation_date": point["valuation_date"],
                "cash": point["cash"],
                "positions_value": point["positions_value"],
                "total_value": point["total_value"],
                "return": _portfolio_return_from_values(initial_capital, point["total_value"]) or 0.0,
            }
            for point in points
            if point["total_value"] is not None
        ]
        if returns:
            result.append({**group, "points": returns})
    return sorted(result, key=lambda item: item["expert_name"])


def expert_comparison_curve(series: list[dict[str, Any]]) -> str:
    return_values = [float(point["return"]) for item in series for point in item["points"] if point["return"] is not None]
    if not return_values:
        return empty("还没有有效收益点。")
    low, high = _curve_domain(return_values, include_zero=True)
    dates = sorted({point["valuation_date"] for item in series for point in item["points"]})
    chart_data = {
        "dates": dates,
        "domain": {"low": round(low, 6), "high": round(high, 6)},
        "series": [
            {
                "name": item["expert_name"],
                "latestReturnLabel": plain_percent(item["points"][-1]["return"], signed=True),
                "points": [
                    {
                        "date": point["valuation_date"],
                        "returnValue": round(float(point["return"]), 6),
                        "returnLabel": plain_percent(point["return"], signed=True),
                        "totalValue": round(float(point["total_value"]), 4),
                        "totalLabel": _compact_money(float(point["total_value"])),
                        "isLatest": index == len(item["points"]) - 1,
                    }
                    for index, point in enumerate(item["points"])
                ],
            }
            for item in series
        ],
    }
    return f"""
    <div class="curve-card comparison-curve">
      <div class="curve-meta">
        <span>不同专家虚拟收益</span>
        <strong>{market_percent(max(return_values) if return_values else None)}</strong>
      </div>
      <div class="echarts-curve expert-comparison-echarts" data-echarts="expert-comparison" role="img" aria-label="专家收益对比曲线"></div>
      <script type="application/json" class="echarts-data">{json_for_script(chart_data)}</script>
    </div>
    """


def expert_return_curve(rows: list[dict[str, Any]], initial_capital: Any) -> str:
    if not rows or not initial_capital:
        return empty("还没有估值记录；运行计划或评分后会显示收益曲线。")
    valid_rows = [row for row in rows if row["total_value"] is not None]
    values = [float(row["total_value"]) for row in valid_rows]
    labels = [row["valuation_date"] for row in valid_rows]
    if not values:
        return empty("还没有有效估值记录。")
    returns = [(value / float(initial_capital)) - 1.0 for value in values]
    _, high = _curve_domain(values, include_zero=False)
    latest_return = returns[-1]
    chart_data = {
        "points": [
            {
                "date": label,
                "cashValue": round(float(row.get("cash") or 0), 4),
                "positionsValue": round(float(row.get("positions_value") or 0), 4),
                "totalValue": round(value, 4),
                "totalLabel": _compact_money(value),
                "returnValue": round(return_value, 6),
                "returnLabel": plain_percent(return_value, signed=True),
            }
            for row, label, value, return_value in zip(valid_rows, labels, values, returns)
        ],
        "domain": {"low": 0, "high": round(high, 4)},
    }
    return f"""
    <div class="curve-card compact-curve">
      <div class="curve-meta">
        <span>{escape(labels[0])} 至 {escape(labels[-1])}</span>
        <strong>{market_percent(latest_return)}</strong>
      </div>
      <div class="echarts-curve expert-return-echarts" data-echarts="expert-return" role="img" aria-label="专家总资产柱状图"></div>
      <script type="application/json" class="echarts-data">{json_for_script(chart_data)}</script>
    </div>
    """


def _curve_domain(values: list[float], *, include_zero: bool = True) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if include_zero:
        low = min(low, 0.0)
        high = max(high, 0.0)
    span = high - low
    if span <= 1e-12:
        base = max(abs(high), 1.0)
        padding = base * 0.01
        return low - padding, high + padding
    padding = max(span * 0.18, max(abs(low), abs(high), 0.01) * 0.04)
    return low - padding, high + padding


def _curve_date_domain(labels: list[str]) -> tuple[date | None, date | None]:
    dates = [_parse_iso_date(label) for label in labels]
    dates = [value for value in dates if value is not None]
    if not dates:
        return None, None
    return min(dates), max(dates)


def _curve_x(label: str, start: date | None, end: date | None, plot: dict[str, float]) -> float:
    if start is None or end is None or start == end:
        return (plot["left"] + plot["right"]) / 2
    value = _parse_iso_date(label)
    if value is None:
        return plot["left"]
    ratio = (value - start).days / max((end - start).days, 1)
    ratio = min(max(ratio, 0.0), 1.0)
    return plot["left"] + ratio * (plot["right"] - plot["left"])


def _curve_y(value: float, low: float, high: float, plot: dict[str, float]) -> float:
    span = high - low or 1.0
    ratio = (value - low) / span
    ratio = min(max(ratio, 0.0), 1.0)
    return plot["bottom"] - ratio * (plot["bottom"] - plot["top"])


def _curve_axis_markup(low: float, high: float, start: date | None, end: date | None, plot: dict[str, float]) -> str:
    mid = (low + high) / 2
    y_ticks = [high, mid, low]
    y_parts = []
    for value in y_ticks:
        y = _curve_y(value, low, high, plot)
        y_parts.append(f'<line class="grid-line" x1="{plot["left"]:.1f}" y1="{y:.1f}" x2="{plot["right"]:.1f}" y2="{y:.1f}"></line>')
        y_parts.append(f'<text class="axis-label y-label" x="{plot["left"] - 8:.1f}" y="{y + 4:.1f}">{escape(_compact_money(value))}</text>')
    x_parts = [
        f'<line class="axis-line" x1="{plot["left"]:.1f}" y1="{plot["bottom"]:.1f}" x2="{plot["right"]:.1f}" y2="{plot["bottom"]:.1f}"></line>',
        f'<line class="axis-line" x1="{plot["left"]:.1f}" y1="{plot["top"]:.1f}" x2="{plot["left"]:.1f}" y2="{plot["bottom"]:.1f}"></line>',
    ]
    if start and end:
        tick_dates = [start] if start == end else [start, start + (end - start) / 2, end]
        seen = set()
        for tick in tick_dates:
            if tick in seen:
                continue
            seen.add(tick)
            x = _curve_x(tick.isoformat(), start, end, plot)
            x_parts.append(f'<line class="tick-line" x1="{x:.1f}" y1="{plot["bottom"]:.1f}" x2="{x:.1f}" y2="{plot["bottom"] + 5:.1f}"></line>')
            x_parts.append(f'<text class="axis-label x-label" x="{x:.1f}" y="{plot["bottom"] + 20:.1f}">{escape(tick.strftime("%m-%d"))}</text>')
    return "".join(y_parts + x_parts)


def _compact_money(value: float) -> str:
    absolute = abs(value)
    if absolute >= 10000:
        return f"{value / 10000:.1f}万"
    return f"{value:.0f}"


def _parse_iso_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def _portfolio_return_from_values(initial_capital: Any, total_value: Any) -> float | None:
    if initial_capital is None or total_value is None or not float(initial_capital):
        return None
    return (float(total_value) / float(initial_capital)) - 1.0


def expert_lessons_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("还没有清退或招聘经验；专家需要足够成熟的评估窗口后才会写入 lessons。")
    cards = []
    for row in rows[:6]:
        cards.append(
            f"""
            <article class="lesson-card">
              <div>
                <b>{escape(row["expert_name"] or "系统")}</b>
                <span>{escape(row["lesson_date"])} · {escape(row["lesson_type"])}</span>
              </div>
              <p>{escape(row["summary"])}</p>
              <small>{escape(row["avoid_hiring_patterns"] or "暂无招聘规避模式。")}</small>
            </article>
            """
        )
    return '<div class="lesson-grid">' + "".join(cards) + "</div>"


def lifecycle_label(value: str) -> str:
    return {
        "active": "活跃",
        "candidate": "候选",
        "probation": "观察",
        "retired": "已清退",
    }.get(value, value)


def money(value: Any) -> str:
    if value is None:
        return "暂无"
    return f"¥{float(value):,.0f}"


def settings_form(values: dict[str, Any]) -> str:
    risk_options = "".join(
        f'<option value="{value}" {"selected" if values["risk_profile"] == value else ""}>{label}</option>'
        for value, label in [
            ("aggressive", "激进"),
            ("balanced", "中等"),
            ("conservative", "保守"),
        ]
    )
    return section(
        "活跃风险设置",
        f"""
        <form class="settings-form" method="get" action="/settings">
          <input type="hidden" name="save" value="1">
          <label>账户名称<input name="profile_name" value="{escape(values['profile_name'])}"></label>
          <label>风险偏好<select name="risk_profile">{risk_options}</select></label>
          <label>关注周期/天<input type="number" min="1" name="investment_horizon_days" value="{escape(values['investment_horizon_days'])}"></label>
          <label>权益上限<input type="number" min="0" max="1" step="0.01" name="max_equity_pct" value="{escape(values['max_equity_pct'])}"></label>
          <label>现金下限<input type="number" min="0" max="1" step="0.01" name="min_cash_pct" value="{escape(values['min_cash_pct'])}"></label>
          <label class="wide">备注<input name="notes" value="{escape(values.get('notes') or '')}"></label>
          <button type="submit">保存并设为活跃</button>
        </form>
        <p class="muted">保存后，下一次生成每日建议时会按该偏好选择关注周期，并约束权益/现金仓位区间。</p>
        """,
    )


def advice_summary(row: Any) -> str:
    return f"""
    <div class="summary">
      <h3>{escape(row['advice_date'])} Advice</h3>
      <p>{escape(row['market_summary'])}</p>
      <p class="muted">{escape(row['risk_warnings'])}</p>
    </div>
    """


def mini_bars(title: str, values: list[tuple[str, int]]) -> str:
    if not values:
        return empty("No asset coverage yet.")
    total = max(sum(value for _, value in values), 1)
    bars = "".join(
        f'<div class="bar-row"><span>{escape(label)}</span><div class="bar"><i style="width:{value / total * 100:.1f}%"></i></div><b>{value}</b></div>'
        for label, value in values
    )
    return f'<div class="mini-chart"><h3>{escape(title)}</h3>{bars}</div>'


def profile_panel(title: str, text: str) -> str:
    return f'<div class="profile"><h3>{escape(title)}</h3><p>{escape(text)}</p></div>'


def decode_metrics(row: Any) -> dict[str, Any]:
    result = dict(row)
    metrics = json.loads(result.get("metrics_json") or "{}")
    result.update(metrics)
    return result


def empty(message: str) -> str:
    return f'<div class="empty">{escape(message)}</div>'


MARKET_PERCENT_COLUMNS = {
    "pct_change",
    "return",
    "return_1d",
    "return_5d",
    "return_20d",
    "return_60d",
    "avg_return_20d",
    "expected_return",
    "expected_return_low",
    "expected_return_high",
    "downside_risk",
    "max_drawdown",
    "max_drawdown_60d",
    "portfolio_return",
    "benchmark_return",
    "benchmark_excess",
    "cash_drag",
    "current_return",
    "index_trend",
    "stock_bond_proxy",
}


MARKET_STAT_LABELS = ("收益", "回撤", "下行", "涨幅", "强弱")


def format_cell(value: Any, column: str | None = None, escape_value: bool = True) -> str:
    if value is None:
        return '<span class="muted">NULL</span>'
    if column in MARKET_PERCENT_COLUMNS:
        number = _coerce_market_number(value)
        if number is not None:
            return market_percent(number)
    if isinstance(value, float):
        return escape(f"{value:.6g}") if escape_value else f"{value:.6g}"
    text = str(value)
    if len(text) > 180:
        text = text[:177] + "..."
    return escape(text) if escape_value else text


def format_stat(value: Any, label: str | None = None) -> str:
    if value is None:
        return '<span class="muted">暂无</span>'
    if label and any(token in label for token in MARKET_STAT_LABELS):
        return market_percent(value)
    if isinstance(value, float):
        return escape(f"{value:.6g}")
    return escape(value)


def percent(value: Any) -> str:
    return plain_percent(value)


def plain_percent(value: Any, signed: bool = False) -> str:
    if value is None:
        return "暂无"
    number = float(value)
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.2%}"


def market_percent(value: Any) -> str:
    if value is None:
        return '<span class="muted">暂无</span>'
    number = float(value)
    if number > 0:
        state = "market-up"
        arrow = "↑"
        label = "上涨"
    elif number < 0:
        state = "market-down"
        arrow = "↓"
        label = "下跌"
    else:
        state = "market-flat"
        arrow = "→"
        label = "持平"
    return f'<span class="market-signal {state}" aria-label="{label} {escape(plain_percent(number, signed=True))}"><b>{arrow}</b>{escape(plain_percent(number, signed=True))}<small>{label}</small></span>'


def _coerce_market_number(value: Any) -> float | None:
    try:
        if isinstance(value, str):
            text = value.strip()
            if "<" in text or not text:
                return None
            if text.endswith("%"):
                return float(text.rstrip("%")) / 100.0
            return float(text)
        return float(value)
    except (TypeError, ValueError):
        return None


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


JS = """
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab-bar').forEach((bar) => {
    bar.addEventListener('click', (event) => {
      const link = event.target.closest('.tab-link[data-tab-target]');
      if (!link || !bar.contains(link)) {
        return;
      }
      const scope = link.closest('section') || document;
      const target = link.dataset.tabTarget;
      const targetPanel = scope.querySelector(`[data-tab-panel="${target}"]`);
      if (!target || !targetPanel) {
        return;
      }
      event.preventDefault();
      bar.querySelectorAll('.tab-link[data-tab-target]').forEach((item) => {
        const active = item === link;
        item.classList.toggle('active', active);
        item.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      scope.querySelectorAll('.tab-panel[data-tab-panel]').forEach((panel) => {
        panel.classList.toggle('active', panel === targetPanel);
      });
      if (link.dataset.tabUrl && window.history && window.history.replaceState) {
        window.history.replaceState(null, '', link.dataset.tabUrl);
      }
    });
  });
  const formatMoneyAxis = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return '-';
    }
    const absolute = Math.abs(number);
    if (absolute >= 10000) {
      return `${(number / 10000).toFixed(1).replace(/\\.0$/, '')}万`;
    }
    return Math.round(number).toLocaleString('zh-CN');
  };
  const formatCurrency = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return '-';
    }
    return `¥${Math.round(number).toLocaleString('zh-CN')}`;
  };
  const formatPercentAxis = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return '-';
    }
    return `${(number * 100).toFixed(2)}%`;
  };
  const formatDateTick = (value) => {
    const text = String(value || '');
    return text.length >= 10 ? text.slice(5, 10) : text;
  };
  const initExpertReturnChart = (node, payload) => {
    if (!window.echarts || !node || !payload || !Array.isArray(payload.points)) {
      if (node) {
        node.textContent = '图表组件加载失败，请检查网络后刷新页面。';
      }
      return;
    }
    const points = payload.points;
    const chart = window.echarts.init(node, null, { renderer: 'canvas' });
    const cashData = points.map((point) => ({
      value: point.cashValue || 0,
      totalValue: point.totalValue,
      returnLabel: point.returnLabel,
      date: point.date,
      isStackTop: !(point.positionsValue > 0)
    }));
    const positionsData = points.map((point) => ({
      value: point.positionsValue || 0,
      totalValue: point.totalValue,
      returnLabel: point.returnLabel,
      date: point.date,
      isStackTop: point.positionsValue > 0
    }));
    const topLabel = (params) => {
      const data = params.data || {};
      return data.isStackTop ? formatMoneyAxis(data.totalValue) : '';
    };
    chart.setOption({
      color: ['#f2c94c', '#0f766e', '#b91c1c'],
      legend: { top: 8, right: 18, itemWidth: 12, itemHeight: 8, textStyle: { color: '#607177' } },
      grid: { left: 58, right: 58, top: 68, bottom: points.length > 20 ? 58 : 38, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        confine: true,
        formatter: (items) => {
          const list = Array.isArray(items) ? items : [items];
          const data = list[0] && list[0].data ? list[0].data : {};
          const point = points.find((item) => item.date === data.date) || {};
          return [
            `<strong>${data.date || '-'}</strong>`,
            `现金：${formatCurrency(point.cashValue)}`,
            `投资：${formatCurrency(point.positionsValue)}`,
            `总资产：${formatCurrency(point.totalValue)}`,
            `收益：${point.returnLabel || '-'}`
          ].join('<br>');
        }
      },
      xAxis: {
        type: 'category',
        data: points.map((point) => point.date),
        axisTick: { alignWithLabel: true },
        axisLabel: { color: '#607177', formatter: formatDateTick },
        axisLine: { lineStyle: { color: '#8fa4aa' } }
      },
      yAxis: [
        {
          type: 'value',
          min: payload.domain ? payload.domain.low : null,
          max: payload.domain ? payload.domain.high : null,
          axisLabel: { color: '#607177', formatter: formatMoneyAxis },
          splitLine: { lineStyle: { color: '#c9d4d7', type: 'dashed' } },
          axisLine: { show: true, lineStyle: { color: '#8fa4aa' } }
        },
        {
          type: 'value',
          axisLabel: { color: '#9f1d1d', formatter: formatPercentAxis },
          splitLine: { show: false },
          axisLine: { show: true, lineStyle: { color: '#b91c1c' } }
        }
      ],
      dataZoom: points.length > 20 ? [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'slider', xAxisIndex: 0, height: 20, bottom: 12, borderColor: '#d7e0e3', fillerColor: 'rgba(15,118,110,.12)', handleStyle: { color: '#0f766e' } }
      ] : [],
      series: [
        {
          name: '现金',
          type: 'bar',
          stack: 'asset',
          barMaxWidth: 44,
          itemStyle: { borderRadius: [0, 0, 4, 4], opacity: 0.92 },
          label: { show: true, position: 'top', color: '#607177', fontWeight: 700, formatter: topLabel },
          data: cashData
        },
        {
          name: '投资',
          type: 'bar',
          stack: 'asset',
          barMaxWidth: 44,
          itemStyle: { borderRadius: [4, 4, 0, 0], opacity: 0.88 },
          label: { show: true, position: 'top', color: '#0f5f59', fontWeight: 700, formatter: topLabel },
          data: positionsData
        },
        {
          name: '收益',
          type: 'line',
          yAxisIndex: 1,
          symbol: 'circle',
          symbolSize: 7,
          lineStyle: { width: 3 },
          itemStyle: { color: '#b91c1c' },
          label: { show: true, position: 'top', distance: 8, color: '#b91c1c', fontWeight: 750, formatter: (params) => params.dataIndex === points.length - 1 && params.data && params.data.returnLabel ? params.data.returnLabel : '' },
          data: points.map((point) => ({
            value: point.returnValue,
            totalValue: point.totalValue,
            returnValue: point.returnValue,
            returnLabel: point.returnLabel,
            date: point.date
          }))
        }
      ]
    });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
  };
  const initExpertComparisonChart = (node, payload) => {
    if (!window.echarts || !node || !payload || !Array.isArray(payload.series)) {
      if (node) {
        node.textContent = '图表组件加载失败，请检查网络后刷新页面。';
      }
      return;
    }
    const chart = window.echarts.init(node, null, { renderer: 'canvas' });
    const comparisonRowsByDate = new Map();
    payload.series.forEach((item) => {
      (item.points || []).forEach((point) => {
        const rows = comparisonRowsByDate.get(point.date) || [];
        rows.push({
          expert: item.name,
          latestReturnLabel: item.latestReturnLabel || '',
          returnLabel: point.returnLabel || '-',
          totalValue: point.totalValue
        });
        comparisonRowsByDate.set(point.date, rows);
      });
    });
    chart.setOption({
      color: ['#0f766e', '#2563eb', '#a16207', '#b91c1c', '#6d28d9', '#475569'],
      legend: {
        type: 'scroll',
        top: 8,
        left: 12,
        right: 12,
        itemWidth: 16,
        itemHeight: 8,
        selectedMode: true,
        textStyle: { color: '#607177' }
      },
      grid: { left: 54, right: 28, top: 58, bottom: 40, containLabel: true },
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (items) => {
          const list = Array.isArray(items) ? items : [items];
          const date = list[0] && list[0].axisValue ? list[0].axisValue : '-';
          const rows = (comparisonRowsByDate.get(date) || []).map((row) => {
            return `${row.expert}：${row.returnLabel} · 总资产 ${formatCurrency(row.totalValue)}`;
          });
          return [`<strong>${date}</strong>`, ...rows].join('<br>');
        }
      },
      xAxis: {
        type: 'category',
        data: payload.dates || [],
        boundaryGap: false,
        axisTick: { alignWithLabel: true },
        axisLabel: { color: '#607177', formatter: formatDateTick },
        axisLine: { lineStyle: { color: '#8fa4aa' } }
      },
      yAxis: {
        type: 'value',
        min: payload.domain ? payload.domain.low : null,
        max: payload.domain ? payload.domain.high : null,
        axisLabel: { color: '#607177', formatter: formatPercentAxis },
        splitLine: { lineStyle: { color: '#c9d4d7', type: 'dashed' } },
        axisLine: { show: true, lineStyle: { color: '#8fa4aa' } }
      },
      series: payload.series.map((item) => ({
        name: `${item.name} ${item.latestReturnLabel || ''}`,
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 3 },
        label: {
          show: true,
          position: 'top',
          distance: 8,
          fontWeight: 750,
          formatter: (params) => params.data && params.data.isLatest ? params.data.returnLabel : ''
        },
        emphasis: { focus: 'series' },
        data: (item.points || []).map((point) => ({
          value: [point.date, point.returnValue],
          date: point.date,
          returnValue: point.returnValue,
          returnLabel: point.returnLabel,
          totalValue: point.totalValue,
          totalLabel: point.totalLabel,
          isLatest: point.isLatest
        }))
      }))
    });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
  };
  document.querySelectorAll('.echarts-curve[data-echarts="expert-return"]').forEach((node) => {
    const dataNode = node.parentElement ? node.parentElement.querySelector('script.echarts-data') : null;
    if (!dataNode) {
      return;
    }
    try {
      initExpertReturnChart(node, JSON.parse(dataNode.textContent || '{}'));
    } catch (error) {
      node.textContent = '图表数据解析失败。';
    }
  });
  document.querySelectorAll('.echarts-curve[data-echarts="expert-comparison"]').forEach((node) => {
    const dataNode = node.parentElement ? node.parentElement.querySelector('script.echarts-data') : null;
    if (!dataNode) {
      return;
    }
    try {
      initExpertComparisonChart(node, JSON.parse(dataNode.textContent || '{}'));
    } catch (error) {
      node.textContent = '图表数据解析失败。';
    }
  });
});
"""


CSS = """
:root{color-scheme:light;--bg:#f5f7f8;--panel:#ffffff;--ink:#1b2528;--muted:#637176;--line:#d7e0e3;--accent:#0f766e;--warn:#a16207;--bad:#b91c1c;--market-up:#b91c1c;--market-down:#0f766e;--market-flat:#637176}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}
.sidebar{background:#102326;color:#eef7f6;padding:18px 14px;position:sticky;top:0;height:100vh}.brand{display:flex;align-items:center;gap:10px;margin:4px 6px 20px;min-width:0}.brand strong{display:block;font-size:17px;line-height:1.15}.brand small{display:block;color:#9ec8c3;font-size:11px;margin-top:3px;white-space:nowrap}.brand-mark{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border:1px solid rgba(185,222,216,.55);border-radius:8px;background:#e3f4f1;box-shadow:0 6px 18px rgba(0,0,0,.18)}.brand-mark svg{width:34px;height:34px}.brand-mark text{font:bold 17px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#102326}.mark-orbit{fill:none;stroke:#93c5bd;stroke-width:2;stroke-linecap:round}.mark-line{fill:none;stroke:#0f766e;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}.mark-dot{fill:#b91c1c}
nav{display:grid;gap:5px}nav a{position:relative;color:#cfe4e1;text-decoration:none;padding:9px 10px 9px 13px;border-radius:6px}nav a.active,nav a:hover{background:#204346;color:#fff}nav a.active:before{content:"";position:absolute;left:5px;top:9px;bottom:9px;width:3px;border-radius:99px;background:#9ee2d8}
main{padding:22px;min-width:0}header{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--line)}h1{font-size:24px;margin:0}header p{margin:0;color:var(--muted);max-width:680px}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin:0 0 16px;padding:16px;box-shadow:0 1px 2px rgba(10,20,20,.04)}section h2{font-size:17px;margin:0 0 12px}
.stat-grid{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px}.stat{border:1px solid var(--line);border-radius:6px;padding:10px;background:#fbfdfd;min-height:72px}.stat span{display:block;color:var(--muted);font-size:12px}.stat strong{display:block;margin-top:8px;font-size:18px;overflow-wrap:anywhere}
.market-signal{display:inline-flex;align-items:baseline;gap:4px;font-weight:750;white-space:nowrap}.market-signal b{font-size:.92em}.market-signal small{font-size:11px;font-weight:650}.market-up{color:var(--market-up)}.market-down{color:var(--market-down)}.market-flat{color:var(--market-flat)}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse;min-width:760px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}th{background:#edf4f3;font-size:12px;color:#37474c;position:sticky;top:0}td{max-width:260px;overflow:hidden;text-overflow:ellipsis}
.toolbar{display:flex;gap:8px;margin-bottom:12px}select,button{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;padding:0 10px}button{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:650}
.settings-form,.filter-form{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:12px}.settings-form label,.filter-form label{display:grid;gap:6px;color:var(--muted);font-size:12px}.settings-form input,.settings-form select,.filter-form input,.filter-form select{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;padding:0 10px;color:var(--ink);font-size:14px}.settings-form .wide{grid-column:span 2}.filter-form .checkbox{display:flex;align-items:center;gap:8px;color:var(--ink);font-size:14px}.filter-form .checkbox input{height:auto}.notice{border:1px solid #b9ded8;background:#e3f4f1;color:#0f5f59;border-radius:6px;padding:10px;margin-bottom:12px;font-weight:650}.preset-bar,.tab-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.preset-link,.tab-link{border:1px solid var(--line);border-radius:6px;background:#fff;color:#0f5f59;text-decoration:none;padding:7px 10px;font:inherit;font-weight:650;cursor:pointer}.preset-link.active,.tab-link.active{background:#e3f4f1;border-color:#0f766e;color:#0f5f59}.tab-link{min-width:118px;text-align:center}.tab-link:hover{border-color:#95c9c3;background:#f1faf8}.tab-link:focus-visible{outline:2px solid #0f766e;outline-offset:2px}.tab-panel{display:none}.tab-panel.active{display:block}
.notice.warn{border-color:#e2c66f;background:#fffaf0;color:#7c4a03}.today-hero{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;border:1px solid #b9ded8;border-left:5px solid var(--accent);border-radius:8px;background:#fbfdfd;padding:16px}.today-hero span{display:block;color:var(--muted);font-size:12px}.today-hero h2{font-size:28px;line-height:1.2;margin:5px 0 8px;color:#0f5f59}.today-hero p{margin:0 0 8px;max-width:920px}.today-hero small{display:block;color:var(--muted)}.today-hero strong{flex:0 0 auto;background:#e3f4f1;color:#0f5f59;border:1px solid #b9ded8;border-radius:999px;padding:5px 10px}.jarvis-entry{display:flex;justify-content:space-between;gap:16px;align-items:center;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;background:#fbfdfd;padding:14px;color:var(--ink);text-decoration:none}.jarvis-entry:hover{border-color:#95c9c3;background:#f1faf8}.jarvis-entry span{display:block;color:var(--muted);font-size:12px}.jarvis-entry strong{display:block;margin-top:4px;font-size:22px;color:#0f5f59}.jarvis-entry b{color:#0f5f59}.jarvis-hero{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:14px;margin-bottom:12px}.jarvis-hero span{color:var(--muted);font-size:12px}.jarvis-hero h2{font-size:28px;margin:4px 0 8px}.jarvis-hero p{margin:0;max-width:920px}.jarvis-hero strong{background:#e3f4f1;color:#0f5f59;border:1px solid #b9ded8;border-radius:999px;padding:5px 10px}.jarvis-focus-grid{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:10px;margin-bottom:14px}.jarvis-focus-card{border:1px solid var(--line);border-radius:8px;background:#fff;padding:12px}.jarvis-focus-card span{display:block;color:var(--muted);font-size:12px}.jarvis-focus-card strong{display:block;margin:5px 0;font-size:18px;color:#0f5f59}.jarvis-focus-card p{margin:0}.jarvis-subsection{margin-top:16px}.jarvis-subsection h3{margin:0 0 8px;font-size:14px}.jarvis-expert-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}.jarvis-expert-card{display:block;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;background:#fbfdfd;padding:10px;color:var(--ink);text-decoration:none}.jarvis-expert-card:hover{border-color:#95c9c3;background:#f1faf8}.jarvis-expert-card p{margin:8px 0;color:var(--ink)}.jarvis-evidence-links{display:grid;grid-template-columns:repeat(5,minmax(110px,1fr));gap:10px}.jarvis-evidence-links a{border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:10px;color:var(--ink);text-decoration:none}.jarvis-evidence-links a:hover{border-color:#95c9c3;background:#f1faf8}.jarvis-evidence-links span{display:block;color:var(--muted);font-size:12px}.jarvis-evidence-links strong{display:block;margin-top:4px;color:#0f5f59;font-size:20px}
.dashboard-brief{display:grid;grid-template-columns:minmax(260px,1.05fr) minmax(320px,1fr);gap:12px;margin-bottom:14px}.dashboard-brief-main,.dashboard-brief-reasons{border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:14px}.dashboard-brief-main span,.dashboard-brief-main small{display:block;color:var(--muted);font-size:12px}.dashboard-brief-main h2{margin:4px 0 8px;font-size:24px;color:#0f5f59}.dashboard-brief-main p{margin:0 0 8px}.dashboard-brief-reasons strong{display:block;margin-bottom:8px}.dashboard-brief-reasons ol{margin:0;padding-left:20px}.dashboard-brief-reasons li{margin:5px 0}.run-health h3{margin:0 0 8px;font-size:14px}.run-health-grid{display:grid;grid-template-columns:repeat(4,minmax(170px,1fr));gap:10px}.run-health-card{border:1px solid var(--line);border-radius:8px;background:#fff;padding:10px;min-height:142px}.run-health-card div{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.run-health-card span,.run-health-card small{color:var(--muted);font-size:12px}.run-health-card strong{color:#0f5f59}.run-health-card p{margin:8px 0;color:var(--ink)}.run-health-card em{display:block;color:var(--muted);font-style:normal;font-size:12px}.run-health-card.ok{border-color:#b9ded8}.run-health-card.warn{border-color:#e2c66f;background:#fffaf0}.run-health-card.bad,.run-health-card.missing{border-color:#efb4b4;background:#fff8f8}.run-health-card.bad strong,.run-health-card.missing strong{color:var(--bad)}
.score-card-grid,.evidence-chip-grid,.failure-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.score-card,.evidence-chip,.failure-card{border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px;color:var(--ink);text-decoration:none}.score-card div,.failure-card div{display:flex;justify-content:space-between;gap:10px}.score-card span,.score-card small,.score-card em,.evidence-chip span,.evidence-chip small,.failure-card span,.failure-card em{display:block;color:var(--muted);font-size:12px;font-style:normal}.score-card strong,.evidence-chip strong,.failure-card strong{display:block;color:#0f5f59;font-size:20px}.score-card p,.failure-card p{margin:8px 0}.score-card.warn,.score-card.missing{border-color:#e2c66f;background:#fffaf0}.evidence-chip:hover{border-color:#95c9c3;background:#f1faf8}.failure-card{border-color:#efb4b4;background:#fff8f8}.failure-card strong{font-size:15px;color:var(--bad)}.link-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}.link-grid a{border:1px solid var(--line);border-radius:6px;background:#fbfdfd;color:#0f5f59;text-decoration:none;padding:10px;font-weight:700}.link-grid a:hover{border-color:#95c9c3;background:#f1faf8}
.summary,.mini-chart,.recommendations{margin-top:14px}.mini-chart h3,.summary h3,.profile h3,.advice-block h3,.recommendations h3{margin:0 0 8px;font-size:14px}.bar-row{display:grid;grid-template-columns:90px minmax(120px,1fr) 42px;gap:10px;align-items:center;margin:8px 0}.bar{height:10px;background:#e5ecee;border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.recommendations{display:grid;gap:8px}.recommendation{display:grid;grid-template-columns:minmax(160px,1fr) 100px minmax(260px,1.2fr);gap:12px;align-items:center;border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:10px;color:var(--ink);text-decoration:none}.recommendation:hover{border-color:#95c9c3;background:#f1faf8}.recommendation span,.recommendation small{display:block;color:var(--muted)}.recommendation strong{font-size:18px;color:#0f5f59}.history-list{margin-top:16px}.history-list h3{margin:0 0 8px;font-size:14px}
.asset-prediction-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px}.asset-prediction-card{display:block;border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px;color:var(--ink);text-decoration:none}.asset-prediction-card:hover{border-color:#95c9c3;background:#f1faf8}.asset-prediction-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}.asset-prediction-head h3{margin:0;font-size:16px}.asset-prediction-head span{display:block;color:var(--muted);font-size:12px}.agreement{flex:0 0 auto;border-radius:999px;padding:3px 8px;font-size:12px;background:#eef3f4;color:var(--muted);border:1px solid var(--line)}.agreement.positive{background:#fff1f1;color:var(--market-up);border-color:#efb4b4}.agreement.negative{background:#eefaf7;color:var(--market-down);border-color:#b9ded8}.agreement.risk{background:#fffaf0;color:var(--warn);border-color:#e2c66f}.horizon-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.horizon-signal{border:1px solid var(--line);border-radius:6px;background:#fff;padding:8px;min-width:0}.horizon-signal span,.horizon-signal small{display:block;color:var(--muted);font-size:12px}.horizon-signal strong{display:block;margin:4px 0;overflow-wrap:anywhere}.horizon-signal.missing{background:#fafcfc}
.category-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:10px}.category-grid.compact{grid-template-columns:repeat(6,minmax(120px,1fr))}.category-card{display:grid;gap:6px;min-height:132px;border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px;color:var(--ink);text-decoration:none}.category-card:hover,.category-card.active{border-color:#95c9c3;background:#f1faf8}.category-card span{color:var(--muted);font-size:12px}.category-card strong{font-size:24px;color:#0f5f59}.category-card em{font-style:normal;color:#37474c}.category-card small{color:var(--muted)}.category-context{margin-top:12px}.technical-details summary{cursor:pointer;color:#0f5f59;font-weight:700;margin-bottom:10px}.technical-details[open] summary{margin-bottom:12px}
.expert-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:12px}.expert-card{display:block;min-width:0;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;background:#fbfdfd;padding:10px;color:var(--ink);text-decoration:none}.expert-card:hover{border-color:#95c9c3;background:#f1faf8}.expert-card.state-probation{border-left-color:var(--warn);background:#fffaf0}.expert-card.state-retired{border-left-color:var(--bad);background:#fff8f8}.expert-card-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.expert-card-metrics span{border:1px solid var(--line);border-radius:6px;background:#fff;padding:7px;min-width:0}.expert-card-metrics small{display:block;color:var(--muted);font-size:11px}.expert-card-metrics b{display:block;margin-top:3px;font-size:15px;overflow-wrap:anywhere}.detail-link{display:inline-block;margin-top:8px;color:#0f5f59;font-weight:700}.expert-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.expert-head h3{margin:0;font-size:16px}.expert-head span{display:block;color:var(--muted);font-size:12px}.expert-head b{flex:0 0 auto;background:var(--accent);color:#fff;border-radius:999px;padding:2px 7px;font-size:12px}.state-probation .expert-head b{background:var(--warn)}.state-retired .expert-head b{background:var(--bad)}
.expert-detail-list{display:grid;gap:14px}.expert-detail{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;background:#fbfdfd;padding:14px;min-width:0}.expert-detail.state-probation{border-left-color:var(--warn);background:#fffaf0}.expert-detail.state-retired{border-left-color:var(--bad);background:#fff8f8}.expert-detail-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}.expert-detail-head h3{margin:0;font-size:18px}.expert-detail-head span{display:block;color:var(--muted);font-size:12px}.expert-detail-head strong{color:#0f5f59;font-size:22px}.expert-detail .stat-grid{grid-template-columns:repeat(4,minmax(120px,1fr));margin-bottom:12px}.expert-detail-grid{display:grid;grid-template-columns:1.1fr 1fr 1.1fr 1.2fr;gap:12px}.expert-subpanel{min-width:0;border:1px solid var(--line);border-radius:6px;background:#fff;padding:10px}.expert-subpanel h4{margin:0 0 8px;font-size:13px;color:#37474c}.expert-subpanel .table-wrap table{min-width:520px}.expert-plan-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.expert-plan-summary div{border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:8px;min-width:0}.expert-plan-summary span{display:block;color:var(--muted);font-size:12px}.expert-plan-summary strong{display:block;margin-top:4px;overflow-wrap:anywhere}.expert-plan-summary p{grid-column:1/-1;margin:0;color:var(--ink)}.expert-timeline{list-style:none;margin:0;padding:0;display:grid;gap:8px}.expert-timeline li{display:grid;gap:2px;border-left:3px solid #b9ded8;padding-left:8px}.expert-timeline time,.expert-timeline span{color:var(--muted);font-size:12px}.expert-timeline b{font-size:13px}.lesson-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}.lesson-card{border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px}.lesson-card div{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.lesson-card span,.lesson-card small{display:block;color:var(--muted);font-size:12px}.lesson-card p{margin:8px 0}.compact-curve{padding:10px}.expert-curve{height:180px}.curve circle{fill:#0f766e;stroke:#fff;stroke-width:2}
.expert-detail-page section h3{font-size:14px;margin:12px 0 8px}.expert-detail-page td{white-space:normal;overflow:visible;text-overflow:clip;max-width:520px}.expert-profile-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:12px}.expert-profile-head h3{font-size:22px;margin:0}.expert-profile-head span{display:block;color:var(--muted);margin-top:2px}.expert-profile-head p{margin:8px 0 0;max-width:760px}.expert-profile-head strong{color:#0f5f59;font-size:24px}
.timeline{display:grid;gap:12px}.timeline.compact{gap:8px}.timeline-card{border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px}.timeline-date{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}.timeline-date strong{font-size:18px;color:#0f5f59}.timeline-date span{color:var(--muted);text-align:right}.timeline-grid{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:8px}.timeline-state{border:1px solid var(--line);border-radius:6px;background:#fff;padding:10px;min-height:104px}.timeline-state span,.timeline-state small{display:block;color:var(--muted);font-size:12px}.timeline-state strong{display:block;margin:6px 0;color:var(--ink);overflow-wrap:anywhere}.timeline-state a{color:#0f5f59;font-weight:700;text-decoration:none}.timeline-state.ok{border-color:#b9ded8}.timeline-state.warn{border-color:#e2c66f;background:#fffaf0}.timeline-state.bad,.timeline-state.missing{border-color:#efb4b4;background:#fff8f8}.timeline-state.bad strong,.timeline-state.missing strong{color:var(--bad)}
.curve-card{border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:12px;position:relative}.curve-controls{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px}.range-chips{display:flex;gap:6px;flex-wrap:wrap}.range-chip{border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--muted);padding:6px 10px;font-size:13px;text-decoration:none}.range-chip.active{border-color:#0f766e;background:#e3f4f1;color:#0f5f59;font-weight:700}.range-form{display:flex;align-items:end;gap:8px;flex-wrap:wrap}.range-form label{display:grid;gap:3px;color:var(--muted);font-size:12px}.range-form input{border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit;min-width:136px}.range-form button{padding:7px 12px}.curve-meta{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--muted)}.curve-meta strong{color:#0f5f59;font-size:20px}.curve,.echarts-curve{display:block;width:100%;height:260px;background:#fff;border:1px solid var(--line);border-radius:6px}.echarts-curve{padding:4px}.expert-return-echarts{height:260px}.expert-comparison-echarts{height:300px}.curve line{stroke:#c9d4d7;stroke-width:1}.curve .grid-line{stroke-dasharray:4 4}.curve .zero-line{stroke:#9fb3b8;stroke-dasharray:6 5}.curve .axis-line,.curve .tick-line{stroke:#8fa4aa;stroke-dasharray:none}.axis-label{fill:#607177;font-size:12px}.y-label{text-anchor:end}.x-label{text-anchor:middle}.bar-return-label{fill:#0f5f59;font-size:12px;font-weight:700;text-anchor:middle}.asset-bar{fill:#0f766e;opacity:.86}.curve polyline{fill:none;stroke:#0f766e;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}.curve-point{pointer-events:none}.curve .point-dot{fill:#0f766e;stroke:#fff;stroke-width:2;opacity:0}.curve .point-guide{stroke:#0f766e;stroke-width:1;stroke-dasharray:3 4;opacity:0}.curve-point:hover .point-dot,.curve-point:focus .point-dot,.curve-point.selected .point-dot{opacity:1}.curve-point:hover .point-guide,.curve-point:focus .point-guide,.curve-point.selected .point-guide{opacity:.55}.curve-capture{fill:transparent;stroke:none;cursor:crosshair}.curve-capture:focus{outline:none}.curve-tooltip{position:absolute;z-index:4;display:none;min-width:150px;border:1px solid #b9ded8;border-radius:6px;background:#ffffff;box-shadow:0 10px 24px rgba(15,35,38,.16);padding:9px 10px;pointer-events:none}.curve-tooltip.visible{display:grid;gap:4px}.curve-tooltip strong{font-size:15px;color:var(--ink)}.curve-tooltip span{color:var(--muted);font-size:12px}.curve-tooltip b{color:#0f5f59;font-size:13px}.expert-series-line{stroke-width:3}.curve-legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}.curve-legend span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:12px}.curve-legend i{display:inline-block;width:10px;height:10px;border-radius:999px}
.advice-block{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}.advice-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.advice-head h2{margin:0}.badge{background:#e3f4f1;color:#0f5f59;border:1px solid #b9ded8;border-radius:999px;padding:3px 8px;font-weight:700}.profile-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:12px}.profile{border:1px solid var(--line);border-radius:6px;padding:12px;background:#fbfdfd}pre{white-space:pre-wrap;background:#0f1f22;color:#dcefed;border-radius:6px;padding:12px;overflow:auto}
.empty{border:1px dashed var(--line);border-radius:6px;padding:18px;color:var(--muted);background:#fafcfc}.muted{color:var(--muted)}
@media(max-width:1180px){.expert-detail-grid{grid-template-columns:1fr 1fr}.expert-detail .stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:860px){body{display:block}.sidebar{position:static;height:auto}.brand{margin-bottom:10px}.brand small{white-space:normal}nav{display:flex;overflow-x:auto}nav a{white-space:nowrap}nav a.active:before{left:10px;right:10px;top:auto;bottom:3px;width:auto;height:3px}main{padding:14px}header{display:block}header p{margin-top:6px}.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.profile-grid,.settings-form,.filter-form,.timeline-grid,.category-grid,.category-grid.compact,.expert-grid,.expert-detail-grid,.jarvis-focus-grid,.jarvis-evidence-links,.asset-prediction-grid,.dashboard-brief,.run-health-grid{grid-template-columns:1fr}.timeline-date{display:block}.timeline-date span{text-align:left;display:block;margin-top:4px}.settings-form .wide{grid-column:auto}section{padding:12px}.bar-row{grid-template-columns:78px minmax(90px,1fr) 32px}.recommendation{grid-template-columns:1fr}.horizon-grid{grid-template-columns:1fr}.curve,.echarts-curve{height:180px}.expert-return-echarts{height:230px}.expert-comparison-echarts{height:260px}.expert-plan-summary{grid-template-columns:1fr}.jarvis-entry,.jarvis-hero,.today-hero{display:block}.jarvis-hero h2,.today-hero h2{font-size:24px}.today-hero strong{display:inline-block;margin-top:10px}table{min-width:680px}}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    run_web_server(args.db, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
