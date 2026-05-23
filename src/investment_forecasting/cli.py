from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from investment_forecasting.advice.generator import AdviceGenerationError, generate_daily_advice
from investment_forecasting.advice.scoring import AdviceScoringError, score_matured_advice
from investment_forecasting.data.ingestion import UNIVERSES, discover_akshare_universe, ingest_mvp_universe
from investment_forecasting.data.macro import DEFAULT_FRED_SERIES, ingest_fred_macro
from investment_forecasting.db import init_db
from investment_forecasting.mcp.tools import call_tool, list_tools
from investment_forecasting.mcp.server import main as run_mcp_server_main
from investment_forecasting.providers.akshare_provider import ProviderDataError
from investment_forecasting.providers.fred_provider import FredDataError
from investment_forecasting.quant.backtest import BacktestError, run_backtest, run_latest_forecasts
from investment_forecasting.quant.calibration import CalibrationError, run_calibration_report, run_historical_calibration_corpus
from investment_forecasting.quant.features import FeatureCalculationError, calculate_features_for_db
from investment_forecasting.quant.market import MarketSnapshotError, calculate_market_snapshot
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

    macro_parser = ingest_subparsers.add_parser("macro", help="Ingest free macro observations from FRED")
    macro_parser.add_argument("--db", type=Path, default=Path("data/investment_forecasting.sqlite3"))
    macro_parser.add_argument("--start-date", required=True, help="Start date in YYYYMMDD or YYYY-MM-DD format.")
    macro_parser.add_argument("--end-date", required=True, help="End date in YYYYMMDD or YYYY-MM-DD format.")
    macro_parser.add_argument(
        "--series",
        default=",".join(DEFAULT_FRED_SERIES),
        help="Comma-separated FRED series IDs. Defaults to DGS10,T10YIE,DTWEXBGS.",
    )
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
                universe=UNIVERSES[args.universe],
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

    if args.command == "ingest" and args.ingest_command == "full":
        try:
            asset_types = _parse_asset_types(args.asset_types)
            universe = discover_akshare_universe(
                asset_types=asset_types,
                max_assets=args.max_assets,
            )
            summary = ingest_mvp_universe(args.db, start_date=args.start_date, end_date=args.end_date, universe=universe)
        except argparse.ArgumentTypeError as exc:
            print(f"Invalid full universe options: {exc}", file=sys.stderr)
            return 2
        except ProviderDataError as exc:
            print(f"Full universe ingestion failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Ingested {total} rows for {len(summary)} discovered assets into {args.db}")
        return 0

    if args.command == "features" and args.features_command == "calculate":
        try:
            summary = calculate_features_for_db(args.db, start_date=args.start_date, end_date=args.end_date)
        except FeatureCalculationError as exc:
            print(f"Feature calculation failed: {exc}", file=sys.stderr)
            return 1
        total = sum(summary.values())
        print(f"Calculated {total} feature rows in {args.db}: {summary}")
        return 0

    if args.command == "forecast" and args.forecast_command == "run":
        try:
            summary = run_latest_forecasts(args.db, horizons=_parse_horizons(args.horizons))
        except BacktestError as exc:
            print(f"Forecast failed: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote baseline forecasts in {args.db}: {summary}")
        return 0

    if args.command == "backtest" and args.backtest_command == "run":
        try:
            result = run_backtest(args.db, horizons=_parse_horizons(args.horizons), lookback_days=args.lookback_days)
        except BacktestError as exc:
            print(f"Backtest failed: {exc}", file=sys.stderr)
            return 1
        print(f"Backtest completed in {args.db}: {result}")
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
                )
            )
        except Exception as exc:
            print(f"Daily workflow failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

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


if __name__ == "__main__":
    raise SystemExit(main())
