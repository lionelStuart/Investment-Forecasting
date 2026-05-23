from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from investment_forecasting.db import active_user_preference, connect, init_db, list_user_preferences, upsert_user_preference


NAV_ITEMS = [
    ("/", "总览"),
    ("/timeline", "研究时间线"),
    ("/categories", "产品分类"),
    ("/data", "数据与曲线"),
    ("/funds", "基金筛选"),
    ("/predictions", "预测"),
    ("/backtests", "回测评分"),
    ("/advice", "每日建议"),
    ("/experts", "专家委员会"),
    ("/settings", "风险设置"),
    ("/logs", "任务日志"),
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
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return WorkbenchHandler


def render_route(db_path: Path, path: str, query: dict[str, list[str]]) -> str:
    routes = {
        "/": render_dashboard,
        "/timeline": render_timeline,
        "/categories": render_categories,
        "/data": render_data,
        "/funds": render_funds,
        "/predictions": render_predictions,
        "/backtests": render_backtests,
        "/advice": render_advice,
        "/experts": render_experts,
        "/settings": render_settings,
        "/logs": render_logs,
    }
    if path not in routes:
        raise KeyError(path)
    return routes[path](db_path, query)


def render_dashboard(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        latest_advice = conn.execute("SELECT * FROM daily_advice ORDER BY advice_date DESC, id DESC LIMIT 1").fetchone()
        latest_log = conn.execute("SELECT * FROM task_logs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
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
        assets = build_category_summaries(conn)
        recommendations = latest_recommendations(conn, limit=8)
        timeline_rows = build_timeline_rows(conn, limit=3)
    body = section("数据状态", data_status_panel(data_status))
    body += section("研究时间线", timeline_preview(timeline_rows))
    body += section(
        "市场状态",
        stat_grid(
            [
                ("风险等级", latest_advice["risk_level"] if latest_advice else "暂无建议"),
                ("活跃偏好", preference["profile_name"] if preference else "默认"),
                ("预测日期", prediction_summary["prediction_date"] or "暂无预测"),
                ("平均预期收益", percent(prediction_summary["avg_expected_return"])),
                ("平均下行风险", percent(prediction_summary["avg_downside_risk"])),
                ("平均置信度", percent(prediction_summary["avg_confidence"])),
                ("最近任务", latest_log["status"] if latest_log else "暂无日志"),
            ]
        )
        + (
            stat_grid(
                [
                    ("市场情绪", environment["sentiment"]),
                    ("上涨宽度", percent(environment["breadth"])),
                    ("成交热度", environment["liquidity_heat"]),
                    ("股债强弱", percent(environment["stock_bond_proxy"])),
                    ("快照日期", environment["snapshot_date"]),
                    ("数据来源", environment["source"]),
                ]
            )
            if environment
            else empty("还没有计算市场环境快照。")
        )
        + category_nav_panel(assets, compact=True)
        + recommendation_panel(recommendations)
        + (advice_summary(latest_advice) if latest_advice else empty("还没有生成每日建议。")),
    )
    return render_page("总览", body, "/")


def render_timeline(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        rows = build_timeline_rows(conn, limit=12)
    body = timeline_panel(rows)
    return render_page("研究时间线", section("连续研究记录", body), "/timeline")


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


def render_data(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        assets = conn.execute("SELECT * FROM assets ORDER BY asset_type, code").fetchall()
        selected_id = int(query.get("asset_id", [assets[0]["id"] if assets else 0])[0] or 0)
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
            ORDER BY trade_date DESC
            LIMIT 120
            """,
            (selected_id,),
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
    selector = asset_selector(assets, selected_id, "/data")
    chart_rows = list(reversed(history))
    body = section("资产概览", selector + selected_asset_summary(selected_asset, selected_prediction, category) + category_context_panel(category, peers))
    body += section("涨幅曲线", return_curve(chart_rows))
    body += section("行情 / 净值历史", table(history, ["trade_date", "close", "adjusted_close", "nav", "volume", "amount", "pct_change", "source"]))
    body += section("量化指标", table(features, ["feature_date", "return_1d", "return_20d", "volatility_20d", "max_drawdown_60d", "sharpe_60d", "calmar_60d", "win_rate_60d", "market_state", "source"]))
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
    filtered = filter_funds(funds, filters)
    body = fund_filter_panel(filters, funds, active_preference)
    body += section("筛选结果", fund_results_panel(filtered, funds, filters))
    body += section("技术明细", collapsible("原始基金字段", table(fund_display_rows(filtered), ["code", "name", "fund_type", "manager", "scale", "purchase_fee", "feature_date", "return_20d", "max_drawdown_60d", "sharpe_60d", "win_rate_60d", "market_state", "explanation"], escape_cells=False)))
    return render_page("基金筛选", body, "/funds")


def render_predictions(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.asset_id, a.code, a.name, a.asset_type, p.prediction_date, p.horizon_days,
                   p.up_probability, p.expected_return, p.expected_return_low,
                   p.expected_return_high, p.downside_risk, p.confidence,
                   p.model_version, p.input_window_start, p.input_window_end
            FROM model_predictions p
            LEFT JOIN assets a ON a.id = p.asset_id
            ORDER BY p.prediction_date DESC, a.code, p.horizon_days
            LIMIT 300
            """
        ).fetchall()
    body = section("近期关注标的", recommendation_panel(rows[:12]))
    body += section("模型预测", table(rows, ["id", "code", "name", "prediction_date", "horizon_days", "up_probability", "expected_return", "expected_return_low", "expected_return_high", "downside_risk", "confidence", "model_version", "input_window_start", "input_window_end"]))
    return render_page("预测", body, "/predictions")


def render_backtests(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
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
    body = section("回测任务", table(run_rows, ["id", "model_version", "asset_scope", "start_date", "end_date", "horizon_days", "count", "direction_accuracy", "mean_return_error", "risk_hit_rate", "mean_overall_score"]))
    body += section("历史预测评分", table(results, ["id", "run_id", "code", "prediction_date", "horizon_days", "predicted_return", "actual_return", "predicted_direction", "actual_direction", "prediction_score", "risk_score", "advice_score", "overall_score"]))
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
          {recommendation_panel(allocation.get('focus_assets', []))}
          <pre>{escape(json.dumps(allocation.get('evidence', {}), ensure_ascii=False, indent=2))}</pre>
        </article>
        """
    body = advice_selector(history, selected_id)
    body += content or empty("还没有建议记录。")
    body += advice_history_table(history)
    return render_page("每日建议", section("每日建议", body), "/advice")


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

    form_values = dict(active) if active else {
        "profile_name": "默认账户",
        "risk_profile": "balanced",
        "investment_horizon_days": 20,
        "max_equity_pct": 0.6,
        "min_cash_pct": 0.1,
        "notes": "",
    }
    body = saved_message + settings_form(form_values)
    body += section(
        "已保存设置",
        table(preferences, ["profile_name", "risk_profile", "investment_horizon_days", "max_equity_pct", "min_cash_pct", "is_active", "updated_at"]),
    )
    return render_page("风险设置", body, "/settings")


def render_experts(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        experts = expert_overview_rows(conn)
        plans = latest_expert_plans(conn)
        lessons = expert_lesson_rows(conn)
        equity_rows = expert_equity_rows(conn)
        raw_scorecards = conn.execute(
            """
            SELECT id, expert_id, score_date, window_days, valuation_count,
                   mature_enough, portfolio_return, benchmark_excess,
                   max_drawdown, cash_drag, turnover, overall_score
            FROM expert_scorecards
            ORDER BY score_date DESC, id DESC
            LIMIT 80
            """
        ).fetchall()
        raw_reviews = conn.execute(
            """
            SELECT id, expert_id, review_date, decision, previous_lifecycle_state,
                   new_lifecycle_state, rationale
            FROM expert_reviews
            ORDER BY review_date DESC, id DESC
            LIMIT 80
            """
        ).fetchall()
    if not experts:
        body = section("专家委员会", empty("还没有专家记录；请先运行 experts init。"))
        return render_page("专家委员会", body, "/experts")
    body = section("专家委员会", expert_cards(experts))
    body += section("最新计划与执行", expert_plan_table(plans))
    body += section("权益曲线与基准", expert_equity_panel(equity_rows))
    body += section("复盘与经验", expert_lessons_panel(lessons))
    body += section(
        "技术明细",
        collapsible("原始评分记录", table(raw_scorecards, ["id", "expert_id", "score_date", "window_days", "valuation_count", "mature_enough", "portfolio_return", "benchmark_excess", "max_drawdown", "cash_drag", "turnover", "overall_score"]))
        + collapsible("原始复盘记录", table(raw_reviews, ["id", "expert_id", "review_date", "decision", "previous_lifecycle_state", "new_lifecycle_state", "rationale"])),
    )
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
    return render_page("任务日志", section("任务日志", table(rows, ["id", "task_name", "run_date", "started_at", "finished_at", "status", "duration_ms", "message", "error"])), "/logs")


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
</head>
<body>
  <aside class="sidebar">
    <div class="brand">投资预测工作台</div>
    <nav>{nav}</nav>
  </aside>
  <main>
    <header><h1>{escape(title)}</h1><p>本地投资研究工作台：用入库数据、涨幅曲线、模型预测和回测评分辅助判断，不承诺收益。</p></header>
    {body}
  </main>
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
            latest_macro = _max_value(conn, "macro_observations", "observation_date")
            latest_snapshot = _max_value(conn, "market_snapshots", "snapshot_date")
            summaries.append(
                {
                    **category,
                    "count": snapshot_count + macro_count,
                    "asset_count": 0,
                    "latest_date": latest_snapshot or latest_macro,
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
    filtered = [dict(row) | {"category": asset_category(row)["label"]} for row in rows if asset_category(row)["key"] == category_key]
    return filtered[:limit]


def category_nav_panel(summaries: list[dict[str, Any]], compact: bool = False) -> str:
    if not summaries:
        return empty("还没有可分类的资产。")
    cards = "".join(category_card(item, compact=compact) for item in summaries)
    return f'<div class="category-grid {"compact" if compact else ""}">{cards}</div>'


def category_card(item: dict[str, Any], compact: bool = False) -> str:
    metrics = "" if compact else (
        f'<small>最新 {escape(item["latest_date"] or "暂无")} · 20日均值 {escape(percent(item["avg_return_20d"]))} · 回撤 {escape(percent(item["avg_drawdown_60d"]))}</small>'
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
                ("20日收益均值", percent(item["avg_return_20d"])),
                ("60日回撤均值", percent(item["avg_drawdown_60d"])),
            ]
        )
        + f'<p class="muted">{escape(item["description"])}</p>'
    )


def category_asset_table(category: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if category["key"] == "market_indicator":
        return empty("宏观/市场指标暂通过总览和研究时间线查看；后续会拆成独立指标页。")
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
        ["code", "name", "asset_type", "feature_date", "return_20d", "max_drawdown_60d", "sharpe_60d", "market_state", "expected_return", "up_probability", "confidence"],
        escape_cells=False,
    )


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
        if filters.get("fund_type") and filters["fund_type"] not in str(item.get("fund_type") or ""):
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
    return f'<p class="muted">{escape(explanation)}</p>' + table(top, ["code", "name", "fund_type", "manager", "scale", "purchase_fee", "return_20d", "max_drawdown_60d", "sharpe_60d", "win_rate_60d", "market_state", "explanation"], escape_cells=False)


def fund_display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    display = []
    for row in rows:
        display.append(
            {
                **row,
                "code": f'<a href="/data?asset_id={row["id"]}">{escape(row["code"])}</a>',
                "fund_type": escape(row.get("fund_type") or "基金类型待补充"),
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
        notes.append(f"20日收益 {percent(row['return_20d'])}")
    else:
        notes.append("20日收益样本不足")
    if row.get("max_drawdown_60d") is not None:
        notes.append(f"60日回撤 {percent(row['max_drawdown_60d'])}")
    else:
        notes.append("回撤数据待补充")
    if row.get("sharpe_60d") is not None:
        notes.append(f"Sharpe {format_stat(row['sharpe_60d'])}")
    if row.get("purchase_fee") is None:
        notes.append("费率数据待补充")
    if filters.get("preset") in FUND_PRESETS:
        notes.append(f"匹配{FUND_PRESETS[filters['preset']]['label']}预设")
    return "；".join(notes)


def select_options(values: list[str], selected: Any) -> str:
    return "".join(f'<option value="{escape(value)}" {"selected" if value == selected else ""}>{escape(value)}</option>' for value in values)


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
    prediction_text = "暂无预测"
    if prediction:
        prediction_text = f"{prediction['horizon_days']}日 {percent(prediction['expected_return'])} / 上涨 {percent(prediction['up_probability'])}"
    return stat_grid(
        [
            ("代码", asset["code"]),
            ("名称", asset["name"]),
            ("分类", category["label"]),
            ("最新指标", asset["feature_date"] or "暂无"),
            ("20日收益", percent(asset["return_20d"])),
            ("60日回撤", percent(asset["max_drawdown_60d"])),
            ("夏普", asset["sharpe_60d"]),
            ("市场状态", asset["market_state"] or "暂无"),
            ("最新预测", prediction_text),
        ]
    )


def category_context_panel(category: dict[str, str], peers: list[dict[str, Any]]) -> str:
    rows = [
        {
            **row,
            "code": f'<a href="/data?asset_id={row["id"]}">{escape(row["code"])}</a>',
        }
        for row in peers
    ]
    content = f'<p class="muted">当前分类：<a href="/categories?category={escape(category["key"])}">{escape(category["label"])}</a>。{escape(category["description"])}</p>'
    content += table(rows, ["code", "name", "return_20d", "max_drawdown_60d", "expected_return", "confidence"], escape_cells=False) if rows else empty("当前分类暂无同类资产。")
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
        "features_daily": _count_rows(conn, "features_daily"),
        "model_predictions": _count_rows(conn, "model_predictions"),
        "daily_advice": _count_rows(conn, "daily_advice"),
        "market_snapshots": _count_rows(conn, "market_snapshots"),
        "macro_observations": _count_rows(conn, "macro_observations"),
    }
    latest = {
        "price_date": _max_value(conn, "price_daily", "trade_date"),
        "feature_date": _max_value(conn, "features_daily", "feature_date"),
        "prediction_date": _max_value(conn, "model_predictions", "prediction_date"),
        "advice_date": _max_value(conn, "daily_advice", "advice_date"),
    }
    return {"db_path": str(db_path), "counts": counts, "latest": latest}


def data_status_panel(status: dict[str, Any]) -> str:
    counts = status["counts"]
    latest = status["latest"]
    summary = stat_grid(
        [
            ("资产", counts["assets"]),
            ("行情/净值", counts["price_daily"]),
            ("预测", counts["model_predictions"]),
            ("每日建议", counts["daily_advice"]),
            ("最新行情", latest["price_date"] or "暂无"),
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
    content = f'<a href="/predictions">{count} 条</a><small>平均收益 {escape(percent(predictions.get("avg_expected_return")))} · 置信度 {escape(percent(predictions.get("avg_confidence")))}</small>'
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
               (COALESCE(p.expected_return, 0) * 0.5
                + COALESCE(p.up_probability, 0) * 0.2
                + COALESCE(p.confidence, 0) * 0.2
                + COALESCE(p.downside_risk, 0) * 0.1) AS recommendation_score
        FROM model_predictions p
        LEFT JOIN assets a ON a.id = p.asset_id
        WHERE p.prediction_date = (SELECT MAX(prediction_date) FROM model_predictions)
          AND p.horizon_days = 20
        ORDER BY recommendation_score DESC, p.expected_return DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def stat_grid(items: list[tuple[str, Any]]) -> str:
    return '<div class="stat-grid">' + "".join(f'<div class="stat"><span>{escape(label)}</span><strong>{format_stat(value)}</strong></div>' for label, value in items) + "</div>"


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
          <strong>{escape(percent(item['expected_return']))}</strong>
          <small>{escape(item['horizon_days'])}日预期 · 上涨概率 {escape(percent(item['up_probability']))} · 下行 {escape(percent(item['downside_risk']))} · 置信度 {escape(percent(item['confidence']))}</small>
        </{tag}>
        """


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
    }


def _safe_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key] if key in row.keys() else None


def _first_query_value(query: dict[str, list[str]], key: str, default: Any = None) -> Any:
    values = query.get(key)
    return values[0] if values else default


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


def return_curve(rows: Any) -> str:
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
    width = 720
    height = 220
    points = []
    for index, value in enumerate(returns):
        x = index / max(len(returns) - 1, 1) * width
        y = height - ((value - low) / span * height)
        points.append(f"{x:.1f},{y:.1f}")

    latest_return = returns[-1]
    start_label = labels[0] or ""
    end_label = labels[-1] or ""
    return f"""
    <div class="curve-card">
      <div class="curve-meta">
        <span>{escape(start_label)} 至 {escape(end_label)}</span>
        <strong>{escape(percent(latest_return))}</strong>
      </div>
      <svg class="curve" viewBox="0 0 {width} {height}" role="img" aria-label="涨幅曲线">
        <line x1="0" y1="{height - ((0 - low) / span * height):.1f}" x2="{width}" y2="{height - ((0 - low) / span * height):.1f}"></line>
        <polyline points="{' '.join(points)}"></polyline>
      </svg>
    </div>
    """


def table(rows: Any, columns: list[str], escape_cells: bool = True) -> str:
    rows = list(rows)
    if not rows:
        return empty("No records available.")
    head = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(
            f"<td>{format_cell(row[column] if column in row.keys() else row.get(column), escape_value=escape_cells)}</td>"
            for column in columns
        ) + "</tr>"
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def asset_selector(assets: Any, selected_id: int, path: str) -> str:
    options = "".join(
        f'<option value="{asset["id"]}" {"selected" if asset["id"] == selected_id else ""}>{escape(asset["code"])} · {escape(asset["name"])}</option>'
        for asset in assets
    )
    return f'<form class="toolbar" method="get" action="{path}"><select name="asset_id">{options}</select><button type="submit">查看</button></form>'


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
        ORDER BY
            CASE e.lifecycle_state
                WHEN 'active' THEN 0
                WHEN 'probation' THEN 1
                WHEN 'candidate' THEN 2
                WHEN 'retired' THEN 3
                ELSE 4
            END,
            e.expert_key
        """
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
        ORDER BY e.expert_key
        """
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
            e.name AS expert_name,
            e.lifecycle_state,
            vv.valuation_date,
            vv.cash,
            vv.positions_value,
            vv.total_value,
            sc.portfolio_return,
            sc.benchmark_return,
            sc.benchmark_excess,
            sc.overall_score
        FROM virtual_valuations vv
        JOIN virtual_portfolios vp ON vp.id = vv.portfolio_id
        JOIN experts e ON e.id = vp.owner_id AND vp.owner_type = 'expert'
        LEFT JOIN expert_scorecards sc
          ON sc.expert_id = e.id AND sc.score_date = vv.valuation_date
        ORDER BY vv.valuation_date DESC, e.expert_key
        LIMIT 120
        """
    ).fetchall()
    return [dict(row) for row in rows]


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
    review = row["review_rationale"] or "暂无生命周期复盘。"
    score = row["overall_score"]
    mature = "成熟" if row["mature_enough"] else "样本不足"
    return f"""
    <article class="expert-card state-{escape(state)}">
      <div class="expert-head">
        <div><h3>{escape(row['name'])}</h3><span>{escape(row['style_label'])}</span></div>
        <b>{escape(lifecycle_label(state))}</b>
      </div>
      <p>{escape(row['short_description'])}</p>
      {stat_grid([
          ("当前资产", money(total_value)),
          ("现金", money(row["current_cash"])),
          ("虚拟收益", percent(return_value)),
          ("最大回撤", percent(row["max_drawdown"])),
          ("综合评分", score if score is not None else "暂无"),
          ("评分状态", mature),
      ])}
      <p class="muted">{escape(review)}</p>
    </article>
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


def expert_lessons_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("还没有清退或招聘经验；专家需要足够成熟的评估窗口后才会写入 lessons。")
    display_rows = [
        {
            "lesson_date": row["lesson_date"],
            "expert_name": row["expert_name"] or "系统",
            "lesson_type": row["lesson_type"],
            "summary": row["summary"],
            "avoid_hiring_patterns": row["avoid_hiring_patterns"],
        }
        for row in rows
    ]
    return table(display_rows, ["lesson_date", "expert_name", "lesson_type", "summary", "avoid_hiring_patterns"])


def expert_equity_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty("还没有专家组合估值；运行估值或评分后会显示权益曲线和基准比较。")
    display_rows = [
        {
            "expert_name": row["expert_name"],
            "state": lifecycle_label(row["lifecycle_state"]),
            "valuation_date": row["valuation_date"],
            "cash": money(row["cash"]),
            "positions_value": money(row["positions_value"]),
            "total_value": money(row["total_value"]),
            "portfolio_return": percent(row["portfolio_return"]),
            "benchmark_return": percent(row["benchmark_return"]),
            "benchmark_excess": percent(row["benchmark_excess"]),
            "overall_score": row["overall_score"] if row["overall_score"] is not None else "暂无",
        }
        for row in rows
    ]
    return table(display_rows, ["expert_name", "state", "valuation_date", "cash", "positions_value", "total_value", "portfolio_return", "benchmark_return", "benchmark_excess", "overall_score"])


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


def format_cell(value: Any, escape_value: bool = True) -> str:
    if value is None:
        return '<span class="muted">NULL</span>'
    if isinstance(value, float):
        return escape(f"{value:.6g}") if escape_value else f"{value:.6g}"
    text = str(value)
    if len(text) > 180:
        text = text[:177] + "..."
    return escape(text) if escape_value else text


def format_stat(value: Any) -> str:
    if value is None:
        return '<span class="muted">暂无</span>'
    if isinstance(value, float):
        return escape(f"{value:.6g}")
    return escape(value)


def percent(value: Any) -> str:
    if value is None:
        return "暂无"
    return f"{float(value):.2%}"


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


CSS = """
:root{color-scheme:light;--bg:#f5f7f8;--panel:#ffffff;--ink:#1b2528;--muted:#637176;--line:#d7e0e3;--accent:#0f766e;--warn:#a16207;--bad:#b91c1c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}
.sidebar{background:#102326;color:#eef7f6;padding:18px 14px;position:sticky;top:0;height:100vh}.brand{font-weight:700;font-size:18px;margin:4px 8px 18px}
nav{display:grid;gap:4px}nav a{color:#cfe4e1;text-decoration:none;padding:9px 10px;border-radius:6px}nav a.active,nav a:hover{background:#204346;color:#fff}
main{padding:22px;min-width:0}header{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:16px}h1{font-size:24px;margin:0}header p{margin:0;color:var(--muted);max-width:680px}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin:0 0 16px;padding:16px;box-shadow:0 1px 2px rgba(10,20,20,.04)}section h2{font-size:17px;margin:0 0 12px}
.stat-grid{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px}.stat{border:1px solid var(--line);border-radius:6px;padding:10px;background:#fbfdfd;min-height:72px}.stat span{display:block;color:var(--muted);font-size:12px}.stat strong{display:block;margin-top:8px;font-size:18px;overflow-wrap:anywhere}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse;min-width:760px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}th{background:#edf4f3;font-size:12px;color:#37474c;position:sticky;top:0}td{max-width:260px;overflow:hidden;text-overflow:ellipsis}
.toolbar{display:flex;gap:8px;margin-bottom:12px}select,button{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;padding:0 10px}button{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:650}
.settings-form,.filter-form{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:12px}.settings-form label,.filter-form label{display:grid;gap:6px;color:var(--muted);font-size:12px}.settings-form input,.settings-form select,.filter-form input,.filter-form select{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;padding:0 10px;color:var(--ink);font-size:14px}.settings-form .wide{grid-column:span 2}.filter-form .checkbox{display:flex;align-items:center;gap:8px;color:var(--ink);font-size:14px}.filter-form .checkbox input{height:auto}.notice{border:1px solid #b9ded8;background:#e3f4f1;color:#0f5f59;border-radius:6px;padding:10px;margin-bottom:12px;font-weight:650}.preset-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.preset-link{border:1px solid var(--line);border-radius:6px;background:#fff;color:#0f5f59;text-decoration:none;padding:7px 10px;font-weight:650}.preset-link.active{background:#e3f4f1;border-color:#95c9c3}
.summary,.mini-chart,.recommendations{margin-top:14px}.mini-chart h3,.summary h3,.profile h3,.advice-block h3,.recommendations h3{margin:0 0 8px;font-size:14px}.bar-row{display:grid;grid-template-columns:90px minmax(120px,1fr) 42px;gap:10px;align-items:center;margin:8px 0}.bar{height:10px;background:#e5ecee;border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.recommendations{display:grid;gap:8px}.recommendation{display:grid;grid-template-columns:minmax(160px,1fr) 100px minmax(260px,1.2fr);gap:12px;align-items:center;border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:10px;color:var(--ink);text-decoration:none}.recommendation:hover{border-color:#95c9c3;background:#f1faf8}.recommendation span,.recommendation small{display:block;color:var(--muted)}.recommendation strong{font-size:18px;color:#0f5f59}.history-list{margin-top:16px}.history-list h3{margin:0 0 8px;font-size:14px}
.category-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:10px}.category-grid.compact{grid-template-columns:repeat(6,minmax(120px,1fr))}.category-card{display:grid;gap:6px;min-height:132px;border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px;color:var(--ink);text-decoration:none}.category-card:hover{border-color:#95c9c3;background:#f1faf8}.category-card span{color:var(--muted);font-size:12px}.category-card strong{font-size:24px;color:#0f5f59}.category-card em{font-style:normal;color:#37474c}.category-card small{color:var(--muted)}.category-context{margin-top:12px}.technical-details summary{cursor:pointer;color:#0f5f59;font-weight:700;margin-bottom:10px}.technical-details[open] summary{margin-bottom:12px}
.expert-grid{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:12px;margin-top:12px}.expert-card{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;background:#fbfdfd;padding:12px}.expert-card.state-probation{border-left-color:var(--warn);background:#fffaf0}.expert-card.state-retired{border-left-color:var(--bad);background:#fff8f8}.expert-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.expert-head h3{margin:0}.expert-head span{display:block;color:var(--muted);font-size:12px}.expert-head b{background:var(--accent);color:#fff;border-radius:999px;padding:3px 8px;font-size:12px}.state-probation .expert-head b{background:var(--warn)}.state-retired .expert-head b{background:var(--bad)}
.timeline{display:grid;gap:12px}.timeline.compact{gap:8px}.timeline-card{border:1px solid var(--line);border-radius:8px;background:#fbfdfd;padding:12px}.timeline-date{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}.timeline-date strong{font-size:18px;color:#0f5f59}.timeline-date span{color:var(--muted);text-align:right}.timeline-grid{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:8px}.timeline-state{border:1px solid var(--line);border-radius:6px;background:#fff;padding:10px;min-height:104px}.timeline-state span,.timeline-state small{display:block;color:var(--muted);font-size:12px}.timeline-state strong{display:block;margin:6px 0;color:var(--ink);overflow-wrap:anywhere}.timeline-state a{color:#0f5f59;font-weight:700;text-decoration:none}.timeline-state.ok{border-color:#b9ded8}.timeline-state.warn{border-color:#e2c66f;background:#fffaf0}.timeline-state.bad,.timeline-state.missing{border-color:#efb4b4;background:#fff8f8}.timeline-state.bad strong,.timeline-state.missing strong{color:var(--bad)}
.curve-card{border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:12px}.curve-meta{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--muted)}.curve-meta strong{color:#0f5f59;font-size:20px}.curve{display:block;width:100%;height:220px;background:#fff;border:1px solid var(--line);border-radius:6px}.curve line{stroke:#c9d4d7;stroke-width:1;stroke-dasharray:4 4}.curve polyline{fill:none;stroke:#0f766e;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
.advice-block{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}.advice-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.advice-head h2{margin:0}.badge{background:#e3f4f1;color:#0f5f59;border:1px solid #b9ded8;border-radius:999px;padding:3px 8px;font-weight:700}.profile-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:12px}.profile{border:1px solid var(--line);border-radius:6px;padding:12px;background:#fbfdfd}pre{white-space:pre-wrap;background:#0f1f22;color:#dcefed;border-radius:6px;padding:12px;overflow:auto}
.empty{border:1px dashed var(--line);border-radius:6px;padding:18px;color:var(--muted);background:#fafcfc}.muted{color:var(--muted)}
@media(max-width:860px){body{display:block}.sidebar{position:static;height:auto}.brand{margin-bottom:10px}nav{display:flex;overflow-x:auto}nav a{white-space:nowrap}main{padding:14px}header{display:block}header p{margin-top:6px}.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.profile-grid,.settings-form,.filter-form,.timeline-grid,.category-grid,.category-grid.compact,.expert-grid{grid-template-columns:1fr}.timeline-date{display:block}.timeline-date span{text-align:left;display:block;margin-top:4px}.settings-form .wide{grid-column:auto}section{padding:12px}.bar-row{grid-template-columns:78px minmax(90px,1fr) 32px}.recommendation{grid-template-columns:1fr}.curve{height:180px}table{min-width:680px}}
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
