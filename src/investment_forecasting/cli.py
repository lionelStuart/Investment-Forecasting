from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from investment_forecasting.advice.generator import AdviceGenerationError, generate_daily_advice
from investment_forecasting.advice.scoring import AdviceScoringError, score_matured_advice
from investment_forecasting.agent_runtime import CodexCliRuntimeAdapter, CodexRuntimePolicy, build_launch_request, list_runtime_agent_runs
from investment_forecasting.agent_runtime.execution import run_expert_codex_agents, run_jarvis_codex_agent
from investment_forecasting.ai_providers import AIProviderRequest, call_ai_provider, load_ai_provider_config
from investment_forecasting.communication.imessage import verify_imessage_setup
from investment_forecasting.communication.service import CommunicationError, send_outbound_message
from investment_forecasting.communication.config import notification_defaults
from investment_forecasting.communication.templates import render_jarvis_weekly_summary, send_rendered_notification
from investment_forecasting.data.ingestion import (
    UNIVERSES,
    discover_akshare_universe,
    filter_existing_universe_assets,
    ingest_mvp_universe,
)
from investment_forecasting.data.capital_flow import CapitalFlowIngestionError, ingest_capital_flow
from investment_forecasting.data.fund_holdings import FundHoldingIngestionError, ingest_fund_holdings
from investment_forecasting.data.macro import DEFAULT_FRED_SERIES, ingest_fred_macro
from investment_forecasting.data.news import NewsIngestionError, ingest_news
from investment_forecasting.db import (
    active_user_preference,
    connect,
    init_db,
    list_communication_recipients,
    list_communication_adapter_configs,
    list_outbound_messages,
    list_user_preferences,
    upsert_communication_adapter_config,
    upsert_communication_recipient,
    upsert_user_preference,
)
from investment_forecasting.experts.planning import ExpertPlanningError, run_expert_daily_plans
from investment_forecasting.experts.roster import initialize_default_experts, list_roster
from investment_forecasting.experts.scoring import ExpertScoringError, score_and_review_experts
from investment_forecasting.jarvis.persistence import deserialize_jarvis_brief
from investment_forecasting.jarvis.synthesis import JarvisSynthesisError, generate_jarvis_brief
from investment_forecasting.mcp.tools import call_tool, list_tools
from investment_forecasting.portfolio.accounting import (
    DEFAULT_EXPERT_INITIAL_CAPITAL,
    PortfolioError,
    create_virtual_portfolio,
    ensure_expert_portfolios,
    record_virtual_order,
    value_virtual_portfolio,
)
from investment_forecasting.mcp.server import main as run_mcp_server_main
from investment_forecasting.providers.akshare_provider import AkshareProvider, ProviderAccessPolicy, ProviderDataError, RetryConfig
from investment_forecasting.providers.fred_provider import FredDataError
from investment_forecasting.providers.tushare_provider import TushareProvider
from investment_forecasting.quant.backtest import BacktestError, run_backtest, run_latest_forecasts
from investment_forecasting.quant.calibration import CalibrationError, run_calibration_report, run_historical_calibration_corpus
from investment_forecasting.quant.features import FeatureCalculationError, calculate_features_for_db
from investment_forecasting.quant.market import MarketSnapshotError, calculate_market_snapshot
from investment_forecasting.quant.model_validation import (
    ModelValidationError,
    build_replay_report,
    build_tuning_plan,
    replay_ytd_predictions,
)
from investment_forecasting.quant.monitoring import ModelMonitoringError, run_model_monitoring_report
from investment_forecasting.scheduler import initialize_scheduler, list_scheduler_jobs, run_due_jobs, run_scheduler_job, scheduler_status
from investment_forecasting.web.app import run_web_server
from investment_forecasting.workflows.daily import default_daily_config, run_daily_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="investment-forecasting",
        description="Investment Forecasting local operations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    db_parser = subparsers.add_parser("db", help="Database operations")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)

    init_parser = db_subparsers.add_parser("init", help="Create or migrate SQLite schema")
    init_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Data ingestion operations")
    ingest_subparsers = ingest_parser.add_subparsers(dest="ingest_command", required=True)

    mvp_parser = ingest_subparsers.add_parser("mvp", help="Ingest the MVP AKShare universe")
    mvp_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )
    mvp_parser.add_argument("--start-date", required=True, help="Start date in YYYYMMDD format.")
    mvp_parser.add_argument("--end-date", required=True, help="End date in YYYYMMDD format.")
    mvp_parser.add_argument(
        "--universe",
        choices=sorted(UNIVERSES),
        default="mvp",
        help="Asset universe to ingest. Use research for broader stock/ETF/fund coverage.",
    )
    mvp_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep ingesting remaining universe assets if one provider call fails.",
    )
    _add_provider_access_args(mvp_parser)
    _add_provider_choice_args(mvp_parser)

    macro_parser = ingest_subparsers.add_parser("macro", help="Ingest free macro observations from FRED")
    macro_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    macro_parser.add_argument("--start-date", required=True, help="Start date in YYYYMMDD or YYYY-MM-DD format.")
    macro_parser.add_argument("--end-date", required=True, help="End date in YYYYMMDD or YYYY-MM-DD format.")
    macro_parser.add_argument(
        "--series",
        default=",".join(DEFAULT_FRED_SERIES),
        help="Comma-separated FRED series IDs. Defaults to DGS10,T10YIE,DTWEXBGS.",
    )
    capital_flow_parser = ingest_subparsers.add_parser("capital-flow", help="Ingest A-share capital flow observations")
    capital_flow_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    capital_flow_parser.add_argument("--scope", choices=["market", "stock"], default="stock")
    capital_flow_parser.add_argument(
        "--asset-codes",
        default="",
        help="Comma-separated tracked stock codes. Omit to ingest the first active tracked stock sample.",
    )
    capital_flow_parser.add_argument("--max-days", type=int, default=20, help="Latest rows to persist per subject.")
    capital_flow_parser.add_argument(
        "--tushare-lookback-days",
        type=int,
        default=180,
        help="Days to request from Tushare capital-flow APIs when --provider=tushare.",
    )
    _add_provider_access_args(capital_flow_parser)
    _add_provider_choice_args(capital_flow_parser)
    fund_holdings_parser = ingest_subparsers.add_parser("fund-holdings", help="Ingest public-fund stock holding reports")
    fund_holdings_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    fund_holdings_parser.add_argument(
        "--fund-codes",
        default="",
        help="Comma-separated tracked fund codes. Omit to ingest a small tracked fund sample.",
    )
    fund_holdings_parser.add_argument("--year", help="Report year, e.g. 2024. Defaults to current year.")
    _add_provider_access_args(fund_holdings_parser)
    news_parser = ingest_subparsers.add_parser("news", help="Ingest provider-backed financial news evidence")
    news_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    news_parser.add_argument("--source", required=True, help="Provider news source, e.g. sina, wallstreetcn, 10jqka.")
    news_parser.add_argument("--start-datetime", required=True, help="Start datetime, e.g. 20260523 09:00:00.")
    news_parser.add_argument("--end-datetime", required=True, help="End datetime, e.g. 20260523 15:30:00.")
    news_parser.add_argument("--max-items", type=int, default=500, help="Maximum rows to persist from this bounded request.")
    news_parser.add_argument("--tushare-token", help="Optional Tushare Pro token. Defaults to TUSHARE_TOKEN/TS_TOKEN.")
    full_parser = ingest_subparsers.add_parser("full", help="Discover a broad AKShare universe and ingest history")
    full_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    full_parser.add_argument("--start-date", required=True, help="Start date in YYYYMMDD format.")
    full_parser.add_argument("--end-date", required=True, help="End date in YYYYMMDD format.")
    full_parser.add_argument(
        "--asset-types",
        default="stock,etf,fund",
        help="Comma-separated asset types to discover from AKShare: stock,etf,fund.",
    )
    full_parser.add_argument(
        "--max-assets",
        type=int,
        help="Optional cap for dry runs or staged ingestion. Omit to ingest the discovered universe.",
    )
    full_parser.add_argument(
        "--max-assets-per-type",
        type=int,
        help="Optional cap per asset type before applying --max-assets, useful for balanced stock/ETF/fund samples.",
    )
    full_parser.add_argument(
        "--offset-per-type",
        type=int,
        default=0,
        help="Skip this many discovered assets in each requested type before applying caps.",
    )
    full_parser.add_argument(
        "--skip-existing-assets",
        action="store_true",
        help="Only fetch assets that are not already present in the local assets table.",
    )
    _add_provider_access_args(full_parser)
    _add_provider_choice_args(full_parser)

    features_parser = subparsers.add_parser("features", help="Feature calculation operations")
    features_subparsers = features_parser.add_subparsers(dest="features_command", required=True)

    calculate_parser = features_subparsers.add_parser("calculate", help="Calculate daily features from SQLite prices")
    calculate_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )
    calculate_parser.add_argument("--start-date", help="Optional start date in YYYYMMDD or YYYY-MM-DD format.")
    calculate_parser.add_argument("--end-date", help="Optional end date in YYYYMMDD or YYYY-MM-DD format.")
    calculate_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Skip assets with invalid price history and continue calculating the rest.",
    )

    forecast_parser = subparsers.add_parser("forecast", help="Forecast operations")
    forecast_subparsers = forecast_parser.add_subparsers(dest="forecast_command", required=True)
    run_forecast_parser = forecast_subparsers.add_parser("run", help="Run latest baseline forecasts")
    run_forecast_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )
    run_forecast_parser.add_argument("--horizons", default="5,20,60", help="Comma-separated horizon days.")
    run_forecast_parser.add_argument("--model-versions", default="baseline_mean_v1", help="Comma-separated model versions.")

    backtest_parser = subparsers.add_parser("backtest", help="Backtest operations")
    backtest_subparsers = backtest_parser.add_subparsers(dest="backtest_command", required=True)
    run_backtest_parser = backtest_subparsers.add_parser("run", help="Run rolling baseline backtests")
    run_backtest_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )
    run_backtest_parser.add_argument("--horizons", default="5,20,60", help="Comma-separated horizon days.")
    run_backtest_parser.add_argument("--lookback-days", type=int, default=60)
    run_backtest_parser.add_argument("--embargo-days", type=int, default=0, help="Days to skip between validation labels to reduce overlapping-outcome leakage.")
    run_backtest_parser.add_argument("--model-versions", default="baseline_mean_v1", help="Comma-separated model versions.")

    model_validation_parser = subparsers.add_parser("model-validation", help="Point-in-time replay validation operations")
    model_validation_subparsers = model_validation_parser.add_subparsers(dest="model_validation_command", required=True)
    replay_parser = model_validation_subparsers.add_parser("replay-ytd", help="Replay current-year daily predictions from local history")
    replay_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    replay_parser.add_argument("--year", type=int, help="Replay year. Defaults to current year.")
    replay_parser.add_argument("--start-date", help="Replay start date in YYYYMMDD or YYYY-MM-DD format.")
    replay_parser.add_argument("--end-date", help="Replay end date in YYYYMMDD or YYYY-MM-DD format.")
    replay_parser.add_argument("--horizons", default="5,20,60")
    replay_parser.add_argument("--model-versions", default="baseline_mean_v1,momentum_reversal_v1,risk_adjusted_factor_v1")
    replay_parser.add_argument("--lookback-days", type=int, default=60)
    replay_parser.add_argument("--asset-scope", default="all", help="Asset type scope, e.g. stock/etf/fund/index, or all.")
    report_parser = model_validation_subparsers.add_parser("report", help="Aggregate replay scoring diagnostics")
    report_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    report_parser.add_argument("--run-id", type=int)
    tuning_parser = model_validation_subparsers.add_parser("tuning-plan", help="Build model tuning recommendations from replay diagnostics")
    tuning_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    tuning_parser.add_argument("--run-id", type=int)

    advice_parser = subparsers.add_parser("advice", help="Daily advice operations")
    advice_subparsers = advice_parser.add_subparsers(dest="advice_command", required=True)
    generate_parser = advice_subparsers.add_parser("generate", help="Generate daily advice from stored evidence")
    generate_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )
    generate_parser.add_argument("--date", help="Advice date in YYYYMMDD or YYYY-MM-DD format.")
    score_parser = advice_subparsers.add_parser("score-outcomes", help="Score matured advice outcomes")
    score_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    score_parser.add_argument("--horizon-days", type=int, default=20)

    ai_parser = subparsers.add_parser("ai", help="AI provider adapter operations")
    ai_subparsers = ai_parser.add_subparsers(dest="ai_command", required=True)
    provider_check_parser = ai_subparsers.add_parser("provider-check", help="Dry-run the configured AI provider adapter")
    provider_check_parser.add_argument("--analysis-type", choices=["expert", "jarvis"], default="expert")
    provider_check_parser.add_argument("--force-error", action="store_true", help="Force fake-provider error fallback.")
    provider_check_parser.add_argument("--force-timeout", action="store_true", help="Force fake-provider timeout fallback.")

    prefs_parser = subparsers.add_parser("prefs", help="User risk preference operations")
    prefs_subparsers = prefs_parser.add_subparsers(dest="prefs_command", required=True)
    prefs_list_parser = prefs_subparsers.add_parser("list", help="List stored user preferences")
    prefs_list_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    prefs_set_parser = prefs_subparsers.add_parser("set", help="Create or update the active user preference")
    prefs_set_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    prefs_set_parser.add_argument("--name", default="默认账户")
    prefs_set_parser.add_argument("--risk-profile", choices=["aggressive", "balanced", "conservative"], default="balanced")
    prefs_set_parser.add_argument("--horizon-days", type=int, default=20)
    prefs_set_parser.add_argument("--max-equity-pct", type=float, default=0.6)
    prefs_set_parser.add_argument("--min-cash-pct", type=float, default=0.1)
    prefs_set_parser.add_argument("--notes", default="")

    portfolio_parser = subparsers.add_parser("portfolio", help="Simulated portfolio operations")
    portfolio_subparsers = portfolio_parser.add_subparsers(dest="portfolio_command", required=True)
    portfolio_create_parser = portfolio_subparsers.add_parser("create", help="Create or update a simulated portfolio")
    portfolio_create_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    portfolio_create_parser.add_argument("--owner-type", choices=["user", "expert", "system"], default="user")
    portfolio_create_parser.add_argument("--owner-id", type=int, default=1)
    portfolio_create_parser.add_argument("--name", default="用户研究组合")
    portfolio_create_parser.add_argument("--initial-capital", type=float, default=100_000.0)
    portfolio_create_parser.add_argument("--currency", default="CNY")
    portfolio_list_parser = portfolio_subparsers.add_parser("list", help="List simulated portfolios")
    portfolio_list_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    portfolio_trade_parser = portfolio_subparsers.add_parser("trade", help="Record a simulated transaction")
    portfolio_trade_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    portfolio_trade_parser.add_argument("--portfolio-id", type=int, required=True)
    portfolio_trade_parser.add_argument("--date", required=True, help="Trade date in YYYY-MM-DD format.")
    portfolio_trade_parser.add_argument("--side", choices=["buy", "sell", "hold", "no_trade"], required=True)
    portfolio_trade_parser.add_argument("--asset-id", type=int)
    portfolio_trade_parser.add_argument("--quantity", type=float, default=0.0)
    portfolio_trade_parser.add_argument("--fee", type=float, default=0.0)
    portfolio_trade_parser.add_argument("--reason", default="")
    portfolio_value_parser = portfolio_subparsers.add_parser("value", help="Value a simulated portfolio with stored prices")
    portfolio_value_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    portfolio_value_parser.add_argument("--portfolio-id", type=int, required=True)
    portfolio_value_parser.add_argument("--date", required=True, help="Valuation date in YYYY-MM-DD format.")

    communication_parser = subparsers.add_parser("communication", help="Communication adapter operations")
    communication_subparsers = communication_parser.add_subparsers(dest="communication_command", required=True)
    communication_config_parser = communication_subparsers.add_parser("configure-adapter", help="Configure a channel adapter")
    communication_config_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_config_parser.add_argument("--channel", default="imessage")
    communication_config_parser.add_argument("--enabled", action="store_true")
    communication_config_parser.add_argument("--real-send-default", action="store_true", help="Disable dry-run default for this adapter")
    communication_config_parser.add_argument("--config-json", default="{}")
    communication_subparsers.add_parser("list-adapters", help="List communication adapter configurations").add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_recipient_parser = communication_subparsers.add_parser("upsert-recipient", help="Create or update an allowlisted recipient")
    communication_recipient_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_recipient_parser.add_argument("--recipient-key", required=True)
    communication_recipient_parser.add_argument("--display-name", required=True)
    communication_recipient_parser.add_argument("--channel", default="imessage")
    communication_recipient_parser.add_argument("--address", required=True)
    communication_recipient_parser.add_argument("--allowlisted", action="store_true")
    communication_recipient_parser.add_argument("--disabled", action="store_true")
    communication_recipient_parser.add_argument("--min-severity", choices=["info", "warning", "critical"], default="info")
    communication_recipient_parser.add_argument("--rate-limit-per-hour", type=int, default=6)
    communication_recipient_parser.add_argument("--retry-limit", type=int, default=2)
    communication_recipient_parser.add_argument("--notes")
    communication_subparsers.add_parser("list-recipients", help="List communication recipients").add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_send_parser = communication_subparsers.add_parser("send-test", help="Persist and optionally dry-run a test message")
    communication_send_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_send_parser.add_argument("--channel", default="imessage")
    communication_send_parser.add_argument("--recipient-key", required=True)
    communication_send_parser.add_argument("--body", default="投资研究系统测试消息，仅用于验证通信链路，不构成投资建议。")
    communication_send_parser.add_argument("--subject", default="Investment Forecasting test")
    communication_send_parser.add_argument("--severity", choices=["info", "warning", "critical"], default="info")
    communication_send_parser.add_argument("--idempotency-key")
    communication_send_parser.add_argument("--real-send", action="store_true")
    communication_messages_parser = communication_subparsers.add_parser("list-messages", help="List recent outbound messages")
    communication_messages_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_messages_parser.add_argument("--limit", type=int, default=20)
    communication_verify_parser = communication_subparsers.add_parser("verify-setup", help="Verify iMessage adapter setup health")
    communication_verify_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    communication_verify_parser.add_argument("--channel", default="imessage")
    communication_verify_parser.add_argument("--recipient-key", required=True)
    communication_verify_parser.add_argument("--skip-system-probe", action="store_true", help="Only verify database config and allowlist")

    experts_parser = subparsers.add_parser("experts", help="Expert committee roster operations")
    experts_subparsers = experts_parser.add_subparsers(dest="experts_command", required=True)
    experts_init_parser = experts_subparsers.add_parser("init", help="Initialize the default four active experts")
    experts_init_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    experts_portfolios_parser = experts_subparsers.add_parser(
        "init-portfolios",
        help="Create one virtual portfolio for each active expert",
    )
    experts_portfolios_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    experts_portfolios_parser.add_argument("--initial-capital", type=float, default=DEFAULT_EXPERT_INITIAL_CAPITAL)
    experts_list_parser = experts_subparsers.add_parser("list", help="List expert roster records")
    experts_list_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    experts_list_parser.add_argument(
        "--state",
        choices=["candidate", "active", "probation", "retired"],
        help="Optional lifecycle state filter.",
    )
    experts_run_parser = experts_subparsers.add_parser("run-plans", help="Run daily expert plans and simulated execution")
    experts_run_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    experts_run_parser.add_argument("--date", help="Plan date in YYYYMMDD or YYYY-MM-DD format.")
    experts_run_parser.add_argument("--notify-recipient-key", help="Send a mobile notification to this allowlisted recipient")
    experts_run_parser.add_argument("--notification-channel", default="imessage")
    experts_run_parser.add_argument("--notification-dry-run", action="store_true", help="Force notification dry-run for this command")
    experts_score_parser = experts_subparsers.add_parser("score", help="Score experts and review lifecycle status")
    experts_score_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    experts_score_parser.add_argument("--date", help="Review date in YYYYMMDD or YYYY-MM-DD format.")
    experts_score_parser.add_argument("--window-days", type=int, default=20)
    experts_score_parser.add_argument("--min-valuations", type=int, default=3)
    experts_score_parser.add_argument("--notify-recipient-key", help="Send mobile notifications for warnings/retirements")
    experts_score_parser.add_argument("--notification-channel", default="imessage")
    experts_score_parser.add_argument("--notification-dry-run", action="store_true", help="Force notification dry-run for this command")

    mcp_parser = subparsers.add_parser("mcp", help="MCP-compatible tool operations")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_subparsers.add_parser("list-tools", help="List available tools and schemas")
    serve_parser = mcp_subparsers.add_parser("serve", help="Start the MCP server transport")
    serve_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    serve_parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8766)
    call_parser = mcp_subparsers.add_parser("call", help="Call one MCP-compatible tool")
    call_parser.add_argument("tool_name")
    call_parser.add_argument("--args", default="{}", help="Tool arguments as a JSON object.")
    call_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )

    daily_parser = subparsers.add_parser("daily", help="Daily workflow operations")
    daily_subparsers = daily_parser.add_subparsers(dest="daily_command", required=True)
    run_daily_parser = daily_subparsers.add_parser("run", help="Run the full daily workflow")
    run_daily_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/investment_forecasting.sqlite3"),
        help="Path to the SQLite database file.",
    )
    run_daily_parser.add_argument("--date", help="Run/advice date in YYYYMMDD or YYYY-MM-DD format.")
    run_daily_parser.add_argument("--start-date", help="Ingestion/calculation start date.")
    run_daily_parser.add_argument("--end-date", help="Ingestion/calculation end date.")
    run_daily_parser.add_argument("--horizons", default="5,20,60", help="Comma-separated horizon days.")
    run_daily_parser.add_argument("--lookback-days", type=int, default=60)
    run_daily_parser.add_argument("--skip-ingest", action="store_true", help="Use existing SQLite data without provider calls.")
    run_daily_parser.add_argument("--generate-jarvis", action="store_true", help="Generate the Jarvis daily brief after advice scoring.")
    run_daily_parser.add_argument(
        "--notify-recipient-key",
        help="Send mobile workflow notification to this allowlisted recipient. Defaults to INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY.",
    )
    run_daily_parser.add_argument(
        "--notification-channel",
        default=None,
        help="Notification channel. Defaults to INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL or imessage.",
    )
    run_daily_parser.add_argument(
        "--notification-dry-run",
        action="store_true",
        help="Force notification dry-run for this workflow run. If omitted, INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN may set the default.",
    )

    jarvis_parser = subparsers.add_parser("jarvis", help="Jarvis assistant operations")
    jarvis_subparsers = jarvis_parser.add_subparsers(dest="jarvis_command", required=True)
    jarvis_generate_parser = jarvis_subparsers.add_parser("generate", help="Generate and store a Jarvis daily brief")
    jarvis_generate_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    jarvis_generate_parser.add_argument("--date", help="Brief date in YYYYMMDD or YYYY-MM-DD format.")
    jarvis_generate_parser.add_argument("--notify-recipient-key", help="Send a Jarvis phone summary to this allowlisted recipient. Defaults to INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY.")
    jarvis_generate_parser.add_argument("--notification-channel", default=None, help="Notification channel. Defaults to INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL or imessage.")
    jarvis_generate_parser.add_argument("--notification-dry-run", action="store_true", help="Force Jarvis phone summary dry-run. If omitted, INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN may set the default.")
    jarvis_weekly_parser = jarvis_subparsers.add_parser("send-weekly", help="Render and send a Jarvis weekly phone summary")
    jarvis_weekly_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    jarvis_weekly_parser.add_argument("--start-date", help="Week start date in YYYYMMDD or YYYY-MM-DD format. Defaults to end date minus 6 days.")
    jarvis_weekly_parser.add_argument("--end-date", help="Week end date in YYYYMMDD or YYYY-MM-DD format. Defaults to today.")
    jarvis_weekly_parser.add_argument("--recipient-key", default="owner_phone", help="Allowlisted recipient key.")
    jarvis_weekly_parser.add_argument("--notification-channel", default="imessage")
    jarvis_weekly_parser.add_argument("--notification-dry-run", action="store_true", help="Force weekly summary dry-run")

    agent_runs_parser = subparsers.add_parser("agent-runs", help="Codex agent runtime audit operations")
    agent_runs_subparsers = agent_runs_parser.add_subparsers(dest="agent_runs_command", required=True)
    agent_runs_list_parser = agent_runs_subparsers.add_parser("list", help="List audited expert/Jarvis agent runs")
    agent_runs_list_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    agent_runs_list_parser.add_argument("--role-type", choices=["expert", "jarvis"])
    agent_runs_list_parser.add_argument("--role-key")
    agent_runs_list_parser.add_argument(
        "--status",
        choices=[
            "pending",
            "running",
            "completed",
            "failed",
            "submitted",
            "completed_via_artifact",
            "skipped",
            "validation_failed",
            "cancelled",
            "timed_out",
        ],
    )
    agent_runs_list_parser.add_argument("--limit", type=int, default=20)
    agent_runs_readiness_parser = agent_runs_subparsers.add_parser("codex-readiness", help="Check local Codex CLI runtime readiness")
    agent_runs_readiness_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    agent_runs_readiness_parser.add_argument("--project-root", type=Path, default=Path("."))
    agent_runs_readiness_parser.add_argument("--codex-bin", default=None)
    agent_runs_smoke_parser = agent_runs_subparsers.add_parser("codex-smoke", help="Run a local Codex CLI runtime smoke test")
    agent_runs_smoke_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    agent_runs_smoke_parser.add_argument("--project-root", type=Path, default=Path("."))
    agent_runs_smoke_parser.add_argument("--codex-bin", default=None)
    agent_runs_smoke_parser.add_argument("--timeout-seconds", type=int, default=180)
    agent_runs_experts_parser = agent_runs_subparsers.add_parser("run-experts-codex", help="Run active expert agents through local Codex CLI artifact mode")
    agent_runs_experts_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    agent_runs_experts_parser.add_argument("--date", help="Expert run date in YYYYMMDD or YYYY-MM-DD format.")
    agent_runs_experts_parser.add_argument("--expert-key", help="Optional single expert key to run.")
    agent_runs_experts_parser.add_argument("--project-root", type=Path, default=Path("."))
    agent_runs_experts_parser.add_argument("--codex-bin", default=None)
    agent_runs_experts_parser.add_argument("--timeout-seconds", type=int, default=180)
    agent_runs_jarvis_parser = agent_runs_subparsers.add_parser("run-jarvis-codex", help="Run Jarvis through local Codex CLI artifact mode")
    agent_runs_jarvis_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    agent_runs_jarvis_parser.add_argument("--date", help="Jarvis run date in YYYYMMDD or YYYY-MM-DD format.")
    agent_runs_jarvis_parser.add_argument("--target-evidence-date", help="Evidence date in YYYYMMDD or YYYY-MM-DD format.")
    agent_runs_jarvis_parser.add_argument("--project-root", type=Path, default=Path("."))
    agent_runs_jarvis_parser.add_argument("--codex-bin", default=None)
    agent_runs_jarvis_parser.add_argument("--timeout-seconds", type=int, default=180)
    agent_runs_jarvis_parser.add_argument("--notify-recipient-key", help="Send the Jarvis phone summary to this allowlisted recipient after brief persistence. Defaults to INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY.")
    agent_runs_jarvis_parser.add_argument("--notification-channel", default=None, help="Notification channel. Defaults to INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL or imessage.")
    agent_runs_jarvis_parser.add_argument("--notification-dry-run", action="store_true", help="Force Jarvis phone summary dry-run.")

    scheduler_parser = subparsers.add_parser("scheduler", help="System-owned scheduler operations")
    scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_command", required=True)
    scheduler_list_parser = scheduler_subparsers.add_parser("list-jobs", help="List fixed scheduler job definitions")
    scheduler_list_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    scheduler_list_parser.add_argument("--now", help="Override current time in ISO format for deterministic inspection.")
    scheduler_status_parser = scheduler_subparsers.add_parser("status", help="Show scheduler runs, watermarks, and provider backoff state")
    scheduler_status_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    scheduler_run_due_parser = scheduler_subparsers.add_parser("run-due", help="Run all due scheduler jobs through the system scheduler")
    scheduler_run_due_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    scheduler_run_due_parser.add_argument("--now", help="Override current time in ISO format for deterministic runs.")
    scheduler_run_job_parser = scheduler_subparsers.add_parser("run-job", help="Run one scheduler job through the system scheduler")
    scheduler_run_job_parser.add_argument("job_key")
    scheduler_run_job_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    scheduler_run_job_parser.add_argument("--now", help="Override current time in ISO format for deterministic runs.")

    web_parser = subparsers.add_parser("web", help="Local WebUI operations")
    web_subparsers = web_parser.add_subparsers(dest="web_command", required=True)
    web_run_parser = web_subparsers.add_parser("run", help="Start the local workbench server")
    web_run_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    web_run_parser.add_argument("--host", default="127.0.0.1")
    web_run_parser.add_argument("--port", type=int, default=8765)

    calibration_parser = subparsers.add_parser("calibration", help="Model calibration operations")
    calibration_subparsers = calibration_parser.add_subparsers(dest="calibration_command", required=True)
    calibration_run_parser = calibration_subparsers.add_parser("run", help="Run candidate model calibration")
    calibration_run_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    calibration_run_parser.add_argument("--date", help="Report date in YYYYMMDD or YYYY-MM-DD format.")
    calibration_run_parser.add_argument("--horizons", default="5,20,60", help="Comma-separated horizon days.")
    calibration_run_parser.add_argument("--lookback-days", type=int, default=60)
    calibration_corpus_parser = calibration_subparsers.add_parser("corpus", help="Build historical corpus and run calibration")
    calibration_corpus_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    calibration_corpus_parser.add_argument("--start-date", required=True)
    calibration_corpus_parser.add_argument("--end-date", required=True)
    calibration_corpus_parser.add_argument("--date", help="Report date in YYYYMMDD or YYYY-MM-DD format.")
    calibration_corpus_parser.add_argument("--horizons", default="5,20,60", help="Comma-separated horizon days.")
    calibration_corpus_parser.add_argument("--lookback-days", type=int, default=60)
    calibration_corpus_parser.add_argument("--skip-ingest", action="store_true")

    monitoring_parser = subparsers.add_parser("monitoring", help="Model monitoring operations")
    monitoring_subparsers = monitoring_parser.add_subparsers(dest="monitoring_command", required=True)
    monitoring_run_parser = monitoring_subparsers.add_parser("run", help="Generate model monitoring and drift report")
    monitoring_run_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    monitoring_run_parser.add_argument("--date", help="Report date in YYYYMMDD or YYYY-MM-DD format.")

    market_parser = subparsers.add_parser("market", help="Market environment operations")
    market_subparsers = market_parser.add_subparsers(dest="market_command", required=True)
    market_snapshot_parser = market_subparsers.add_parser("snapshot", help="Calculate stored market environment snapshot")
    market_snapshot_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    market_snapshot_parser.add_argument("--date", help="Snapshot date in YYYYMMDD or YYYY-MM-DD format.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "db" and args.db_command == "init":
        db_path = init_db(args.db)
        print(f"Initialized SQLite database: {db_path}")
        return 0

    if args.command == "ingest" and args.ingest_command == "mvp":
        try:
            summary = ingest_mvp_universe(
                args.db,
                start_date=args.start_date,
                end_date=args.end_date,
                provider=_provider_from_args(args),
                universe=UNIVERSES[args.universe],
                continue_on_error=args.continue_on_error,
            )
        except ProviderDataError as exc:
            print(f"Ingestion failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Ingested {total} rows into {args.db}: {summary}")
        return 0

    if args.command == "ingest" and args.ingest_command == "macro":
        try:
            summary = ingest_fred_macro(args.db, args.start_date, args.end_date, series_ids=_parse_series(args.series))
        except FredDataError as exc:
            print(f"Macro ingestion failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Ingested {total} macro observations into {args.db}: {summary}")
        return 0

    if args.command == "ingest" and args.ingest_command == "capital-flow":
        try:
            summary = ingest_capital_flow(
                args.db,
                provider=_provider_from_args(args),
                scope=args.scope,
                asset_codes=_parse_optional_codes(args.asset_codes),
                max_days=args.max_days,
            )
        except (CapitalFlowIngestionError, ProviderDataError) as exc:
            print(f"Capital flow ingestion failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Ingested {total} capital flow observations into {args.db}: {summary}")
        return 0

    if args.command == "ingest" and args.ingest_command == "fund-holdings":
        try:
            summary = ingest_fund_holdings(
                args.db,
                provider=_akshare_provider_from_args(args),
                fund_codes=_parse_optional_codes(args.fund_codes),
                year=args.year,
            )
        except (FundHoldingIngestionError, ProviderDataError) as exc:
            print(f"Fund holdings ingestion failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Ingested {total} fund holding rows into {args.db}: {summary}")
        return 0

    if args.command == "ingest" and args.ingest_command == "news":
        try:
            summary = ingest_news(
                args.db,
                provider=TushareProvider(token=args.tushare_token),
                source=args.source,
                start_datetime=args.start_datetime,
                end_datetime=args.end_datetime,
                max_items=args.max_items,
            )
        except (NewsIngestionError, ProviderDataError) as exc:
            print(f"News ingestion failed: {exc}", file=sys.stderr)
            return 1
        print(f"Ingested news evidence into {args.db}: {json.dumps(summary, ensure_ascii=False)}")
        return 0

    if args.command == "ingest" and args.ingest_command == "full":
        try:
            asset_types = _parse_asset_types(args.asset_types)
            if args.offset_per_type < 0:
                raise argparse.ArgumentTypeError("--offset-per-type must be zero or positive")
            provider = _provider_from_args(args)
            universe = discover_akshare_universe(
                provider=provider,
                asset_types=asset_types,
                max_assets=args.max_assets,
                max_assets_per_type=args.max_assets_per_type,
                offset_per_type=args.offset_per_type,
            )
            discovered_count = len(universe)
            if args.skip_existing_assets:
                universe = filter_existing_universe_assets(args.db, universe)
            summary = ingest_mvp_universe(
                args.db,
                start_date=args.start_date,
                end_date=args.end_date,
                provider=provider,
                universe=universe,
                continue_on_error=True,
            )
        except argparse.ArgumentTypeError as exc:
            print(f"Invalid full universe options: {exc}", file=sys.stderr)
            return 2
        except ProviderDataError as exc:
            print(f"Full universe ingestion failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        skipped = sum(1 for rows in summary.values() if rows == 0)
        print(
            f"Ingested {total} rows for {len(summary)} assets into {args.db}; "
            f"discovered {discovered_count}; skipped {discovered_count - len(summary)} existing and {skipped} failed/empty assets"
        )
        return 0

    if args.command == "features" and args.features_command == "calculate":
        try:
            summary = calculate_features_for_db(
                args.db,
                start_date=args.start_date,
                end_date=args.end_date,
                continue_on_error=args.continue_on_error,
            )
        except FeatureCalculationError as exc:
            print(f"Feature calculation failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Calculated {total} feature rows in {args.db}: {summary}")
        return 0

    if args.command == "forecast" and args.forecast_command == "run":
        try:
            summary = run_latest_forecasts(
                args.db,
                horizons=_parse_horizons(args.horizons),
                model_versions=_parse_csv(args.model_versions),
            )
        except BacktestError as exc:
            print(f"Forecast failed: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote forecasts in {args.db}: {summary}")
        return 0

    if args.command == "backtest" and args.backtest_command == "run":
        try:
            result = run_backtest(
                args.db,
                horizons=_parse_horizons(args.horizons),
                lookback_days=args.lookback_days,
                embargo_days=args.embargo_days,
                model_versions=_parse_csv(args.model_versions),
            )
        except BacktestError as exc:
            print(f"Backtest failed: {exc}", file=sys.stderr)
            return 1
        print(f"Backtest completed in {args.db}: {result}")
        return 0

    if args.command == "model-validation" and args.model_validation_command == "replay-ytd":
        try:
            result = replay_ytd_predictions(
                args.db,
                year=args.year,
                start_date=args.start_date,
                end_date=args.end_date,
                horizons=_parse_horizons(args.horizons),
                model_versions=_parse_csv(args.model_versions),
                lookback_days=args.lookback_days,
                asset_scope=args.asset_scope,
            )
        except ModelValidationError as exc:
            print(f"Model replay failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "model-validation" and args.model_validation_command == "report":
        try:
            result = build_replay_report(args.db, run_id=args.run_id)
        except ModelValidationError as exc:
            print(f"Model replay report failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "model-validation" and args.model_validation_command == "tuning-plan":
        try:
            result = build_tuning_plan(args.db, run_id=args.run_id)
        except ModelValidationError as exc:
            print(f"Model tuning plan failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "advice" and args.advice_command == "generate":
        try:
            advice_id = generate_daily_advice(args.db, advice_date=args.date)
        except AdviceGenerationError as exc:
            print(f"Advice generation failed: {exc}", file=sys.stderr)
            return 1
        print(f"Generated daily advice id={advice_id} in {args.db}")
        return 0

    if args.command == "advice" and args.advice_command == "score-outcomes":
        try:
            scored = score_matured_advice(args.db, horizon_days=args.horizon_days)
        except AdviceScoringError as exc:
            print(f"Advice outcome scoring failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"scored": scored}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ai" and args.ai_command == "provider-check":
        config = load_ai_provider_config()
        request = AIProviderRequest(
            analysis_type=args.analysis_type,
            schema_version="ai_provider_check_v1",
            evidence_packet={"dry_run": True, "analysis_type": args.analysis_type},
            prompt="Dry-run adapter check. Return structured JSON only.",
            output_schema={"type": "object", "required": ["schema_version", "analysis_type", "risk_boundaries"]},
            metadata={"force_error": args.force_error, "force_timeout": args.force_timeout},
        )
        response = call_ai_provider(request, config)
        print(
            json.dumps(
                {
                    "ok": response.ok,
                    "provider": response.provider,
                    "model": response.model,
                    "source": response.source,
                    "status": response.status,
                    "duration_ms": response.duration_ms,
                    "fallback_reason": response.fallback_reason,
                    "error": response.error,
                    "output": response.output,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "prefs" and args.prefs_command == "list":
        init_db(args.db)
        with connect(args.db) as conn:
            preferences = [dict(row) for row in list_user_preferences(conn)]
            active = active_user_preference(conn)
        print(json.dumps({"active": dict(active) if active else None, "preferences": preferences}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prefs" and args.prefs_command == "set":
        init_db(args.db)
        if args.horizon_days <= 0:
            print("--horizon-days must be positive", file=sys.stderr)
            return 2
        if not 0 <= args.max_equity_pct <= 1 or not 0 <= args.min_cash_pct <= 1:
            print("--max-equity-pct and --min-cash-pct must be decimals between 0 and 1", file=sys.stderr)
            return 2
        with connect(args.db) as conn:
            preference_id = upsert_user_preference(
                conn,
                {
                    "profile_name": args.name,
                    "risk_profile": args.risk_profile,
                    "investment_horizon_days": args.horizon_days,
                    "max_equity_pct": args.max_equity_pct,
                    "min_cash_pct": args.min_cash_pct,
                    "notes": args.notes,
                    "is_active": 1,
                },
            )
        print(f"Saved active user preference id={preference_id} in {args.db}")
        return 0

    if args.command == "portfolio" and args.portfolio_command == "create":
        init_db(args.db)
        try:
            with connect(args.db) as conn:
                portfolio_id = create_virtual_portfolio(
                    conn,
                    owner_type=args.owner_type,
                    owner_id=args.owner_id,
                    name=args.name,
                    initial_capital=args.initial_capital,
                    currency=args.currency,
                )
                portfolio = dict(conn.execute("SELECT * FROM virtual_portfolios WHERE id = ?", (portfolio_id,)).fetchone())
        except PortfolioError as exc:
            print(f"Portfolio create failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"portfolio_id": portfolio_id, "portfolio": portfolio}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "portfolio" and args.portfolio_command == "list":
        init_db(args.db)
        with connect(args.db) as conn:
            portfolios = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT vp.*, vv.valuation_date, vv.total_value
                    FROM virtual_portfolios vp
                    LEFT JOIN virtual_valuations vv ON vv.id = (
                        SELECT id FROM virtual_valuations
                        WHERE portfolio_id = vp.id
                        ORDER BY valuation_date DESC, id DESC
                        LIMIT 1
                    )
                    ORDER BY vp.id
                    """
                ).fetchall()
            ]
        print(json.dumps({"count": len(portfolios), "portfolios": portfolios}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "portfolio" and args.portfolio_command == "trade":
        init_db(args.db)
        try:
            with connect(args.db) as conn:
                transaction = record_virtual_order(
                    conn,
                    portfolio_id=args.portfolio_id,
                    trade_date=args.date,
                    side=args.side,
                    asset_id=args.asset_id,
                    quantity=args.quantity,
                    fee=args.fee,
                    reason=args.reason or None,
                )
        except PortfolioError as exc:
            print(f"Portfolio trade failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"transaction": transaction}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "portfolio" and args.portfolio_command == "value":
        init_db(args.db)
        try:
            with connect(args.db) as conn:
                valuation = value_virtual_portfolio(conn, portfolio_id=args.portfolio_id, valuation_date=args.date)
        except PortfolioError as exc:
            print(f"Portfolio valuation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"valuation": valuation}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "configure-adapter":
        init_db(args.db)
        with connect(args.db) as conn:
            config_id = upsert_communication_adapter_config(
                conn,
                {
                    "channel": args.channel,
                    "enabled": 1 if args.enabled else 0,
                    "dry_run_default": 0 if args.real_send_default else 1,
                    "config_json": args.config_json,
                    "setup_status": "configured" if args.enabled else "disabled",
                    "last_verified_at": None,
                    "last_error": None,
                },
            )
        print(json.dumps({"adapter_config_id": config_id, "channel": args.channel}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "upsert-recipient":
        init_db(args.db)
        with connect(args.db) as conn:
            recipient_id = upsert_communication_recipient(
                conn,
                {
                    "recipient_key": args.recipient_key,
                    "display_name": args.display_name,
                    "channel": args.channel,
                    "address": args.address,
                    "allowlisted": 1 if args.allowlisted else 0,
                    "enabled": 0 if args.disabled else 1,
                    "min_severity": args.min_severity,
                    "quiet_hours_start": None,
                    "quiet_hours_end": None,
                    "rate_limit_per_hour": args.rate_limit_per_hour,
                    "retry_limit": args.retry_limit,
                    "notes": args.notes,
                },
            )
        print(json.dumps({"recipient_id": recipient_id, "recipient_key": args.recipient_key}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "list-adapters":
        init_db(args.db)
        with connect(args.db) as conn:
            adapters = [dict(row) for row in list_communication_adapter_configs(conn)]
        print(json.dumps({"count": len(adapters), "adapters": adapters}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "list-recipients":
        init_db(args.db)
        with connect(args.db) as conn:
            recipients = [dict(row) for row in list_communication_recipients(conn)]
        print(json.dumps({"count": len(recipients), "recipients": recipients}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "send-test":
        init_db(args.db)
        try:
            with connect(args.db) as conn:
                message = send_outbound_message(
                    conn,
                    channel=args.channel,
                    recipient_key=args.recipient_key,
                    template_key="test_message",
                    subject=args.subject,
                    body=args.body,
                    severity=args.severity,
                    payload_summary="CLI test message",
                    idempotency_key=args.idempotency_key,
                    dry_run=not args.real_send,
                )
        except CommunicationError as exc:
            print(f"Communication send failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"message": message}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "list-messages":
        init_db(args.db)
        with connect(args.db) as conn:
            messages = [dict(row) for row in list_outbound_messages(conn, limit=args.limit)]
        print(json.dumps({"count": len(messages), "messages": messages}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "communication" and args.communication_command == "verify-setup":
        init_db(args.db)
        with connect(args.db) as conn:
            result = verify_imessage_setup(
                conn,
                channel=args.channel,
                recipient_key=args.recipient_key,
                run_system_probe=not args.skip_system_probe,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    if args.command == "experts" and args.experts_command == "init":
        experts = initialize_default_experts(args.db)
        print(json.dumps({"active_count": len(experts), "experts": experts}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "experts" and args.experts_command == "init-portfolios":
        portfolios = ensure_expert_portfolios(args.db, initial_capital=args.initial_capital)
        print(json.dumps({"portfolio_count": len(portfolios), "portfolios": portfolios}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "experts" and args.experts_command == "list":
        experts = list_roster(args.db, lifecycle_state=args.state)
        print(json.dumps({"count": len(experts), "experts": experts}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "experts" and args.experts_command == "run-plans":
        try:
            plans = run_expert_daily_plans(
                args.db,
                plan_date=args.date,
                notify_recipient_key=args.notify_recipient_key,
                notification_channel=args.notification_channel,
                notification_dry_run=True if args.notification_dry_run else None,
            )
        except ExpertPlanningError as exc:
            print(f"Expert planning failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"plan_count": len(plans), "plans": plans}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "experts" and args.experts_command == "score":
        try:
            result = score_and_review_experts(
                args.db,
                review_date=args.date,
                window_days=args.window_days,
                min_valuations=args.min_valuations,
                notify_recipient_key=args.notify_recipient_key,
                notification_channel=args.notification_channel,
                notification_dry_run=True if args.notification_dry_run else None,
            )
        except ExpertScoringError as exc:
            print(f"Expert scoring failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "mcp" and args.mcp_command == "list-tools":
        print(json.dumps({"tools": list_tools()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "mcp" and args.mcp_command == "serve":
        server_args = ["--db", str(args.db), "--transport", args.transport, "--host", args.host, "--port", str(args.port)]
        return run_mcp_server_main(server_args)

    if args.command == "mcp" and args.mcp_command == "call":
        try:
            arguments = json.loads(args.args)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON arguments: {exc}", file=sys.stderr)
            return 2
        response = call_tool(args.db, args.tool_name, arguments)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if response["ok"] else 1

    if args.command == "daily" and args.daily_command == "run":
        try:
            result = run_daily_workflow(
                default_daily_config(
                    db_path=args.db,
                    run_date=args.date,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    horizons=_parse_horizons(args.horizons),
                    lookback_days=args.lookback_days,
                    skip_ingest=args.skip_ingest,
                    generate_jarvis=args.generate_jarvis,
                    notify_recipient_key=args.notify_recipient_key,
                    notification_channel=args.notification_channel,
                    notification_dry_run=True if args.notification_dry_run else None,
                )
            )
        except Exception as exc:
            print(f"Daily workflow failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "jarvis" and args.jarvis_command == "generate":
        notification = notification_defaults(
            recipient_key=args.notify_recipient_key,
            channel=args.notification_channel,
            dry_run=True if args.notification_dry_run else None,
        )
        try:
            brief = generate_jarvis_brief(
                args.db,
                brief_date=args.date,
                notify_recipient_key=notification.recipient_key,
                notification_channel=notification.channel,
                notification_dry_run=notification.dry_run,
            )
        except (JarvisSynthesisError, ValueError) as exc:
            print(f"Jarvis generation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"brief_id": brief["id"], "brief": brief}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "jarvis" and args.jarvis_command == "send-weekly":
        init_db(args.db)
        period_start, period_end = _weekly_period(args.start_date, args.end_date)
        try:
            with connect(args.db) as conn:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM jarvis_daily_briefs
                    WHERE brief_date BETWEEN ? AND ?
                    ORDER BY brief_date ASC, updated_at ASC, id ASC
                    """,
                    (period_start, period_end),
                ).fetchall()
                briefs = [deserialize_jarvis_brief(row) for row in rows]
                notification = render_jarvis_weekly_summary(
                    briefs,
                    period_start=period_start,
                    period_end=period_end,
                )
                message = send_rendered_notification(
                    conn,
                    channel=args.notification_channel,
                    recipient_key=args.recipient_key,
                    notification=notification,
                    dry_run=True if args.notification_dry_run else None,
                )
        except CommunicationError as exc:
            print(f"Weekly report send failed: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {"period_start": period_start, "period_end": period_end, "brief_count": len(briefs), "message": message},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "agent-runs" and args.agent_runs_command == "list":
        rows = list_runtime_agent_runs(
            args.db,
            role_type=args.role_type,
            role_key=args.role_key,
            status=args.status,
            limit=args.limit,
        )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "agent-runs" and args.agent_runs_command == "codex-readiness":
        adapter = CodexCliRuntimeAdapter(args.db, project_root=args.project_root, codex_bin=args.codex_bin)
        readiness = adapter.readiness()
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
        return 0 if readiness.get("ok") else 1

    if args.command == "agent-runs" and args.agent_runs_command == "codex-smoke":
        try:
            result = _run_codex_runtime_smoke(
                args.db,
                project_root=args.project_root,
                codex_bin=args.codex_bin,
                timeout_seconds=args.timeout_seconds,
            )
        except Exception as exc:
            print(f"Codex runtime smoke failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "agent-runs" and args.agent_runs_command == "run-experts-codex":
        result = run_expert_codex_agents(
            args.db,
            run_date=args.date,
            expert_key=args.expert_key,
            project_root=args.project_root,
            codex_bin=args.codex_bin,
            timeout_seconds=args.timeout_seconds,
            notify_recipient_key=args.notify_recipient_key,
            notification_channel=args.notification_channel,
            notification_dry_run=True if args.notification_dry_run else None,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "agent-runs" and args.agent_runs_command == "run-jarvis-codex":
        result = run_jarvis_codex_agent(
            args.db,
            run_date=args.date,
            target_evidence_date=args.target_evidence_date,
            project_root=args.project_root,
            codex_bin=args.codex_bin,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "scheduler" and args.scheduler_command == "list-jobs":
        initialize_scheduler(args.db, now=_parse_optional_datetime(args.now))
        print(json.dumps(list_scheduler_jobs(args.db), ensure_ascii=False, indent=2))
        return 0

    if args.command == "scheduler" and args.scheduler_command == "status":
        print(json.dumps(scheduler_status(args.db), ensure_ascii=False, indent=2))
        return 0

    if args.command == "scheduler" and args.scheduler_command == "run-due":
        result = run_due_jobs(args.db, now=_parse_optional_datetime(args.now))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "scheduler" and args.scheduler_command == "run-job":
        result = run_scheduler_job(args.db, args.job_key, now=_parse_optional_datetime(args.now))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"success", "skipped", "deferred"} else 1

    if args.command == "web" and args.web_command == "run":
        run_web_server(args.db, host=args.host, port=args.port)
        return 0

    if args.command == "calibration" and args.calibration_command == "run":
        try:
            report = run_calibration_report(
                args.db,
                report_date=args.date,
                horizons=_parse_horizons(args.horizons),
                lookback_days=args.lookback_days,
            )
        except CalibrationError as exc:
            print(f"Calibration failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "calibration" and args.calibration_command == "corpus":
        try:
            report = run_historical_calibration_corpus(
                args.db,
                start_date=args.start_date,
                end_date=args.end_date,
                report_date=args.date,
                horizons=_parse_horizons(args.horizons),
                lookback_days=args.lookback_days,
                skip_ingest=args.skip_ingest,
            )
        except CalibrationError as exc:
            print(f"Calibration corpus failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "monitoring" and args.monitoring_command == "run":
        try:
            report = run_model_monitoring_report(args.db, report_date=args.date)
        except ModelMonitoringError as exc:
            print(f"Monitoring failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "market" and args.market_command == "snapshot":
        try:
            snapshot = calculate_market_snapshot(args.db, snapshot_date=args.date)
        except MarketSnapshotError as exc:
            print(f"Market snapshot failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    parser.error("Unsupported command")
    return 2


def _parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not horizons:
        raise argparse.ArgumentTypeError("At least one horizon is required")
    return horizons


def _parse_csv(value: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in value.split(",") if part.strip())
    if not parts:
        raise argparse.ArgumentTypeError("At least one value is required")
    return parts


def _weekly_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    end = _normalize_cli_date(end_date) if end_date else date.today().isoformat()
    start = _normalize_cli_date(start_date) if start_date else (datetime.fromisoformat(end).date() - timedelta(days=6)).isoformat()
    return start, end


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _run_codex_runtime_smoke(
    db_path: Path,
    *,
    project_root: Path,
    codex_bin: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    adapter = CodexCliRuntimeAdapter(db_path, project_root=project_root, codex_bin=codex_bin)
    readiness = adapter.readiness()
    if not readiness.get("ok"):
        return {"ok": False, "stage": "readiness", "readiness": readiness}
    today = date.today().isoformat()
    request = build_launch_request(
        role_type="expert",
        role_key=f"local_codex_smoke_{datetime.now().strftime('%H%M%S')}",
        run_date=today,
        target_evidence_date=today,
        trigger_reason="local_codex_runtime_smoke",
        overview_skill="investment-expert-agent",
        skill_bundle=["investment-agent-output-contract"],
        prompt_ref={"kind": "smoke", "prompt_hash": "sha256:cli-smoke"},
        tool_manifest_ref={"kind": "smoke", "manifest_hash": "sha256:cli-smoke"},
        output_contract={"schema_version": "runtime_smoke_v1", "submission_tool": "artifact"},
        runtime_policy=CodexRuntimePolicy(
            timeout_seconds=timeout_seconds,
            max_tool_calls=0,
            max_retries=0,
            require_submission_tool=False,
        ),
    )
    handle = adapter.prepare_run(
        request,
        prompt='Return a JSON object only with exactly these fields: {"status":"ok","summary":"local codex runtime smoke passed"}. Do not run shell commands.',
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"status": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["status", "summary"],
        },
    )
    adapter.start_run(handle.agent_run_id)
    metadata = list_runtime_agent_runs(db_path, role_type="expert", role_key=request.role_key, limit=1)[0]["runtime_metadata"]
    last_message = Path(metadata["artifact_paths"]["last_message"])
    stderr_log = Path(metadata["artifact_paths"]["stderr_log"])
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        if last_message.exists() and last_message.read_text(encoding="utf-8").strip():
            result = adapter.collect_result(handle.agent_run_id)
            return {
                "ok": result.status == "completed_via_artifact",
                "agent_run_id": handle.agent_run_id,
                "status": result.status,
                "last_message": result.submission_result.get("last_message"),
                "artifact_paths": result.submission_result.get("artifact_paths"),
            }
        time.sleep(2)
    adapter.cancel_run(handle.agent_run_id, "codex runtime smoke timed out")
    return {
        "ok": False,
        "agent_run_id": handle.agent_run_id,
        "status": "timed_out",
        "stderr_tail": stderr_log.read_text(encoding="utf-8")[-2000:] if stderr_log.exists() else "",
    }


def _normalize_cli_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    datetime.fromisoformat(value)
    return value


def _add_provider_access_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider-min-delay", type=float, default=0.25, help="Minimum seconds between AKShare provider calls.")
    parser.add_argument("--provider-jitter", type=float, default=0.25, help="Optional random jitter seconds added to provider delay.")
    parser.add_argument("--provider-attempts", type=int, default=2, help="Attempts per network profile before trying fallback profiles.")
    parser.add_argument("--provider-backoff-base", type=float, default=0.5, help="Initial retry backoff seconds for transient provider failures.")
    parser.add_argument("--provider-backoff-max", type=float, default=5.0, help="Maximum retry backoff seconds for transient provider failures.")


def _add_provider_choice_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=["akshare", "tushare"], default="akshare", help="Market data provider; AKShare is the free default.")
    parser.add_argument("--tushare-token", help="Optional Tushare Pro token. Defaults to TUSHARE_TOKEN/TS_TOKEN when --provider=tushare.")


def _provider_from_args(args: argparse.Namespace) -> object:
    if getattr(args, "provider", "akshare") == "tushare":
        return TushareProvider(
            token=args.tushare_token,
            capital_flow_lookback_days=max(1, int(getattr(args, "tushare_lookback_days", 180))),
        )
    return _akshare_provider_from_args(args)


def _akshare_provider_from_args(args: argparse.Namespace) -> AkshareProvider:
    return AkshareProvider(
        retry_config=RetryConfig(
            attempts=max(1, int(args.provider_attempts)),
            backoff_base_seconds=max(0.0, float(args.provider_backoff_base)),
            max_backoff_seconds=max(0.0, float(args.provider_backoff_max)),
        ),
        access_policy=ProviderAccessPolicy(
            min_delay_seconds=max(0.0, float(args.provider_min_delay)),
            jitter_seconds=max(0.0, float(args.provider_jitter)),
        ),
    )


def _parse_series(value: str) -> tuple[str, ...]:
    series_ids = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    if not series_ids:
        raise argparse.ArgumentTypeError("At least one FRED series id is required")
    return series_ids


def _parse_asset_types(value: str) -> tuple[str, ...]:
    asset_types = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    allowed = {"stock", "etf", "fund"}
    invalid = set(asset_types) - allowed
    if invalid:
        raise argparse.ArgumentTypeError(f"Unsupported asset type(s): {', '.join(sorted(invalid))}")
    if not asset_types:
        raise argparse.ArgumentTypeError("At least one asset type is required")
    return asset_types


def _parse_optional_codes(value: str) -> tuple[str, ...]:
    return tuple(part.strip().zfill(6) for part in value.split(",") if part.strip())


if __name__ == "__main__":
    raise SystemExit(main())
