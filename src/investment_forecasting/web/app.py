from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from investment_forecasting.db import connect, init_db


NAV_ITEMS = [
    ("/", "总览"),
    ("/data", "数据与曲线"),
    ("/funds", "基金筛选"),
    ("/predictions", "预测"),
    ("/backtests", "回测评分"),
    ("/advice", "每日建议"),
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
        "/data": render_data,
        "/funds": render_funds,
        "/predictions": render_predictions,
        "/backtests": render_backtests,
        "/advice": render_advice,
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
        prediction_summary = conn.execute(
            """
            SELECT MAX(prediction_date) AS prediction_date, COUNT(*) AS count,
                   AVG(expected_return) AS avg_expected_return,
                   AVG(downside_risk) AS avg_downside_risk,
                   AVG(confidence) AS avg_confidence
            FROM model_predictions
            """
        ).fetchone()
        assets = conn.execute("SELECT asset_type, COUNT(*) AS count FROM assets GROUP BY asset_type ORDER BY asset_type").fetchall()
        recommendations = latest_recommendations(conn, limit=8)
    body = section(
        "市场状态",
        stat_grid(
            [
                ("风险等级", latest_advice["risk_level"] if latest_advice else "暂无建议"),
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
        + mini_bars("资产覆盖", [(row["asset_type"], row["count"]) for row in assets])
        + recommendation_panel(recommendations)
        + (advice_summary(latest_advice) if latest_advice else empty("还没有生成每日建议。")),
    )
    return render_page("总览", body, "/")


def render_data(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        assets = conn.execute("SELECT * FROM assets ORDER BY asset_type, code").fetchall()
        selected_id = int(query.get("asset_id", [assets[0]["id"] if assets else 0])[0] or 0)
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
    body = section("资产列表", selector + table(assets, ["id", "code", "name", "asset_type", "market", "status", "source"]))
    body += section("涨幅曲线", return_curve(chart_rows))
    body += section("行情 / 净值历史", table(history, ["trade_date", "close", "adjusted_close", "nav", "volume", "amount", "pct_change", "source"]))
    body += section("量化指标", table(features, ["feature_date", "return_1d", "return_20d", "volatility_20d", "max_drawdown_60d", "sharpe_60d", "calmar_60d", "win_rate_60d", "market_state", "source"]))
    return render_page("数据与曲线", body, "/data")


def render_funds(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        funds = conn.execute(
            """
            SELECT a.id, a.code, a.name, f.feature_date, f.return_20d,
                   f.max_drawdown_60d, f.sharpe_60d, f.win_rate_60d, f.market_state,
                   i.fund_type, i.manager, i.scale, i.purchase_fee
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
    return render_page("基金筛选", section("基金收益/风险排名", table(funds, ["code", "name", "fund_type", "manager", "scale", "purchase_fee", "feature_date", "return_20d", "max_drawdown_60d", "sharpe_60d", "win_rate_60d", "market_state"])), "/funds")


def render_predictions(db_path: Path, query: dict[str, list[str]]) -> str:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id, a.code, a.name, p.prediction_date, p.horizon_days,
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
        rows = conn.execute("SELECT * FROM daily_advice ORDER BY advice_date DESC, id DESC LIMIT 60").fetchall()
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
    return render_page("每日建议", section("每日建议", content or empty("还没有建议记录。")), "/advice")


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


def latest_recommendations(conn: Any, limit: int = 8) -> list[Any]:
    return conn.execute(
        """
        SELECT p.id, a.code, a.name, a.asset_type, p.prediction_date, p.horizon_days,
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
    cards = "".join(
        f"""
        <div class="recommendation">
          <div><b>{escape(item['name'])}</b><span>{escape(item['code'])} · {escape(item['asset_type'])}</span></div>
          <strong>{escape(percent(item['expected_return']))}</strong>
          <small>{escape(item['horizon_days'])}日预期 · 上涨概率 {escape(percent(item['up_probability']))} · 下行 {escape(percent(item['downside_risk']))} · 置信度 {escape(percent(item['confidence']))}</small>
        </div>
        """
        for item in normalized
    )
    return f'<div class="recommendations"><h3>近期优先关注</h3>{cards}</div>'


def _recommendation_row(row: Any) -> dict[str, Any]:
    code = _safe_get(row, "code") or _safe_get(row, "asset_code") or f"asset:{_safe_get(row, 'asset_id')}"
    name = _safe_get(row, "name") or _safe_get(row, "asset_name") or code
    return {
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


def table(rows: Any, columns: list[str]) -> str:
    rows = list(rows)
    if not rows:
        return empty("No records available.")
    head = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{format_cell(row[column] if column in row.keys() else row.get(column))}</td>" for column in columns) + "</tr>"
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def asset_selector(assets: Any, selected_id: int, path: str) -> str:
    options = "".join(
        f'<option value="{asset["id"]}" {"selected" if asset["id"] == selected_id else ""}>{escape(asset["code"])} · {escape(asset["name"])}</option>'
        for asset in assets
    )
    return f'<form class="toolbar" method="get" action="{path}"><select name="asset_id">{options}</select><button type="submit">View</button></form>'


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


def format_cell(value: Any) -> str:
    if value is None:
        return '<span class="muted">NULL</span>'
    if isinstance(value, float):
        return escape(f"{value:.6g}")
    text = str(value)
    if len(text) > 180:
        text = text[:177] + "..."
    return escape(text)


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
.summary,.mini-chart,.recommendations{margin-top:14px}.mini-chart h3,.summary h3,.profile h3,.advice-block h3,.recommendations h3{margin:0 0 8px;font-size:14px}.bar-row{display:grid;grid-template-columns:90px minmax(120px,1fr) 42px;gap:10px;align-items:center;margin:8px 0}.bar{height:10px;background:#e5ecee;border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.recommendations{display:grid;gap:8px}.recommendation{display:grid;grid-template-columns:minmax(160px,1fr) 100px minmax(260px,1.2fr);gap:12px;align-items:center;border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:10px}.recommendation span,.recommendation small{display:block;color:var(--muted)}.recommendation strong{font-size:18px;color:#0f5f59}
.curve-card{border:1px solid var(--line);border-radius:6px;background:#fbfdfd;padding:12px}.curve-meta{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--muted)}.curve-meta strong{color:#0f5f59;font-size:20px}.curve{display:block;width:100%;height:220px;background:#fff;border:1px solid var(--line);border-radius:6px}.curve line{stroke:#c9d4d7;stroke-width:1;stroke-dasharray:4 4}.curve polyline{fill:none;stroke:#0f766e;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
.advice-block{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}.advice-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.advice-head h2{margin:0}.badge{background:#e3f4f1;color:#0f5f59;border:1px solid #b9ded8;border-radius:999px;padding:3px 8px;font-weight:700}.profile-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:12px}.profile{border:1px solid var(--line);border-radius:6px;padding:12px;background:#fbfdfd}pre{white-space:pre-wrap;background:#0f1f22;color:#dcefed;border-radius:6px;padding:12px;overflow:auto}
.empty{border:1px dashed var(--line);border-radius:6px;padding:18px;color:var(--muted);background:#fafcfc}.muted{color:var(--muted)}
@media(max-width:860px){body{display:block}.sidebar{position:static;height:auto}.brand{margin-bottom:10px}nav{display:flex;overflow-x:auto}nav a{white-space:nowrap}main{padding:14px}header{display:block}header p{margin-top:6px}.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.profile-grid{grid-template-columns:1fr}section{padding:12px}.bar-row{grid-template-columns:78px minmax(90px,1fr) 32px}.recommendation{grid-template-columns:1fr}.curve{height:180px}table{min-width:680px}}
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
