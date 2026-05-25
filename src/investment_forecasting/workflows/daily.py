from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.advice.scoring import score_matured_advice
from investment_forecasting.communication.config import notification_defaults
from investment_forecasting.communication.templates import render_daily_failure, render_daily_success, send_rendered_notification
from investment_forecasting.data.ingestion import ingest_mvp_universe
from investment_forecasting.db import complete_task_log, connect, init_db, start_task_log
from investment_forecasting.jarvis.synthesis import generate_jarvis_brief
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot
from investment_forecasting.quant.monitoring import run_model_monitoring_report


@dataclass(frozen=True)
class DailyWorkflowConfig:
    db_path: Path
    run_date: str
    start_date: str
    end_date: str
    horizons: tuple[int, ...] = (5, 20, 60)
    lookback_days: int = 60
    skip_ingest: bool = False
    generate_jarvis: bool = False
    notify_recipient_key: str | None = None
    notification_channel: str = "imessage"
    notification_dry_run: bool | None = None


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
                continue_on_error=True,
            )
        completed_steps["features"] = calculate_features_for_db(
            config.db_path,
            start_date=config.start_date,
            end_date=config.end_date,
            continue_on_error=True,
        )
        completed_steps["market_snapshot"] = calculate_market_snapshot(config.db_path, snapshot_date=config.run_date)
        completed_steps["forecast"] = run_latest_forecasts(config.db_path, horizons=config.horizons)
        completed_steps["backtest"] = run_backtest(
            config.db_path,
            horizons=config.horizons,
            lookback_days=config.lookback_days,
        )
        completed_steps["advice"] = {"advice_id": generate_daily_advice(config.db_path, advice_date=config.run_date)}
        completed_steps["advice_outcome_scores"] = score_matured_advice(
            config.db_path,
            horizon_days=min(config.horizons) if config.horizons else 20,
        )
        monitoring = run_model_monitoring_report(config.db_path, report_date=config.run_date)
        completed_steps["monitoring"] = {"count": monitoring["count"], "report_ids": monitoring["report_ids"]}
        if config.generate_jarvis:
            jarvis_brief = generate_jarvis_brief(config.db_path, brief_date=config.run_date)
            completed_steps["jarvis"] = {"brief_id": jarvis_brief["id"]}

        with connect(config.db_path) as conn:
            notification = _send_daily_success_notification(conn, config, completed_steps)
            if notification is not None:
                completed_steps["notification"] = notification
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
            _send_daily_failure_notification(conn, config, completed_steps, str(exc))
        raise


def default_daily_config(
    db_path: str | Path,
    run_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    horizons: tuple[int, ...] = (5, 20, 60),
    lookback_days: int = 60,
    skip_ingest: bool = False,
    generate_jarvis: bool = False,
    notify_recipient_key: str | None = None,
    notification_channel: str = "imessage",
    notification_dry_run: bool | None = None,
) -> DailyWorkflowConfig:
    target_date = _date_text(run_date) if run_date else date.today().isoformat()
    end = _date_text(end_date) if end_date else target_date
    start = _date_text(start_date) if start_date else (datetime.fromisoformat(end) - timedelta(days=180)).date().isoformat()
    notification = notification_defaults(
        recipient_key=notify_recipient_key,
        channel=notification_channel,
        dry_run=notification_dry_run,
    )
    return DailyWorkflowConfig(
        db_path=Path(db_path),
        run_date=target_date,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        horizons=horizons,
        lookback_days=lookback_days,
        skip_ingest=skip_ingest,
        generate_jarvis=generate_jarvis,
        notify_recipient_key=notification.recipient_key,
        notification_channel=notification.channel,
        notification_dry_run=notification.dry_run,
    )


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if value:
        return value
    return date.today().isoformat()


def _send_daily_success_notification(conn, config: DailyWorkflowConfig, completed_steps: dict[str, Any]) -> dict[str, Any] | None:
    if not config.notify_recipient_key:
        return None
    try:
        message = send_rendered_notification(
            conn,
            channel=config.notification_channel,
            recipient_key=config.notify_recipient_key,
            notification=render_daily_success(conn, run_date=config.run_date, steps=completed_steps),
            dry_run=config.notification_dry_run,
        )
        return _notification_summary(message)
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _send_daily_failure_notification(conn, config: DailyWorkflowConfig, completed_steps: dict[str, Any], error: str) -> dict[str, Any] | None:
    if not config.notify_recipient_key:
        return None
    try:
        message = send_rendered_notification(
            conn,
            channel=config.notification_channel,
            recipient_key=config.notify_recipient_key,
            notification=render_daily_failure(run_date=config.run_date, completed_steps=completed_steps, error=error),
            dry_run=config.notification_dry_run,
        )
        return _notification_summary(message)
    except Exception:
        return None


def _notification_summary(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id"),
        "status": message.get("status"),
        "duplicate": message.get("duplicate"),
        "template_key": message.get("template_key"),
        "error": message.get("error"),
    }
