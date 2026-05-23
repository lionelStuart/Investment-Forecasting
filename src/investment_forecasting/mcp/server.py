from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from investment_forecasting.mcp.tools import call_tool


DEFAULT_DB_PATH = Path("data/investment_forecasting.sqlite3")


def create_mcp_server(db_path: str | Path | None = None) -> FastMCP:
    resolved_db_path = Path(db_path or os.environ.get("INVESTMENT_FORECASTING_DB", DEFAULT_DB_PATH))
    mcp = FastMCP(
        "Investment Forecasting",
        instructions=(
            "Structured investment research tools backed by local SQLite data. "
            "Outputs are research support and must not be treated as certain investment advice."
        ),
    )

    @mcp.tool(name="get_asset_list", description="List stored assets, optionally filtered by asset_type.")
    def get_asset_list(asset_type: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_asset_list", {"asset_type": asset_type} if asset_type else {})

    @mcp.tool(name="get_asset_history", description="Return stored daily price/NAV history for one asset.")
    def get_asset_history(
        code: str,
        market: str = "CN",
        source: str = "akshare",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        return call_tool(
            resolved_db_path,
            "get_asset_history",
            {
                "code": code,
                "market": market,
                "source": source,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
        )

    @mcp.tool(name="get_fund_metrics", description="Return latest stored feature/risk metrics for a fund.")
    def get_fund_metrics(code: str, market: str = "CN", source: str = "akshare") -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_fund_metrics", {"code": code, "market": market, "source": source})

    @mcp.tool(name="get_market_snapshot", description="Return the latest structured market snapshot.")
    def get_market_snapshot() -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_market_snapshot", {})

    @mcp.tool(name="run_forecast", description="Run latest baseline forecasts.")
    def run_forecast(horizons: list[int] | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "run_forecast", {"horizons": horizons or [5, 20, 60]})

    @mcp.tool(name="run_backtest", description="Run rolling baseline backtests.")
    def run_backtest(horizons: list[int] | None = None, lookback_days: int = 60) -> dict[str, Any]:
        return call_tool(
            resolved_db_path,
            "run_backtest",
            {"horizons": horizons or [5, 20, 60], "lookback_days": lookback_days},
        )

    @mcp.tool(name="get_daily_advice", description="Return stored daily advice for a date or the latest advice.")
    def get_daily_advice(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_daily_advice", {"date": date} if date else {})

    @mcp.tool(name="generate_daily_advice", description="Generate and store daily advice from stored evidence.")
    def generate_daily_advice(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "generate_daily_advice", {"date": date} if date else {})

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Investment Forecasting MCP stdio server.")
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path.")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)

    if args.db:
        os.environ["INVESTMENT_FORECASTING_DB"] = str(args.db)
    server = create_mcp_server(args.db)
    if args.transport in {"sse", "streamable-http"}:
        server.settings.host = args.host
        server.settings.port = args.port
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

