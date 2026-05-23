from __future__ import annotations

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.db import init_db
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.web.app import render_route
from tests.test_daily_workflow import seed_asset_with_prices


def prepare_web_db(tmp_path):
    db_path = tmp_path / "web.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    calculate_features_for_db(db_path)
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)
    generate_daily_advice(db_path, advice_date="20260523")
    return db_path


def test_dashboard_renders_empty_database(tmp_path):
    db_path = tmp_path / "empty.sqlite3"
    init_db(db_path)

    html = render_route(db_path, "/", {})

    assert "总览" in html
    assert "暂无建议" in html
    assert "暂无日志" in html


def test_workbench_pages_render_with_data(tmp_path):
    db_path = prepare_web_db(tmp_path)

    pages = ["/", "/data", "/funds", "/predictions", "/backtests", "/advice", "/logs"]
    rendered = {page: render_route(db_path, page, {}) for page in pages}

    assert "市场状态" in rendered["/"]
    assert "近期优先关注" in rendered["/"]
    assert "涨幅曲线" in rendered["/data"]
    assert "行情 / 净值历史" in rendered["/data"]
    assert "模型预测" in rendered["/predictions"]
    assert "回测任务" in rendered["/backtests"]
    assert "每日建议" in rendered["/advice"]
    assert "任务日志" in rendered["/logs"]
    for html in rendered.values():
        assert "<!doctype html>" in html
        assert "投资预测工作台" in html
        assert "viewport" in html
