from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.data.ingestion import ingest_mvp_universe
from investment_forecasting.db import complete_task_log, connect, init_db, start_task_log
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot


@dataclass(frozen=True)
class DailyWorkflowConfig:
    db_path: Path
    run_date: str
    start_date: str
    end_date: str
    horizons: tuple[int, ...] = (5, 20, 60)
    lookback_days: int = 60
    skip_ingest: bool = False


def run_daily_workflow(config: DailyWorkflowConfig) -> dict[str, Any]:
    init_db(config.db_path)
    with connect(config.db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="daily_workflow",
            run_date=config.run_date,
            message=f"Daily workflow for {config.run_date}",
        )

    completed_steps: dict[str, Any] = {}
    try:
        if config.skip_ingest:
            completed_steps["ingest"] = {"skipped": True}
        else:
            completed_steps["ingest"] = ingest_mvp_universe(
                config.db_path,
                start_date=config.start_date,
                end_date=config.end_date,
            )
        completed_steps["features"] = calculate_features_for_db(
            config.db_path,
            start_date=config.start_date,
            end_date=config.end_date,
        )
        completed_steps["market_snapshot"] = calculate_market_snapshot(config.db_path, snapshot_date=config.run_date)
        completed_steps["forecast"] = run_latest_forecasts(config.db_path, horizons=config.horizons)
        completed_steps["backtest"] = run_backtest(
            config.db_path,
            horizons=config.horizons,
            lookback_days=config.lookback_days,
        )
        completed_steps["advice"] = {"advice_id": generate_daily_advice(config.db_path, advice_date=config.run_date)}

        with connect(config.db_path) as conn:
            complete_task_log(
                conn,
                log_id,
                status="success",
                message=json.dumps(completed_steps, ensure_ascii=False),
            )
        return {"ok": True, "run_date": config.run_date, "steps": completed_steps}
    except Exception as exc:
        with connect(config.db_path) as conn:
            complete_task_log(
                conn,
                log_id,
                status="failed",
                message=json.dumps(completed_steps, ensure_ascii=False),
                error=str(exc),
            )
        raise


def default_daily_config(
    db_path: str | Path,
    run_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    horizons: tuple[int, ...] = (5, 20, 60),
    lookback_days: int = 60,
    skip_ingest: bool = False,
) -> DailyWorkflowConfig:
    target_date = _date_text(run_date) if run_date else date.today().isoformat()
    end = _date_text(end_date) if end_date else target_date
    start = _date_text(start_date) if start_date else (datetime.fromisoformat(end) - timedelta(days=180)).date().isoformat()
    return DailyWorkflowConfig(
        db_path=Path(db_path),
        run_date=target_date,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        horizons=horizons,
        lookback_days=lookback_days,
        skip_ingest=skip_ingest,
    )


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if value:
        return value
    return date.today().isoformat()
