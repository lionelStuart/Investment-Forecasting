from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from investment_forecasting.db import complete_task_log, connect, init_db, start_task_log
from investment_forecasting.scheduler.registry import DEFAULT_JOB_DEFINITIONS, SchedulerJobDefinition, next_run_after


TERMINAL_STATUSES = {"success", "skipped", "deferred", "failed"}
THROTTLE_MARKERS = ("429", "403", "too many", "rate limit", "captcha", "anti", "访问过于频繁", "限流", "验证码", "proxy", "dns")


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
            result = _run_deterministic_job(conn, job, current)
            status = result["status"]
            next_run = next_run_after(_definition_from_job(job), current).isoformat(timespec="seconds")
            conn.execute(
                """
                UPDATE scheduler_runs
                SET status = ?,
                    finished_at = datetime('now'),
                    updated_counts_json = ?,
                    skipped_reason = ?,
                    deferred_reason = ?,
                    provider_request_counts_json = ?,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result.get("updated_counts", {}), ensure_ascii=False, sort_keys=True),
                    result.get("skipped_reason"),
                    result.get("deferred_reason"),
                    json.dumps(result.get("provider_request_counts", {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(result.get("metadata", {}), ensure_ascii=False, sort_keys=True),
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
            conn.execute(
                "UPDATE scheduler_runs SET status = 'failed', finished_at = datetime('now'), error = ? WHERE id = ?",
                (str(exc), run_id),
            )
            complete_task_log(conn, task_log_id, "failed", error=str(exc))
            raise
    return _get_scheduler_run(db_path, run_id)


def _run_deterministic_job(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
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

    result = _run_incremental_job(conn, job, now)
    request_count = sum(int(value) for value in result.get("provider_request_counts", {}).values())
    if provider_key and request_count:
        _record_provider_success(conn, provider_key, request_count, policy, now)
    return result


def _run_incremental_job(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    job_type = job["job_type"]
    if job_type == "news_incremental":
        return _run_news_incremental(conn, job, now)
    if job_type == "market_context_incremental":
        return _run_market_context_incremental(conn, job, now)
    if job_type == "price_nav_incremental":
        return _run_price_nav_incremental(conn, job, now)
    if job_type == "features_incremental":
        return _run_features_incremental(conn, job, now)
    if job_type == "model_post_close":
        return _run_readiness_gate_job(conn, job, now, required_watermarks=("price_nav_post_close", "features_post_close"))
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


def _run_news_incremental(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
    provider_key = job.get("provider_key")
    policy = job.get("policy", {})
    window_minutes = int(policy.get("window_minutes") or 65)
    sources = [str(source) for source in policy.get("sources", ["sina"])]
    planned = []
    request_count = 0
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
        request_count += 1
        planned.append({"source": source, "start": start.isoformat(timespec="seconds"), "end": now.isoformat(timespec="seconds"), "max_items": int(policy.get("request_cap") or 200)})
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=provider_key,
            source_key=source,
            scope_key="news",
            success_cursor=now.isoformat(timespec="seconds"),
            attempted_cursor=now.isoformat(timespec="seconds"),
            metadata={"incremental": True, "bounded_window": True, "real_provider_calls": False, "window_minutes": window_minutes},
        )
    return {
        "status": "success" if request_count else "skipped",
        "skipped_reason": None if request_count else "news watermarks already current",
        "updated_counts": {"news_windows": request_count, "sources": len(sources)},
        "provider_request_counts": {provider_key: request_count} if provider_key else {},
        "metadata": {"real_provider_calls": False, "incremental": True, "bounded_window": True, "planned_windows": planned, "policy": _policy_summary(policy)},
    }


def _run_market_context_incremental(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
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
    for item in planned:
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=provider_key,
            source_key=str(item["subject"]),
            scope_key=f"capital_flow:{item['scope']}",
            success_cursor=now.date().isoformat(),
            attempted_cursor=now.date().isoformat(),
            metadata={"incremental": True, "real_provider_calls": False, "source": "capital_flow_observations"},
        )
    return {
        "status": "success" if planned else "skipped",
        "skipped_reason": None if planned else "no tracked market context subjects",
        "updated_counts": {"capital_flow_subjects": len(planned), "skipped_by_cap": max(0, len(subjects) - len(planned))},
        "provider_request_counts": {provider_key: len(planned)} if provider_key else {},
        "metadata": {"real_provider_calls": False, "incremental": True, "planned_subjects": planned, "policy": _policy_summary(policy)},
    }


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
    for row in rows:
        source_key = f"{row['asset_type']}:{row['code']}"
        latest = row["latest_trade_date"] or ""
        attempted = target_date if row in planned else latest
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=provider_key,
            source_key=source_key,
            scope_key="price_daily",
            success_cursor=latest,
            attempted_cursor=attempted,
            metadata={
                "incremental": True,
                "real_provider_calls": False,
                "target_date": target_date,
                "already_current": row not in planned,
            },
        )
    return {
        "status": "success" if planned else "skipped",
        "skipped_reason": None if planned else f"all tracked assets are current for {target_date}",
        "updated_counts": {"stale_assets": len(stale), "planned_assets": len(planned), "current_assets": len(rows) - len(stale), "skipped_by_cap": max(0, len(stale) - len(planned))},
        "provider_request_counts": {provider_key: len(planned)} if provider_key else {},
        "metadata": {"real_provider_calls": False, "incremental": True, "target_date": target_date, "planned_assets": [_asset_plan(row, target_date) for row in planned], "policy": _policy_summary(policy)},
    }


def _run_features_incremental(conn: Any, job: dict[str, Any], now: datetime) -> dict[str, Any]:
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
    for row in rows:
        latest_feature = row["latest_feature_date"] or ""
        latest_price = row["latest_price_date"] or ""
        _upsert_watermark(
            conn,
            job_key=job["job_key"],
            provider_key=job.get("provider_key"),
            source_key=f"{row['asset_type']}:{row['code']}",
            scope_key="features_daily",
            success_cursor=latest_feature,
            attempted_cursor=latest_price or target_date,
            metadata={"incremental": True, "real_provider_calls": False, "affected": row in affected},
        )
    return {
        "status": "success" if affected else "skipped",
        "skipped_reason": None if affected else "features already cover latest stored prices",
        "updated_counts": {"affected_assets": len(affected), "current_assets": len(rows) - len(affected)},
        "provider_request_counts": {job.get("provider_key"): 0} if job.get("provider_key") else {},
        "metadata": {"real_provider_calls": False, "incremental": True, "target_date": target_date, "affected_ranges": [_feature_plan(row) for row in affected]},
    }


def _run_readiness_gate_job(conn: Any, job: dict[str, Any], now: datetime, *, required_watermarks: tuple[str, ...]) -> dict[str, Any]:
    missing = []
    for required in required_watermarks:
        row = conn.execute(
            "SELECT MAX(last_success_cursor) AS cursor FROM scheduler_watermarks WHERE job_key = ?",
            (required,),
        ).fetchone()
        if not row or not row["cursor"]:
            missing.append(required)
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


def _provider_defer_reason(conn: Any, provider_key: str | None, policy: dict[str, Any], now: datetime) -> str | None:
    if not provider_key:
        return None
    rate_limit = conn.execute("SELECT * FROM provider_rate_limits WHERE provider_key = ?", (provider_key,)).fetchone()
    now_text = now.isoformat(timespec="seconds")
    if rate_limit and rate_limit["backoff_until"] and rate_limit["backoff_until"] > now_text:
        return f"provider backoff active until {rate_limit['backoff_until']}"
    hourly_budget = int(policy.get("hourly_request_budget") or policy.get("request_cap") or 0)
    daily_budget = int(policy.get("daily_request_budget") or max(hourly_budget, 0))
    if rate_limit and hourly_budget and int(rate_limit["hourly_count"] or 0) >= hourly_budget:
        return f"provider hourly budget exhausted for {provider_key}"
    if rate_limit and daily_budget and int(rate_limit["daily_count"] or 0) >= daily_budget:
        return f"provider daily budget exhausted for {provider_key}"
    return None


def _record_provider_success(conn: Any, provider_key: str, request_count: int, policy: dict[str, Any], now: datetime) -> None:
    metadata = {
        "last_policy": _policy_summary(policy),
        "last_success_at": now.isoformat(timespec="seconds"),
    }
    conn.execute(
        """
        INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, failure_count, metadata_json)
        VALUES (?, ?, ?, 0, ?)
        ON CONFLICT(provider_key) DO UPDATE SET
            hourly_count = provider_rate_limits.hourly_count + excluded.hourly_count,
            daily_count = provider_rate_limits.daily_count + excluded.daily_count,
            metadata_json = excluded.metadata_json,
            updated_at = datetime('now')
        """,
        (provider_key, request_count, request_count, json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
    )


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
    return data


def _watermark_row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    return data


def _rate_limit_row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    return data
