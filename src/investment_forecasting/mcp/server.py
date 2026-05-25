from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from investment_forecasting.mcp.tools import call_agent_tool, call_tool


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
    def run_forecast(horizons: list[int] | None = None, model_versions: list[str] | None = None) -> dict[str, Any]:
        return call_tool(
            resolved_db_path,
            "run_forecast",
            {"horizons": horizons or [5, 20, 60], "model_versions": model_versions or ["baseline_mean_v1"]},
        )

    @mcp.tool(name="run_backtest", description="Run rolling baseline backtests.")
    def run_backtest(
        horizons: list[int] | None = None,
        lookback_days: int = 60,
        embargo_days: int = 0,
        model_versions: list[str] | None = None,
    ) -> dict[str, Any]:
        return call_tool(
            resolved_db_path,
            "run_backtest",
            {
                "horizons": horizons or [5, 20, 60],
                "lookback_days": lookback_days,
                "embargo_days": embargo_days,
                "model_versions": model_versions or ["baseline_mean_v1"],
            },
        )

    @mcp.tool(name="get_daily_advice", description="Return stored daily advice for a date or the latest advice.")
    def get_daily_advice(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_daily_advice", {"date": date} if date else {})

    @mcp.tool(name="generate_daily_advice", description="Generate and store daily advice from stored evidence.")
    def generate_daily_advice(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "generate_daily_advice", {"date": date} if date else {})

    @mcp.tool(name="get_jarvis_daily_brief", description="Return a structured Jarvis daily brief for a date or the latest brief.")
    def get_jarvis_daily_brief(date: str | None = None, version: str | None = None) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        if date:
            arguments["date"] = date
        if version:
            arguments["version"] = version
        return call_tool(resolved_db_path, "get_jarvis_daily_brief", arguments)

    @mcp.tool(name="generate_jarvis_daily_brief", description="Generate and store a Jarvis daily brief from persisted evidence.")
    def generate_jarvis_daily_brief(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "generate_jarvis_daily_brief", {"date": date} if date else {})

    @mcp.tool(name="search_news_evidence", description="Search bounded financial news evidence. Results are context only, not buy/sell advice.")
    def search_news_evidence(
        source: str | list[str] | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        asset_id: int | None = None,
        asset_code: str | None = None,
        theme: str | None = None,
        event_type: str | None = None,
        sentiment: str | None = None,
        keyword: str | None = None,
        max_results: int = 10,
        dedupe: str = "content_hash",
        sort: str = "recency",
    ) -> dict[str, Any]:
        return call_tool(
            resolved_db_path,
            "search_news_evidence",
            {
                "source": source,
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "asset_id": asset_id,
                "asset_code": asset_code,
                "theme": theme,
                "event_type": event_type,
                "sentiment": sentiment,
                "keyword": keyword,
                "max_results": max_results,
                "dedupe": dedupe,
                "sort": sort,
            },
        )

    @mcp.tool(name="list_experts", description="List expert committee roster records and lifecycle state.")
    def list_experts(state: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "list_experts", {"state": state} if state else {})

    @mcp.tool(name="get_expert_plans", description="Return persisted expert plans for a date or latest plans.")
    def get_expert_plans(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_expert_plans", {"date": date} if date else {})

    @mcp.tool(name="run_expert_plans", description="Run expert daily planning and simulated execution.")
    def run_expert_plans(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "run_expert_plans", {"date": date} if date else {})

    @mcp.tool(name="get_expert_portfolios", description="Return expert-owned virtual portfolio state.")
    def get_expert_portfolios() -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_expert_portfolios", {})

    @mcp.tool(name="score_experts", description="Score experts and review lifecycle status.")
    def score_experts(
        date: str | None = None,
        window_days: int = 20,
        min_valuations: int = 3,
    ) -> dict[str, Any]:
        return call_tool(
            resolved_db_path,
            "score_experts",
            {"date": date, "window_days": window_days, "min_valuations": min_valuations},
        )

    @mcp.tool(name="get_expert_scorecards", description="Return expert scorecards and lifecycle reviews.")
    def get_expert_scorecards(date: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_expert_scorecards", {"date": date} if date else {})

    @mcp.tool(name="get_expert_lessons", description="Return structured expert lifecycle and hiring lessons.")
    def get_expert_lessons(lesson_type: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_expert_lessons", {"lesson_type": lesson_type} if lesson_type else {})

    @mcp.tool(name="get_agent_tool_manifest", description="Return allowed tools and skills for a role-scoped Codex agent run.")
    def get_agent_tool_manifest(role_type: str, role_key: str | None = None) -> dict[str, Any]:
        return call_tool(resolved_db_path, "get_agent_tool_manifest", {"role_type": role_type, "role_key": role_key})

    @mcp.tool(name="validate_agent_output", description="Validate a structured expert/Jarvis agent output preview.")
    def validate_agent_output(agent_run_id: int, role_type: str, role_key: str, output: dict[str, Any]) -> dict[str, Any]:
        return call_agent_tool(
            resolved_db_path,
            "validate_agent_output",
            {"agent_run_id": agent_run_id, "role_type": role_type, "role_key": role_key, "output": output},
        )

    @mcp.tool(name="submit_expert_virtual_action", description="Submit one expert virtual action envelope for system validation.")
    def submit_expert_virtual_action(agent_run_id: int, role_key: str, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return call_agent_tool(
            resolved_db_path,
            "submit_expert_virtual_action",
            {
                "agent_run_id": agent_run_id,
                "role_type": "expert",
                "role_key": role_key,
                "idempotency_key": idempotency_key,
                "payload": payload,
            },
        )

    @mcp.tool(name="submit_jarvis_daily_brief", description="Submit one Jarvis daily brief envelope for system validation.")
    def submit_jarvis_daily_brief(agent_run_id: int, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return call_agent_tool(
            resolved_db_path,
            "submit_jarvis_daily_brief",
            {
                "agent_run_id": agent_run_id,
                "role_type": "jarvis",
                "role_key": "jarvis",
                "idempotency_key": idempotency_key,
                "payload": payload,
            },
        )

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
