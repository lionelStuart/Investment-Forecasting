from __future__ import annotations

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.test_mcp_tools import prepare_tool_db


@pytest.mark.asyncio
async def test_mcp_stdio_lists_tools_and_calls_read_and_workflow_tools(tmp_path):
    db_path = prepare_tool_db(tmp_path)
    params = StdioServerParameters(
        command="investment-forecasting-mcp",
        args=["--db", str(db_path)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}

            snapshot = await session.call_tool("get_market_snapshot", {})
            forecast = await session.call_tool("run_forecast", {"horizons": [5]})
            missing = await session.call_tool("get_asset_history", {"code": "NOPE"})

    assert {
        "get_asset_list",
        "get_asset_history",
        "get_fund_metrics",
        "get_market_snapshot",
        "run_forecast",
        "run_backtest",
        "get_daily_advice",
        "generate_daily_advice",
        "list_experts",
        "get_expert_plans",
        "run_expert_plans",
        "get_expert_portfolios",
        "score_experts",
        "get_expert_scorecards",
        "get_expert_lessons",
    } == tool_names

    snapshot_payload = getattr(snapshot, "structuredContent")
    forecast_payload = getattr(forecast, "structuredContent")
    missing_payload = getattr(missing, "structuredContent")

    assert snapshot_payload["ok"] is True
    assert snapshot_payload["result"]["prediction_summary"]["count"] >= 3
    assert forecast_payload["ok"] is True
    assert forecast_payload["result"]["horizons"] == [5]
    assert missing_payload == {
        "ok": False,
        "tool": "get_asset_history",
        "result": None,
        "error": {"message": "Unknown asset: NOPE/CN/akshare"},
    }
