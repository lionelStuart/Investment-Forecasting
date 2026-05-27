from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.advice.scoring import score_matured_advice
from investment_forecasting.data.news import ingest_news
from investment_forecasting.db import complete_task_log, connect, init_db, start_task_log, upsert_capital_flow_observation, upsert_price_daily
from investment_forecasting.providers.akshare_provider import AkshareProvider
from investment_forecasting.providers.tushare_provider import TushareProvider
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot
from investment_forecasting.quant.monitoring import run_model_monitoring_report
from investment_forecasting.scheduler.registry import DEFAULT_JOB_DEFINITIONS, SchedulerJobDefinition, next_run_after


TERMINAL_STATUSES = {"success", "skipped", "deferred", "failed"}
THROTTLE_MARKERS = ("429", "403", "too many", "rate limit", "captcha", "anti", "访问过于频繁", "限流", "验证码", "proxy", "dns")
CRON_LABEL = "local.investment-forecasting.scheduler"
LEGACY_AGENT_LABELS = ("local.investment-forecasting.experts", "local.investment-forecasting.jarvis")


def initialize_scheduler(db_path: str | Path, *, now: datetime | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    current = now or datetime.now()
    with connect(db_path) as conn:
        for definition in DEFAULT_JOB_DEFINITIONS:
            next_run = next_run_after(definition, current).isoformat(timespec="seconds")
            conn.execute(
                """
                INSERT INTO scheduler_jobs(
                    job_key, job_type, enabled, cadence, time_window_json,
                    provider_key, policy_json, next_run_at, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_key) DO UPDATE SET
                    job_type = excluded.job_type,
                    enabled = excluded.enabled,
                    cadence = excluded.cadence,
                    time_window_json = excluded.time_window_json,
                    provider_key = excluded.provider_key,
                    policy_json = excluded.policy_json,
                    next_run_at = COALESCE(scheduler_jobs.next_run_at, excluded.next_run_at),
                    description = excluded.description,
                    updated_at = datetime('now')
                """,
                (
                    definition.job_key,
                    definition.job_type,
                    1 if definition.enabled else 0,
                    definition.cadence,
                    json.dumps(definition.time_window, ensure_ascii=False, sort_keys=True),
                    definition.provider_key,
                    json.dumps(definition.policy, ensure_ascii=False, sort_keys=True),
                    next_run,
                    definition.description,
                ),
            )
    return list_scheduler_jobs(db_path)


def list_scheduler_jobs(db_path: str | Path) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM scheduler_jobs ORDER BY enabled DESC, job_key").fetchall()
    return [_job_row_to_dict(row) for row in rows]


def scheduler_status(db_path: str | Path) -> dict[str, Any]:
    initialize_scheduler(db_path)
    with connect(db_path) as conn:
        job_rows = conn.execute("SELECT * FROM scheduler_jobs ORDER BY job_key").fetchall()
        watermarks = conn.execute("SELECT * FROM scheduler_watermarks ORDER BY job_key, provider_key, source_key, scope_key").fetchall()
        rate_limits = conn.execute("SELECT * FROM provider_rate_limits ORDER BY provider_key").fetchall()
        latest_runs = {}
        for job in job_rows:
            run = conn.execute(
                "SELECT * FROM scheduler_runs WHERE job_key = ? ORDER BY started_at DESC, id DESC LIMIT 1",
                (job["job_key"],),
            ).fetchone()
            latest_runs[job["job_key"]] = _run_row_to_dict(run) if run else None
    return {
        "jobs": [_job_row_to_dict(row) for row in job_rows],
        "latest_runs": latest_runs,
        "watermarks": [_watermark_row_to_dict(row) for row in watermarks],
        "provider_rate_limits": [_rate_limit_row_to_dict(row) for row in rate_limits],
        "today": scheduler_today_status(db_path),
    }


def scheduler_today_status(db_path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    initialize_scheduler(db_path, now=now)
    current = now or datetime.now()
    today = current.date()
    today_text = today.isoformat()
    with connect(db_path) as conn:
        jobs = [_job_row_to_dict(row) for row in conn.execute("SELECT * FROM scheduler_jobs ORDER BY job_key").fetchall()]
        run_rows = [
            _run_row_to_dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM scheduler_runs
                WHERE substr(scheduled_at, 1, 10) = ?
                   OR substr(started_at, 1, 10) = ?
                ORDER BY started_at DESC, id DESC
                """,
                (today_text, today_text),
            ).fetchall()
        ]
        task_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, task_name, run_date, started_at, finished_at, status, message, error
                FROM task_logs
                WHERE run_date = ?
                  AND status != 'success'
                ORDER BY started_at DESC, id DESC
                LIMIT 50
                """,
                (today_text,),
            ).fetchall()
        ]
    runs_by_job: dict[str, list[dict[str, Any]]] = {}
    for run in run_rows:
        runs_by_job.setdefault(run["job_key"], []).append(run)

    items = [_today_status_item(job, runs_by_job.get(job["job_key"], []), today=today, now=current) for job in jobs]
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    overall = "bad" if counts.get("failed") or counts.get("missed") else ("warn" if counts.get("deferred") or counts.get("partial") else "ok")
    return {
        "date": today_text,
        "checked_at": current.isoformat(timespec="seconds"),
        "overall_status": overall,
        "counts": counts,
        "items": items,
        "task_log_failures": task_rows,
    }


def run_due_jobs(db_path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    initialize_scheduler(db_path, now=now)
    current = now or datetime.now()
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE enabled = 1
              AND next_run_at IS NOT NULL
              AND next_run_at <= ?
            ORDER BY next_run_at, job_key
            """,
            (current.isoformat(timespec="seconds"),),
        ).fetchall()
    runs = [run_scheduler_job(db_path, row["job_key"], now=current) for row in rows]
    return {"ok": all(run["status"] in TERMINAL_STATUSES and run["status"] != "failed" for run in runs), "due_count": len(rows), "runs": runs}


def run_scheduler_job(db_path: str | Path, job_key: str, *, now: datetime | None = None) -> dict[str, Any]:
    initialize_scheduler(db_path, now=now)
    current = now or datetime.now()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM scheduler_jobs WHERE job_key = ?", (job_key,)).fetchone()
        if row is None:
            raise ValueError(f"scheduler job not found: {job_key}")
        job = _job_row_to_dict(row)
        scheduled_at = job["next_run_at"] or current.isoformat(timespec="seconds")
        task_log_id = start_task_log(conn, "scheduler_job", date.today().isoformat(), f"Running scheduler job {job_key}")
        run_id = _insert_scheduler_run(conn, job_key=job_key, scheduled_at=scheduled_at)
    try:
        if job["job_type"] in {"expert_agents", "jarvis_agent"}:
            result = _run_agent_runtime_job(db_path, job, current)
        else:
            with connect(db_path) as conn:
                result = _run_deterministic_job(db_path, conn, job, current)
        status = result["status"]
        next_run = next_run_after(_definition_from_job(job), current).isoformat(timespec="seconds")
        with connect(db_path) as conn:
            conn.execute(
                """
                UPDATE scheduler_runs
                SET status = ?,
                    finished_at = datetime('now'),
                    updated_counts_json = ?,
                    skipped_reason = ?,
                    deferred_reason = ?,
                    provider_request_counts_json = ?,
                    metadata_json = ?,
                    error = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result.get("updated_counts", {}), ensure_ascii=False, sort_keys=True),
                    result.get("skipped_reason"),
                    result.get("deferred_reason"),
                    json.dumps(result.get("provider_request_counts", {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(result.get("metadata", {}), ensure_ascii=False, sort_keys=True),
                    result.get("error"),
                    run_id,
                ),
            )
            conn.execute(
                "UPDATE scheduler_jobs SET next_run_at = ?, updated_at = datetime('now') WHERE job_key = ?",
                (next_run, job_key),
            )
            task_log_status = "failed" if status == "failed" else "success"
            complete_task_log(conn, task_log_id, task_log_status, json.dumps({"job_key": job_key, **result}, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE scheduler_runs SET status = 'failed', finished_at = datetime('now'), error = ? WHERE id = ?",
                (str(exc), run_id),
            )
            complete_task_log(conn, task_log_id, "failed", error=str(exc))
        raise
    return _get_scheduler_run(db_path, run_id)


def install_scheduler_cron(
    db_path: str | Path,
    *,
    project_root: str | Path = ".",
    interval_minutes: int = 5,
    python_bin: str | None = None,
    load: bool = True,
    run_at_load: bool = True,
    reset_stale_next_runs: bool = True,
) -> dict[str, Any]:
    initialize_scheduler(db_path)
    if reset_stale_next_runs:
        refresh_stale_next_runs(db_path)
    root = Path(project_root).resolve()
    resolved_db = Path(db_path).resolve()
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents_dir / f"{CRON_LABEL}.plist"
    py = python_bin or sys.executable
    interval_seconds = max(60, int(interval_minutes) * 60)
    env = {
        "PATH": _scheduler_launch_path(),
        "PYTHONPATH": str(root / "src"),
        "INVESTMENT_FORECASTING_DB": str(resolved_db),
        "INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY": os.environ.get("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY", "owner_phone"),
        "INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL": os.environ.get("INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL", "imessage"),
        "INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN": os.environ.get("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN", "false"),
    }
    codex_bin = os.environ.get("INVESTMENT_FORECASTING_CODEX_BIN") or shutil.which("codex", path=env["PATH"])
    if codex_bin:
        env["INVESTMENT_FORECASTING_CODEX_BIN"] = codex_bin
    plist = _launchd_plist(
        label=CRON_LABEL,
        program_arguments=[py, "-m", "investment_forecasting.cli", "scheduler", "run-due", "--db", str(resolved_db)],
        working_directory=str(root),
        start_interval=interval_seconds,
        run_at_load=run_at_load,
        environment=env,
        stdout_path=str(root / ".runtime" / "scheduler_cron.log"),
        stderr_path=str(root / ".runtime" / "scheduler_cron.err.log"),
    )
    (root / ".runtime").mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist, encoding="utf-8")
    plist_path.chmod(0o644)

    commands: list[list[str]] = []
    if load:
        uid = os.getuid()
        domain = f"gui/{uid}"
        for label in (*LEGACY_AGENT_LABELS, CRON_LABEL):
            _launchctl(["bootout", f"{domain}/{label}"], check=False)
        _launchctl(["bootstrap", domain, str(plist_path)])
        _launchctl(["enable", f"{domain}/{CRON_LABEL}"])
        _launchctl(["print", f"{domain}/{CRON_LABEL}"])
        commands.append(["launchctl", "bootstrap", domain, str(plist_path)])
    return {
        "ok": True,
        "label": CRON_LABEL,
        "plist_path": str(plist_path),
        "db_path": str(resolved_db),
        "project_root": str(root),
        "interval_seconds": interval_seconds,
        "run_at_load": run_at_load,
        "reset_stale_next_runs": reset_stale_next_runs,
        "loaded": load,
        "legacy_labels_unloaded": list(LEGACY_AGENT_LABELS) if load else [],
        "commands": commands,
    }


def _scheduler_launch_path() -> str:
    paths = [
        *os.environ.get("PATH", "").split(os.pathsep),
        str(Path.home() / ".bun" / "bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        "/Applications/Codex.app/Contents/Resources",
    ]
    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if nvm_root.exists():
        paths.extend(str(path) for path in sorted(nvm_root.glob("*/bin"), reverse=True))
    deduped = []
    seen = set()
    for path in paths:
        if path and path not in seen:
            deduped.append(path)
            seen.add(path)
    return os.pathsep.join(deduped)


def uninstall_scheduler_cron(*, project_root: str | Path = ".", remove_plist: bool = False) -> dict[str, Any]:
    uid = os.getuid()
    domain = f"gui/{uid}"
    _launchctl(["bootout", f"{domain}/{CRON_LABEL}"], check=False)
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{CRON_LABEL}.plist"
    removed = False
    if remove_plist and plist_path.exists():
        plist_path.unlink()
        removed = True
    return {"ok": True, "label": CRON_LABEL, "plist_path": str(plist_path), "removed": removed, "project_root": str(Path(project_root).resolve())}


def refresh_stale_next_runs(db_path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    jobs = initialize_scheduler(db_path, now=current)
    refreshed = []
    with connect(db_path) as conn:
        for job in jobs:
            next_run_at = job.get("next_run_at")
            if next_run_at and next_run_at > current.isoformat(timespec="seconds"):
                continue
            next_run = next_run_after(_definition_from_job(job), current).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE scheduler_jobs SET next_run_at = ?, updated_at = datetime('now') WHERE job_key = ?",
                (next_run, job["job_key"]),
            )
            refreshed.append({"job_key": job["job_key"], "next_run_at": next_run})
    return {"ok": True, "refreshed": refreshed, "count": len(refreshed)}


def _today_status_item(job: dict[str, Any], runs: list[dict[str, Any]], *, today: date, now: datetime) -> dict[str, Any]:
    expected = _expected_occurrences_for_date(job, today)
    due = [item for item in expected if item <= now]
    due_runs = [run for run in runs if (_parse_cursor(run.get("scheduled_at")) or now) <= now]
    latest = due_runs[0] if due_runs else None
    failed = [run for run in due_runs if run.get("status") == "failed"]
    deferred = [run for run in due_runs if run.get("status") == "deferred"]
    success = [run for run in due_runs if run.get("status") == "success"]
    missed_count = max(0, len(due) - len(due_runs))
    if success and len(success) >= len(due):
        status = "success"
        reason = "今天到点任务已运行"
    elif success:
        status = "partial"
        reason = "今天部分到点任务已成功"
    elif failed:
        status = "failed"
        reason = failed[0].get("error") or "今天有失败运行"
    elif deferred:
        status = "deferred"
        reason = deferred[0].get("deferred_reason") or "今天有延后运行"
    elif missed_count:
        status = "missed"
        reason = "今天已有到点任务未记录运行"
    elif expected:
        status = "not_yet_due"
        reason = "今天任务尚未到触发时间"
    else:
        status = "no_run_expected"
        reason = "今天不在该任务触发日历内"
    return {
        "job_key": job["job_key"],
        "job_type": job["job_type"],
        "enabled": job["enabled"],
        "status": status,
        "reason": reason,
        "expected_count": len(expected),
        "due_count": len(due),
        "run_count": len(due_runs),
        "success_count": len(success),
        "failed_count": len(failed),
        "deferred_count": len(deferred),
        "missed_count": missed_count,
        "next_expected_at": _format_dt(next((item for item in expected if item > now), None)),
        "last_run_status": latest.get("status") if latest else None,
        "last_run_started_at": latest.get("started_at") if latest else None,
        "last_run_scheduled_at": latest.get("scheduled_at") if latest else None,
    }


def _expected_occurrences_for_date(job: dict[str, Any], day: date) -> list[datetime]:
    if not job.get("enabled"):
        return []
    cadence = job["cadence"]
    window = job.get("time_window", {})
    if bool(window.get("weekdays_only")) and day.weekday() >= 5:
        return []
    if cadence == "daily":
        return [_combine_date_hhmm(day, str(window["fixed_time"]))]
    if cadence == "fixed_times":
        return [_combine_date_hhmm(day, str(value)) for value in sorted(window.get("fixed_times", []))]
    if cadence == "hourly":
        fixed_minute = int(window.get("fixed_minute", 0))
        return [datetime(day.year, day.month, day.day, hour, fixed_minute) for hour in range(24)]
    if cadence == "interval_hours":
        interval = max(1, int(window.get("interval_hours", 2)))
        fixed_minute = int(window.get("fixed_minute", 0))
        return [datetime(day.year, day.month, day.day, hour, fixed_minute) for hour in range(24) if hour % interval == 0]
    return []


def _combine_date_hhmm(day: date, hhmm: str) -> datetime:
    hour, minute = hhmm.split(":", 1)
    return datetime(day.year, day.month, day.day, int(hour), int(minute))


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _run_agent_runtime_job(db_path: str | Path, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    from investment_forecasting.agent_runtime.execution import run_expert_codex_agents, run_jarvis_codex_agent

    run_date = now.date().isoformat()
    project_root = Path.cwd()
    timeout_seconds = int(job.get("policy", {}).get("timeout_seconds") or 600)
    if job["job_type"] == "expert_agents":
        result = run_expert_codex_agents(
            db_path,
            run_date=run_date,
            project_root=project_root,
            timeout_seconds=timeout_seconds,
        )
        return _agent_scheduler_result(job, result, ok_status="success")
    if job["job_type"] == "jarvis_agent":
        evidence_date = _previous_weekday(now.date()).isoformat()
        result = run_jarvis_codex_agent(
            db_path,
            run_date=run_date,
            target_evidence_date=evidence_date,
            project_root=project_root,
            timeout_seconds=timeout_seconds,
            notify_recipient_key=os.environ.get("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY", "owner_phone"),
            notification_channel=os.environ.get("INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL", "imessage"),
            notification_dry_run=_env_bool("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN", default=False),
        )
        return _agent_scheduler_result(job, result, ok_status="success")
    return {"status": "failed", "error": f"unsupported agent job type: {job['job_type']}"}


def _agent_scheduler_result(job: dict[str, Any], result: dict[str, Any], *, ok_status: str) -> dict[str, Any]:
    ok = bool(result.get("ok"))
    runs = result.get("runs") or []
    if ok:
        status = ok_status
        deferred_reason = None
    else:
        status = "deferred" if result.get("stage") == "readiness" else "failed"
        deferred_reason = _agent_deferred_reason(result)
    return {
        "status": status,
        "deferred_reason": deferred_reason,
        "updated_counts": {
            "agent_runs": len(runs),
            "completed_runs": sum(1 for run in runs if run.get("ok") or run.get("status") == "completed"),
        },
        "provider_request_counts": {job.get("provider_key"): 1 if runs else 0} if job.get("provider_key") else {},
        "metadata": {
            "real_provider_calls": False,
            "agent_runtime": True,
            "job_type": job["job_type"],
            "result": result,
        },
    }


def _agent_deferred_reason(result: dict[str, Any]) -> str | None:
    if result.get("readiness"):
        return json.dumps(result["readiness"], ensure_ascii=False, sort_keys=True)
    if result.get("expert_runtime_status"):
        return json.dumps(result["expert_runtime_status"], ensure_ascii=False, sort_keys=True)
    if result.get("stage"):
        return f"agent runtime {result['stage']} not ready"
    return None


def _previous_weekday(value: date) -> date:
    target = value - timedelta(days=1)
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _launchctl(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *arguments], check=check, text=True, capture_output=True)


def _launchd_plist(
    *,
    label: str,
    program_arguments: list[str],
    working_directory: str,
    start_interval: int,
    run_at_load: bool,
    environment: dict[str, str],
    stdout_path: str,
    stderr_path: str,
) -> str:
    args_xml = "\n".join(f"    <string>{_xml_escape(value)}</string>" for value in program_arguments)
    env_xml = "\n".join(f"    <key>{_xml_escape(key)}</key><string>{_xml_escape(value)}</string>" for key, value in sorted(environment.items()))
    run_at_load_xml = "true" if run_at_load else "false"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_xml_escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>StartInterval</key>
  <integer>{int(start_interval)}</integer>
  <key>RunAtLoad</key>
  <{run_at_load_xml}/>
  <key>WorkingDirectory</key>
  <string>{_xml_escape(working_directory)}</string>
  <key>EnvironmentVariables</key>
  <dict>
{env_xml}
  </dict>
  <key>StandardOutPath</key>
  <string>{_xml_escape(stdout_path)}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(stderr_path)}</string>
</dict>
</plist>
"""


def _xml_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _run_deterministic_job(db_path: str | Path, conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    provider_key = job.get("provider_key")
    policy = job.get("policy", {})
    deferred = _provider_defer_reason(conn, provider_key, policy, now)
    if deferred:
        return {
            "status": "deferred",
            "deferred_reason": deferred,
            "provider_request_counts": {provider_key: 0} if provider_key else {},
            "updated_counts": {},
            "metadata": {"real_provider_calls": False, "job_type": job["job_type"]},
        }

    try:
        result = _run_incremental_job(db_path, conn, job, now)
    except Exception as exc:
        if provider_key:
            _record_provider_failure_conn(
                conn,
                provider_key,
                str(exc),
                now=now,
                backoff_minutes=int(policy.get("backoff_minutes") or 30),
            )
        return {
            "status": "failed",
            "error": str(exc),
            "provider_request_counts": {provider_key: 0} if provider_key else {},
            "updated_counts": {},
            "metadata": {"real_provider_calls": True, "job_type": job["job_type"], "failed_stage": "deterministic_job"},
        }
    request_count = sum(int(value) for value in result.get("provider_request_counts", {}).values())
    if provider_key and request_count:
        _record_provider_success(conn, provider_key, request_count, policy, now)
    return result


def _run_incremental_job(db_path: str | Path, conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    job_type = job["job_type"]
    if job_type == "news_incremental":
        return _run_news_incremental(db_path, conn, job, now)
    if job_type == "market_context_incremental":
        return _run_market_context_incremental(db_path, conn, job, now)
    if job_type == "price_nav_incremental":
        return _run_price_nav_incremental(conn, job, now)
    if job_type == "features_incremental":
        return _run_features_incremental(db_path, conn, job, now)
    if job_type == "model_post_close":
        return _run_model_post_close_job(db_path, conn, job, now)
    if job_type in {"expert_agents", "jarvis_agent"}:
        return _run_agent_gate_job(conn, job, now)
    watermark_cursor = now.isoformat(timespec="seconds")
    _upsert_watermark(
        conn,
        job_key=job["job_key"],
        provider_key=job.get("provider_key"),
        source_key=job.get("policy", {}).get("watermark_scope", ""),
        scope_key=job_type,
        success_cursor=watermark_cursor,
        attempted_cursor=watermark_cursor,
        metadata={"real_provider_calls": False, "job_type": job_type},
    )
    return {
        "status": "success",
        "updated_counts": {"scheduler_job_run": 1},
        "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
        "metadata": {
            "real_provider_calls": False,
            "job_type": job_type,
            "fixed_sync": job["time_window"],
        },
    }


def _run_news_incremental(db_path: str | Path, conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    provider_key = job.get("provider_key")
    policy = job.get("policy", {})
    window_minutes = int(policy.get("window_minutes") or 65)
    sources = [str(source) for source in policy.get("sources", ["sina"])]
    planned = []
    request_count = 0
    fetched_count = 0
    inserted_count = 0
    provider = _news_provider()
    for source in sources:
        watermark = _get_watermark(conn, job["job_key"], provider_key, source, "news")
        start = _parse_cursor(watermark["last_success_cursor"] if watermark else None) or (now - timedelta(minutes=window_minutes))
        if start >= now:
            planned.append({"source": source, "skipped": True, "reason": "already_current", "start": start.isoformat(timespec="seconds"), "end": now.isoformat(timespec="seconds")})
            _upsert_watermark(
                conn,
                job_key=job["job_key"],
                provider_key=provider_key,
                source_key=source,
                scope_key="news",
                success_cursor=start.isoformat(timespec="seconds"),
                attempted_cursor=now.isoformat(timespec="seconds"),
                metadata={"incremental": True, "bounded_window": True, "real_provider_calls": False, "skipped": True},
            )
            continue
        start_text = start.isoformat(timespec="seconds")
        end_text = now.isoformat(timespec="seconds")
        max_items = int(policy.get("request_cap") or 200)
        summary = ingest_news(
            db_path,
            provider=provider,
            source=source,
            start_datetime=start_text,
            end_datetime=end_text,
            max_items=max_items,
        )
        request_count += 1
        fetched_count += int(summary.get("fetched_count") or 0)
        inserted_count += int(summary.get("inserted_count") or 0)
        planned.append({"source": source, "start": start_text, "end": end_text, "max_items": max_items, "summary": summary})
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=provider_key,
            source_key=source,
            scope_key="news",
            success_cursor=end_text,
            attempted_cursor=end_text,
            metadata={"incremental": True, "bounded_window": True, "real_provider_calls": True, "window_minutes": window_minutes, "summary": summary},
        )
    return {
        "status": "success" if request_count else "skipped",
        "skipped_reason": None if request_count else "news watermarks already current",
        "updated_counts": {"news_windows": request_count, "sources": len(sources), "fetched_news": fetched_count, "inserted_news": inserted_count},
        "provider_request_counts": {provider_key: request_count} if provider_key else {},
        "metadata": {"real_provider_calls": True, "incremental": True, "bounded_window": True, "planned_windows": planned, "policy": _policy_summary(policy)},
    }


def _run_market_context_incremental(db_path: str | Path, conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    provider_key = job.get("provider_key")
    policy = job.get("policy", {})
    stock_limit = int(policy.get("stock_limit") or 20)
    stock_rows = conn.execute(
        "SELECT id, code, name FROM assets WHERE asset_type = 'stock' AND status = 'active' ORDER BY code LIMIT ?",
        (stock_limit,),
    ).fetchall()
    subjects = [{"scope": "market", "subject": "market"}] + [{"scope": "stock", "subject": row["code"], "asset_id": row["id"]} for row in stock_rows]
    request_cap = int(policy.get("request_cap") or 40)
    planned = subjects[:request_cap]
    provider = _market_provider()
    inserted_count = 0
    max_days = int(policy.get("max_days") or 5)
    for item in planned:
        if item["scope"] == "market":
            rows = list(provider.market_capital_flow())[-max_days:]
            summary = {"market": _persist_capital_flow_rows(conn, rows)}
        else:
            rows = list(provider.stock_capital_flow(str(item["subject"])))[-max_days:]
            for row in rows:
                row["asset_id"] = int(item["asset_id"])
                row["subject_code"] = str(item["subject"])
            summary = {str(item["subject"]): _persist_capital_flow_rows(conn, rows)}
        item_inserted = sum(int(value) for value in summary.values())
        inserted_count += item_inserted
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=provider_key,
            source_key=str(item["subject"]),
            scope_key=f"capital_flow:{item['scope']}",
            success_cursor=now.date().isoformat() if item_inserted else None,
            attempted_cursor=now.date().isoformat(),
            metadata={"incremental": True, "real_provider_calls": True, "source": "capital_flow_observations", "summary": summary},
        )
    return {
        "status": "success" if inserted_count else ("skipped" if not planned else "failed"),
        "skipped_reason": None if planned else "no tracked market context subjects",
        "error": None if inserted_count or not planned else "provider returned no capital flow rows for planned subjects",
        "updated_counts": {"capital_flow_subjects": len(planned), "capital_flow_rows": inserted_count, "skipped_by_cap": max(0, len(subjects) - len(planned))},
        "provider_request_counts": {provider_key: len(planned)} if provider_key else {},
        "metadata": {"real_provider_calls": True, "incremental": True, "planned_subjects": planned, "policy": _policy_summary(policy)},
    }


def _persist_capital_flow_rows(conn: Any, rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        upsert_capital_flow_observation(
            conn,
            {
                "asset_id": None,
                **row,
                "source": row.get("source") or "akshare",
            },
        )
        count += 1
    return count


def _run_price_nav_incremental(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    provider_key = job.get("provider_key")
    policy = job.get("policy", {})
    target_date = _target_market_date(now).isoformat()
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.asset_type, a.market, a.source, MAX(p.trade_date) AS latest_trade_date
        FROM assets a
        LEFT JOIN price_daily p ON p.asset_id = a.id AND p.source = a.source
        WHERE a.status = 'active'
        GROUP BY a.id
        ORDER BY a.asset_type, a.code
        """
    ).fetchall()
    request_cap = int(policy.get("request_cap") or 500)
    stale = [row for row in rows if not row["latest_trade_date"] or str(row["latest_trade_date"]) < target_date]
    planned = stale[:request_cap]
    provider = _market_provider()
    written_by_asset: dict[str, int] = {}
    for row in rows:
        source_key = f"{row['asset_type']}:{row['code']}"
        latest = row["latest_trade_date"] or ""
        attempted = target_date if row in planned else latest
        success_cursor = latest
        written = 0
        if row in planned:
            asset = _provider_asset(row)
            start_date = _next_market_date(latest).strftime("%Y%m%d") if latest else target_date.replace("-", "")
            end_date = target_date.replace("-", "")
            prices = provider.history(asset, start_date=start_date, end_date=end_date)
            source = str(row["source"] or getattr(provider, "source", provider_key or "akshare"))
            for price in prices:
                upsert_price_daily(conn, asset_id=int(row["id"]), source=source, price=price)
                written += 1
            if written:
                success_cursor = max(str(price["trade_date"]) for price in prices)
            written_by_asset[str(row["code"])] = written
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=provider_key,
            source_key=source_key,
            scope_key="price_daily",
            success_cursor=success_cursor,
            attempted_cursor=attempted,
            metadata={
                "incremental": True,
                "real_provider_calls": row in planned,
                "target_date": target_date,
                "already_current": row not in planned,
                "written_rows": written,
            },
        )
    written_rows = sum(written_by_asset.values())
    return {
        "status": "success" if written_rows else ("skipped" if not planned else "failed"),
        "skipped_reason": None if planned else f"all tracked assets are current for {target_date}",
        "error": None if written_rows or not planned else "provider returned no price rows for planned stale assets",
        "updated_counts": {"stale_assets": len(stale), "planned_assets": len(planned), "written_price_rows": written_rows, "current_assets": len(rows) - len(stale), "skipped_by_cap": max(0, len(stale) - len(planned))},
        "provider_request_counts": {provider_key: len(planned)} if provider_key else {},
        "metadata": {"real_provider_calls": bool(planned), "incremental": True, "target_date": target_date, "planned_assets": [_asset_plan(row, target_date) for row in planned], "written_by_asset": written_by_asset, "policy": _policy_summary(policy)},
    }


def _run_features_incremental(db_path: str | Path, conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    target_date = _target_market_date(now).isoformat()
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.asset_type, MAX(p.trade_date) AS latest_price_date, MAX(f.feature_date) AS latest_feature_date
        FROM assets a
        LEFT JOIN price_daily p ON p.asset_id = a.id
        LEFT JOIN features_daily f ON f.asset_id = a.id
        WHERE a.status = 'active'
        GROUP BY a.id
        ORDER BY a.asset_type, a.code
        """
    ).fetchall()
    affected = [row for row in rows if row["latest_price_date"] and (not row["latest_feature_date"] or str(row["latest_feature_date"]) < str(row["latest_price_date"]))]
    calculated: dict[int, int] = {}
    if affected:
        start_date = min(str(row["latest_feature_date"] or row["latest_price_date"]) for row in affected)
        end_date = max(str(row["latest_price_date"]) for row in affected)
        calculated = calculate_features_for_db(db_path, start_date=start_date, end_date=end_date, continue_on_error=True)
    for row in rows:
        latest_feature = row["latest_feature_date"] or ""
        latest_price = row["latest_price_date"] or ""
        written = int(calculated.get(int(row["id"]), 0))
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=job.get("provider_key"),
            source_key=f"{row['asset_type']}:{row['code']}",
            scope_key="features_daily",
            success_cursor=latest_price if row in affected and written else latest_feature,
            attempted_cursor=latest_price or target_date,
            metadata={"incremental": True, "real_provider_calls": False, "real_calculation": row in affected, "affected": row in affected, "written_rows": written},
        )
    written_rows = sum(int(value) for value in calculated.values())
    return {
        "status": "success" if written_rows else ("skipped" if not affected else "failed"),
        "skipped_reason": None if affected else "features already cover latest stored prices",
        "error": None if written_rows or not affected else "feature calculator returned no rows for affected assets",
        "updated_counts": {"affected_assets": len(affected), "written_feature_rows": written_rows, "current_assets": len(rows) - len(affected)},
        "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
        "metadata": {"real_provider_calls": False, "real_calculation": bool(affected), "incremental": True, "target_date": target_date, "affected_ranges": [_feature_plan(row) for row in affected]},
    }


def _run_model_post_close_job(db_path: str | Path, conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    missing = _missing_required_watermarks(conn, ("price_nav_post_close", "features_post_close"))
    if missing:
        return _record_readiness_gate_result(conn, job, now, missing=missing)

    policy = job.get("policy", {})
    horizons = tuple(int(value) for value in policy.get("horizons", (5, 20, 60)))
    run_date = _target_market_date(now).isoformat()
    forecast_summary = run_latest_forecasts(db_path, horizons=horizons)
    backtest_summary = run_backtest(db_path, horizons=horizons, lookback_days=int(policy.get("lookback_days") or 60))
    snapshot = calculate_market_snapshot(db_path, snapshot_date=run_date)
    advice_id = generate_daily_advice(db_path, advice_date=run_date)
    scored = score_matured_advice(db_path, horizon_days=int(policy.get("score_horizon_days") or 20))
    monitoring = run_model_monitoring_report(db_path, report_date=run_date)

    cursor = now.isoformat(timespec="seconds")
    _upsert_watermark(
        conn,
        job_key=job["job_key"],
        provider_key=job.get("provider_key"),
        source_key="model",
        scope_key=job["job_type"],
        success_cursor=cursor,
        attempted_cursor=cursor,
        metadata={"real_provider_calls": False, "real_model_run": True, "run_date": run_date},
    )
    return {
        "status": "success",
        "updated_counts": {
            "forecast_assets": len(forecast_summary),
            "forecast_rows": sum(int(value) for value in forecast_summary.values()),
            "backtest_runs": len(backtest_summary.get("run_ids", [])),
            "market_snapshot_id": snapshot.get("id"),
            "advice_id": advice_id,
            "scored_advice": scored,
            "monitoring_reports": monitoring.get("count", 0),
        },
        "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
        "metadata": {
            "real_provider_calls": False,
            "real_model_run": True,
            "run_date": run_date,
            "forecast": forecast_summary,
            "backtest": backtest_summary,
            "monitoring": monitoring,
        },
    }


def _missing_required_watermarks(conn: Any, required_watermarks: tuple[str, ...]) -> list[str]:
    missing = []
    for required in required_watermarks:
        row = conn.execute(
            "SELECT MAX(last_success_cursor) AS cursor FROM scheduler_watermarks WHERE job_key = ?",
            (required,),
        ).fetchone()
        if not row or not row["cursor"]:
            missing.append(required)
    return missing


def _record_readiness_gate_result(conn: Any, job: dict[str, Any], now: datetime, *, missing: list[str]) -> dict[str, Any]:
    cursor = now.isoformat(timespec="seconds")
    _upsert_watermark(
        conn,
        job_key=job["job_key"],
        provider_key=job.get("provider_key"),
        source_key="readiness",
        scope_key=job["job_type"],
        success_cursor=None if missing else cursor,
        attempted_cursor=cursor,
        metadata={"readiness_gate": True, "missing": missing, "real_provider_calls": False},
    )
    if missing:
        return {
            "status": "deferred",
            "deferred_reason": f"readiness gate missing: {', '.join(missing)}",
            "updated_counts": {},
            "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
            "metadata": {"readiness_gate": True, "missing": missing, "real_provider_calls": False},
        }
    return {
        "status": "success",
        "updated_counts": {"readiness_gate_passed": 1},
        "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
        "metadata": {"readiness_gate": True, "real_provider_calls": False},
    }


def _run_readiness_gate_job(conn: Any, job: dict[str, Any], now: datetime, *, required_watermarks: tuple[str, ...]) -> dict[str, Any]:
    missing = _missing_required_watermarks(conn, required_watermarks)
    return _record_readiness_gate_result(conn, job, now, missing=missing)


def _run_agent_gate_job(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    cursor = now.isoformat(timespec="seconds")
    _upsert_watermark(
        conn,
        job_key=job["job_key"],
        provider_key=job.get("provider_key"),
        source_key="readiness",
        scope_key=job["job_type"],
        success_cursor=None,
        attempted_cursor=cursor,
        metadata={"readiness_gate": job.get("policy", {}).get("readiness_gate"), "gated": True, "real_provider_calls": False},
    )
    return {
        "status": "deferred",
        "deferred_reason": f"agent runtime job is gated by {job.get('policy', {}).get('readiness_gate')}",
        "updated_counts": {},
        "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
        "metadata": {"gated": True, "real_provider_calls": False, "readiness_gate": job.get("policy", {}).get("readiness_gate")},
    }


def _news_provider() -> Any:
    return TushareProvider()


def _market_provider() -> Any:
    return AkshareProvider()


def _provider_asset(row: Any) -> Any:
    return SimpleNamespace(
        id=int(row["id"]),
        code=str(row["code"]),
        name=str(row["name"] or row["code"]) if "name" in row.keys() else str(row["code"]),
        asset_type=str(row["asset_type"]),
        market=str(row["market"] or "CN"),
        source=str(row["source"] or "akshare"),
        provider_symbol=_provider_symbol(str(row["asset_type"]), str(row["code"])),
    )


def _provider_symbol(asset_type: str, code: str) -> str | None:
    if asset_type not in {"stock", "index", "etf"}:
        return None
    if asset_type == "index" and code.startswith("000"):
        prefix = "sh"
    else:
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


def _next_market_date(latest: str) -> date:
    try:
        value = datetime.fromisoformat(str(latest)).date()
    except ValueError:
        value = datetime.strptime(str(latest), "%Y%m%d").date()
    value += timedelta(days=1)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def _provider_defer_reason(conn: Any, provider_key: str | None, policy: dict[str, Any], now: datetime) -> str | None:
    if not provider_key:
        return None
    rate_limit = conn.execute("SELECT * FROM provider_rate_limits WHERE provider_key = ?", (provider_key,)).fetchone()
    now_text = now.isoformat(timespec="seconds")
    if rate_limit and rate_limit["backoff_until"] and rate_limit["backoff_until"] > now_text:
        return f"provider backoff active until {rate_limit['backoff_until']}"
    hourly_budget = int(policy.get("hourly_request_budget") or policy.get("request_cap") or 0)
    daily_budget = int(policy.get("daily_request_budget") or max(hourly_budget, 0))
    hourly_count, daily_count = _provider_counts_for_window(rate_limit, now) if rate_limit else (0, 0)
    if hourly_budget and hourly_count >= hourly_budget:
        return f"provider hourly budget exhausted for {provider_key}"
    if daily_budget and daily_count >= daily_budget:
        return f"provider daily budget exhausted for {provider_key}"
    return None


def _record_provider_success(conn: Any, provider_key: str, request_count: int, policy: dict[str, Any], now: datetime) -> None:
    rate_limit = conn.execute("SELECT * FROM provider_rate_limits WHERE provider_key = ?", (provider_key,)).fetchone()
    hourly_count, daily_count = _provider_counts_for_window(rate_limit, now) if rate_limit else (0, 0)
    metadata = {
        "last_policy": _policy_summary(policy),
        "last_success_at": now.isoformat(timespec="seconds"),
    }
    conn.execute(
        """
        INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, backoff_until, failure_count, last_failure_reason, metadata_json)
        VALUES (?, ?, ?, NULL, 0, NULL, ?)
        ON CONFLICT(provider_key) DO UPDATE SET
            hourly_count = excluded.hourly_count,
            daily_count = excluded.daily_count,
            backoff_until = NULL,
            failure_count = 0,
            last_failure_reason = NULL,
            metadata_json = excluded.metadata_json,
            updated_at = datetime('now')
        """,
        (provider_key, hourly_count + request_count, daily_count + request_count, json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
    )


def _record_provider_failure_conn(conn: Any, provider_key: str, reason: str, *, now: datetime, backoff_minutes: int) -> None:
    factor = 2 if _looks_throttled(reason) else 1
    backoff_until = now + timedelta(minutes=max(1, backoff_minutes) * factor)
    conn.execute(
        """
        INSERT INTO provider_rate_limits(provider_key, backoff_until, failure_count, last_failure_reason, metadata_json)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(provider_key) DO UPDATE SET
            backoff_until = excluded.backoff_until,
            failure_count = provider_rate_limits.failure_count + 1,
            last_failure_reason = excluded.last_failure_reason,
            metadata_json = excluded.metadata_json,
            updated_at = datetime('now')
        """,
        (
            provider_key,
            backoff_until.isoformat(timespec="seconds"),
            reason,
            json.dumps({"likely_throttled": _looks_throttled(reason), "recorded_at": now.isoformat(timespec="seconds")}, ensure_ascii=False, sort_keys=True),
        ),
    )


def _provider_counts_for_window(rate_limit: Any, now: datetime) -> tuple[int, int]:
    if rate_limit is None:
        return (0, 0)
    metadata = _json_loads(rate_limit["metadata_json"], {})
    last_success_at = metadata.get("last_success_at")
    if not last_success_at:
        return (int(rate_limit["hourly_count"] or 0), int(rate_limit["daily_count"] or 0))
    try:
        last_success = datetime.fromisoformat(str(last_success_at))
    except ValueError:
        return (int(rate_limit["hourly_count"] or 0), int(rate_limit["daily_count"] or 0))
    hourly_count = int(rate_limit["hourly_count"] or 0) if last_success.date() == now.date() and last_success.hour == now.hour else 0
    daily_count = int(rate_limit["daily_count"] or 0) if last_success.date() == now.date() else 0
    return hourly_count, daily_count


def _json_loads(raw: Any, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return default


def record_provider_failure(
    db_path: str | Path,
    provider_key: str,
    reason: str,
    *,
    now: datetime | None = None,
    backoff_minutes: int = 30,
) -> dict[str, Any]:
    init_db(db_path)
    current = now or datetime.now()
    factor = 2 if _looks_throttled(reason) else 1
    backoff_until = current + timedelta(minutes=max(1, backoff_minutes) * factor)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, backoff_until, failure_count, last_failure_reason, metadata_json)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(provider_key) DO UPDATE SET
                backoff_until = excluded.backoff_until,
                failure_count = provider_rate_limits.failure_count + 1,
                last_failure_reason = excluded.last_failure_reason,
                metadata_json = excluded.metadata_json,
                updated_at = datetime('now')
            """,
            (
                provider_key,
                backoff_until.isoformat(timespec="seconds"),
                reason,
                json.dumps({"likely_throttled": _looks_throttled(reason), "recorded_at": current.isoformat(timespec="seconds")}, ensure_ascii=False, sort_keys=True),
            ),
        )
    return {"provider_key": provider_key, "backoff_until": backoff_until.isoformat(timespec="seconds"), "likely_throttled": _looks_throttled(reason)}


def _looks_throttled(reason: str) -> bool:
    lowered = str(reason or "").lower()
    return any(marker in lowered for marker in THROTTLE_MARKERS)


def _insert_scheduler_run(conn: Any, *, job_key: str, scheduled_at: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO scheduler_runs(job_key, scheduled_at, status)
        VALUES (?, ?, 'running')
        RETURNING id
        """,
        (job_key, scheduled_at),
    )
    return int(cursor.fetchone()["id"])


def _upsert_watermark(
    conn: Any,
    *,
    job_key: str,
    provider_key: str | None,
    source_key: str,
    scope_key: str,
    success_cursor: str | None,
    attempted_cursor: str | None,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO scheduler_watermarks(
            job_key, provider_key, source_key, scope_key,
            last_success_cursor, last_attempted_cursor, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_key, provider_key, source_key, scope_key) DO UPDATE SET
            last_success_cursor = excluded.last_success_cursor,
            last_attempted_cursor = excluded.last_attempted_cursor,
            metadata_json = excluded.metadata_json,
            updated_at = datetime('now')
        """,
        (job_key, provider_key, source_key, scope_key, success_cursor, attempted_cursor, json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
    )


def _get_watermark(conn: Any, job_key: str, provider_key: str | None, source_key: str, scope_key: str) -> Any | None:
    return conn.execute(
        """
        SELECT *
        FROM scheduler_watermarks
        WHERE job_key = ?
          AND provider_key IS ?
          AND source_key = ?
          AND scope_key = ?
        """,
        (job_key, provider_key, source_key, scope_key),
    ).fetchone()


def _parse_cursor(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _target_market_date(now: datetime) -> date:
    target = now.date()
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target


def _policy_summary(policy: dict[str, Any]) -> dict[str, Any]:
    keys = ("request_cap", "hourly_request_budget", "daily_request_budget", "min_delay_seconds", "jitter_seconds", "backoff_minutes")
    return {key: policy[key] for key in keys if key in policy}


def _asset_plan(row: Any, target_date: str) -> dict[str, Any]:
    return {
        "asset_id": int(row["id"]),
        "code": row["code"],
        "asset_type": row["asset_type"],
        "latest_trade_date": row["latest_trade_date"],
        "target_date": target_date,
    }


def _feature_plan(row: Any) -> dict[str, Any]:
    return {
        "asset_id": int(row["id"]),
        "code": row["code"],
        "asset_type": row["asset_type"],
        "from_feature_date": row["latest_feature_date"],
        "to_price_date": row["latest_price_date"],
    }


def _get_scheduler_run(db_path: str | Path, run_id: int) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM scheduler_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise ValueError(f"scheduler run not found: {run_id}")
    return _run_row_to_dict(row)


def _definition_from_job(job: dict[str, Any]) -> SchedulerJobDefinition:
    return SchedulerJobDefinition(
        job_key=job["job_key"],
        job_type=job["job_type"],
        cadence=job["cadence"],
        enabled=bool(job["enabled"]),
        provider_key=job.get("provider_key"),
        time_window=job["time_window"],
        policy=job["policy"],
        description=job["description"],
    )


def _job_row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    data["time_window"] = json.loads(data.pop("time_window_json") or "{}")
    data["policy"] = json.loads(data.pop("policy_json") or "{}")
    return data


def _run_row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["updated_counts"] = json.loads(data.pop("updated_counts_json") or "{}")
    data["provider_request_counts"] = json.loads(data.pop("provider_request_counts_json") or "{}")
    data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    data["execution_mode"] = _execution_mode(data["metadata"])
    return data


def _execution_mode(metadata: dict[str, Any]) -> str:
    if metadata.get("agent_runtime"):
        return "agent_runtime"
    if metadata.get("real_model_run"):
        return "real_model_run"
    if metadata.get("real_provider_calls"):
        return "real_provider"
    if metadata.get("real_calculation"):
        return "real_calculation"
    if metadata.get("readiness_gate"):
        return "readiness_only"
    return "planned_or_skipped"


def _watermark_row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    return data


def _rate_limit_row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    return data
