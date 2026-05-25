from __future__ import annotations

import sqlite3
import json
from importlib import resources
from pathlib import Path
from typing import Any


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    schema = resources.files("investment_forecasting").joinpath("migrations/001_init.sql").read_text()
    with connect(path) as conn:
        conn.executescript(schema)
        _ensure_legacy_columns(conn)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
            "VALUES (?, datetime('now'))",
            ("001_init",),
        )
    return path


def _ensure_legacy_columns(conn: sqlite3.Connection) -> None:
    fund_info_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(fund_info)").fetchall()
    }
    expected_fund_info_columns = {
        "fund_company": "TEXT",
        "custodian": "TEXT",
        "purchase_fee": "REAL",
        "benchmark": "TEXT",
        "strategy": "TEXT",
        "objective": "TEXT",
        "stage_returns_json": "TEXT",
    }
    for column, column_type in expected_fund_info_columns.items():
        if column not in fund_info_columns:
            conn.execute(f"ALTER TABLE fund_info ADD COLUMN {column} {column_type}")

    advice_score_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(advice_outcome_scores)").fetchall()
    }
    expected_advice_score_columns = {
        "benchmark_identity": "TEXT",
        "benchmark_source": "TEXT",
    }
    for column, column_type in expected_advice_score_columns.items():
        if advice_score_columns and column not in advice_score_columns:
            conn.execute(f"ALTER TABLE advice_outcome_scores ADD COLUMN {column} {column_type}")

    expert_plan_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(expert_plans)").fetchall()
    }
    if expert_plan_columns and "ai_analysis_id" not in expert_plan_columns:
        conn.execute("ALTER TABLE expert_plans ADD COLUMN ai_analysis_id INTEGER REFERENCES ai_analysis_records(id) ON DELETE SET NULL")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_prediction_reliability (
          id INTEGER PRIMARY KEY,
          prediction_id INTEGER NOT NULL REFERENCES model_predictions(id) ON DELETE CASCADE,
          rank_score REAL,
          rank_position INTEGER,
          rank_count INTEGER,
          same_category_key TEXT,
          same_category_rank INTEGER,
          same_category_count INTEGER,
          risk_adjusted_score REAL,
          validation_status TEXT NOT NULL DEFAULT 'unvalidated',
          recent_rank_ic REAL,
          bucket_spread REAL,
          degraded_reason TEXT,
          evidence_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE (prediction_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_model_prediction_reliability_prediction "
        "ON model_prediction_reliability(prediction_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_replay_runs (
          id INTEGER PRIMARY KEY,
          run_key TEXT NOT NULL UNIQUE,
          year INTEGER NOT NULL,
          start_date TEXT NOT NULL,
          end_date TEXT NOT NULL,
          horizons_json TEXT NOT NULL,
          model_versions_json TEXT NOT NULL,
          lookback_days INTEGER NOT NULL,
          asset_scope TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
          metrics_json TEXT,
          tuning_recommendations_json TEXT,
          error TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_replay_predictions (
          id INTEGER PRIMARY KEY,
          replay_run_id INTEGER NOT NULL REFERENCES model_replay_runs(id) ON DELETE CASCADE,
          asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
          prediction_date TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          model_version TEXT NOT NULL,
          target TEXT NOT NULL DEFAULT 'return',
          up_probability REAL,
          expected_return REAL,
          expected_return_low REAL,
          expected_return_high REAL,
          downside_risk REAL,
          confidence REAL,
          input_window_start TEXT,
          input_window_end TEXT,
          outcome_date TEXT,
          actual_return REAL,
          benchmark_return REAL,
          benchmark_identity TEXT,
          benchmark_source TEXT,
          prediction_score REAL,
          risk_score REAL,
          advice_score REAL,
          overall_score REAL,
          score_status TEXT NOT NULL CHECK (score_status IN ('matured', 'pending', 'skipped')),
          skip_reason TEXT,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE (replay_run_id, asset_id, prediction_date, horizon_days, model_version, target)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_model_replay_predictions_run "
        "ON model_replay_predictions(replay_run_id, model_version, horizon_days, score_status)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
          id INTEGER PRIMARY KEY,
          role_type TEXT NOT NULL CHECK (role_type IN ('expert', 'jarvis')),
          role_key TEXT NOT NULL,
          run_date TEXT NOT NULL,
          target_evidence_date TEXT NOT NULL,
          version TEXT NOT NULL DEFAULT 'codex_agent_runtime_v1',
          trigger_reason TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN (
            'pending',
            'running',
            'completed',
            'failed',
            'submitted',
            'completed_via_artifact',
            'skipped',
            'validation_failed',
            'cancelled',
            'timed_out'
          )),
          overview_skill TEXT NOT NULL,
          skill_bundle_json TEXT NOT NULL DEFAULT '[]',
          prompt_ref_json TEXT NOT NULL DEFAULT '{}',
          tool_manifest_ref_json TEXT NOT NULL DEFAULT '{}',
          output_contract_json TEXT NOT NULL DEFAULT '{}',
          runtime_policy_json TEXT NOT NULL DEFAULT '{}',
          launch_request_json TEXT NOT NULL DEFAULT '{}',
          runtime_metadata_json TEXT NOT NULL DEFAULT '{}',
          submission_result_json TEXT NOT NULL DEFAULT '{}',
          failure_reason TEXT,
          fallback_reason TEXT,
          idempotency_key TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          started_at TEXT,
          finished_at TEXT,
          UNIQUE (role_type, role_key, run_date, target_evidence_date, version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tool_calls (
          id INTEGER PRIMARY KEY,
          agent_run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
          tool_name TEXT NOT NULL,
          role_type TEXT NOT NULL,
          role_key TEXT NOT NULL,
          arguments_json TEXT NOT NULL DEFAULT '{}',
          idempotency_key TEXT,
          status TEXT NOT NULL CHECK (status IN ('allowed', 'rejected', 'submitted', 'failed')),
          result_summary_json TEXT NOT NULL DEFAULT '{}',
          error TEXT,
          called_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_role_date ON agent_runs(role_type, role_key, run_date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_status_date ON agent_runs(status, run_date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run ON agent_tool_calls(agent_run_id, called_at DESC)")
    _ensure_scheduler_tables(conn)


def _ensure_scheduler_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_jobs (
          id INTEGER PRIMARY KEY,
          job_key TEXT NOT NULL UNIQUE,
          job_type TEXT NOT NULL,
          enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)) DEFAULT 1,
          cadence TEXT NOT NULL,
          time_window_json TEXT NOT NULL DEFAULT '{}',
          provider_key TEXT,
          policy_json TEXT NOT NULL DEFAULT '{}',
          next_run_at TEXT,
          description TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_runs (
          id INTEGER PRIMARY KEY,
          job_key TEXT NOT NULL,
          scheduled_at TEXT NOT NULL,
          started_at TEXT NOT NULL DEFAULT (datetime('now')),
          finished_at TEXT,
          status TEXT NOT NULL CHECK (status IN ('running', 'success', 'skipped', 'deferred', 'failed')),
          updated_counts_json TEXT NOT NULL DEFAULT '{}',
          skipped_reason TEXT,
          deferred_reason TEXT,
          provider_request_counts_json TEXT NOT NULL DEFAULT '{}',
          error TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_watermarks (
          id INTEGER PRIMARY KEY,
          job_key TEXT NOT NULL,
          provider_key TEXT,
          source_key TEXT NOT NULL DEFAULT '',
          scope_key TEXT NOT NULL DEFAULT '',
          last_success_cursor TEXT,
          last_attempted_cursor TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE (job_key, provider_key, source_key, scope_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_rate_limits (
          id INTEGER PRIMARY KEY,
          provider_key TEXT NOT NULL UNIQUE,
          backoff_until TEXT,
          hourly_count INTEGER NOT NULL DEFAULT 0,
          daily_count INTEGER NOT NULL DEFAULT 0,
          failure_count INTEGER NOT NULL DEFAULT 0,
          last_failure_reason TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_next_run ON scheduler_jobs(enabled, next_run_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job_started ON scheduler_runs(job_key, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_watermarks_job ON scheduler_watermarks(job_key, provider_key, source_key, scope_key)")


def upsert_agent_run(conn: sqlite3.Connection, run: dict[str, Any]) -> int:
    payload = _agent_run_payload(run)
    cursor = conn.execute(
        """
        INSERT INTO agent_runs(
            role_type, role_key, run_date, target_evidence_date, version,
            trigger_reason, status, overview_skill, skill_bundle_json,
            prompt_ref_json, tool_manifest_ref_json, output_contract_json,
            runtime_policy_json, launch_request_json, runtime_metadata_json,
            submission_result_json, failure_reason, fallback_reason,
            idempotency_key
        )
        VALUES (
            :role_type, :role_key, :run_date, :target_evidence_date, :version,
            :trigger_reason, :status, :overview_skill, :skill_bundle_json,
            :prompt_ref_json, :tool_manifest_ref_json, :output_contract_json,
            :runtime_policy_json, :launch_request_json, :runtime_metadata_json,
            :submission_result_json, :failure_reason, :fallback_reason,
            :idempotency_key
        )
        ON CONFLICT(role_type, role_key, run_date, target_evidence_date, version) DO UPDATE SET
            trigger_reason = excluded.trigger_reason,
            overview_skill = excluded.overview_skill,
            skill_bundle_json = excluded.skill_bundle_json,
            prompt_ref_json = excluded.prompt_ref_json,
            tool_manifest_ref_json = excluded.tool_manifest_ref_json,
            output_contract_json = excluded.output_contract_json,
            runtime_policy_json = excluded.runtime_policy_json,
            launch_request_json = excluded.launch_request_json,
            runtime_metadata_json = excluded.runtime_metadata_json,
            fallback_reason = excluded.fallback_reason,
            updated_at = datetime('now')
        RETURNING id
        """,
        payload,
    )
    return int(cursor.fetchone()["id"])


def update_agent_run(
    conn: sqlite3.Connection,
    agent_run_id: int,
    *,
    status: str | None = None,
    launch_request: dict[str, Any] | None = None,
    runtime_metadata: dict[str, Any] | None = None,
    submission_result: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    fallback_reason: str | None = None,
) -> None:
    row = get_agent_run(conn, agent_run_id)
    if row is None:
        raise ValueError(f"agent run not found: {agent_run_id}")
    next_status = status or str(row["status"])
    conn.execute(
        """
        UPDATE agent_runs
        SET status = ?,
            launch_request_json = COALESCE(?, launch_request_json),
            runtime_metadata_json = COALESCE(?, runtime_metadata_json),
            submission_result_json = COALESCE(?, submission_result_json),
            failure_reason = COALESCE(?, failure_reason),
            fallback_reason = COALESCE(?, fallback_reason),
            started_at = CASE WHEN ? = 'running' AND started_at IS NULL THEN datetime('now') ELSE started_at END,
            finished_at = CASE
                WHEN ? IN ('completed', 'failed', 'submitted', 'completed_via_artifact', 'skipped', 'validation_failed', 'cancelled', 'timed_out')
                THEN datetime('now')
                ELSE finished_at
            END,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            next_status,
            _json_or_none(launch_request),
            _json_or_none(runtime_metadata),
            _json_or_none(submission_result),
            failure_reason,
            fallback_reason,
            next_status,
            next_status,
            agent_run_id,
        ),
    )


def get_agent_run(conn: sqlite3.Connection, agent_run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agent_runs WHERE id = ?", (agent_run_id,)).fetchone()


def list_agent_runs(
    conn: sqlite3.Connection,
    *,
    role_type: str | None = None,
    role_key: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[sqlite3.Row]:
    where = ["1 = 1"]
    params: list[Any] = []
    if role_type:
        where.append("role_type = ?")
        params.append(role_type)
    if role_key:
        where.append("role_key = ?")
        params.append(role_key)
    if status:
        where.append("status = ?")
        params.append(status)
    params.append(max(1, int(limit)))
    return conn.execute(
        f"""
        SELECT *
        FROM agent_runs
        WHERE {' AND '.join(where)}
        ORDER BY run_date DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def insert_agent_tool_call(conn: sqlite3.Connection, call: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO agent_tool_calls(
            agent_run_id, tool_name, role_type, role_key, arguments_json,
            idempotency_key, status, result_summary_json, error
        )
        VALUES (
            :agent_run_id, :tool_name, :role_type, :role_key, :arguments_json,
            :idempotency_key, :status, :result_summary_json, :error
        )
        RETURNING id
        """,
        {
            "arguments_json": "{}",
            "idempotency_key": None,
            "status": "allowed",
            "result_summary_json": "{}",
            "error": None,
            **call,
        },
    )
    return int(cursor.fetchone()["id"])


def _agent_run_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "codex_agent_runtime_v1",
        "status": "pending",
        "skill_bundle_json": "[]",
        "prompt_ref_json": "{}",
        "tool_manifest_ref_json": "{}",
        "output_contract_json": "{}",
        "runtime_policy_json": "{}",
        "launch_request_json": "{}",
        "runtime_metadata_json": "{}",
        "submission_result_json": "{}",
        "failure_reason": None,
        "fallback_reason": None,
        **run,
    }


def _json_or_none(value: dict[str, Any] | list[Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def upsert_communication_recipient(conn: sqlite3.Connection, recipient: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO communication_recipients(
            recipient_key, display_name, channel, address, allowlisted, enabled,
            min_severity, quiet_hours_start, quiet_hours_end, rate_limit_per_hour,
            retry_limit, notes
        )
        VALUES (
            :recipient_key, :display_name, :channel, :address, :allowlisted, :enabled,
            :min_severity, :quiet_hours_start, :quiet_hours_end, :rate_limit_per_hour,
            :retry_limit, :notes
        )
        ON CONFLICT(recipient_key) DO UPDATE SET
            display_name = excluded.display_name,
            channel = excluded.channel,
            address = excluded.address,
            allowlisted = excluded.allowlisted,
            enabled = excluded.enabled,
            min_severity = excluded.min_severity,
            quiet_hours_start = excluded.quiet_hours_start,
            quiet_hours_end = excluded.quiet_hours_end,
            rate_limit_per_hour = excluded.rate_limit_per_hour,
            retry_limit = excluded.retry_limit,
            notes = excluded.notes,
            updated_at = datetime('now')
        RETURNING id
        """,
        {
            "allowlisted": 0,
            "enabled": 1,
            "min_severity": "info",
            "quiet_hours_start": None,
            "quiet_hours_end": None,
            "rate_limit_per_hour": 6,
            "retry_limit": 2,
            "notes": None,
            **recipient,
        },
    )
    return int(cursor.fetchone()["id"])


def upsert_communication_adapter_config(conn: sqlite3.Connection, config: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO communication_adapter_configs(
            channel, enabled, dry_run_default, config_json, setup_status,
            last_verified_at, last_error
        )
        VALUES (
            :channel, :enabled, :dry_run_default, :config_json, :setup_status,
            :last_verified_at, :last_error
        )
        ON CONFLICT(channel) DO UPDATE SET
            enabled = excluded.enabled,
            dry_run_default = excluded.dry_run_default,
            config_json = excluded.config_json,
            setup_status = excluded.setup_status,
            last_verified_at = excluded.last_verified_at,
            last_error = excluded.last_error,
            updated_at = datetime('now')
        RETURNING id
        """,
        {
            "enabled": 0,
            "dry_run_default": 1,
            "config_json": "{}",
            "setup_status": "unverified",
            "last_verified_at": None,
            "last_error": None,
            **config,
        },
    )
    return int(cursor.fetchone()["id"])


def list_communication_recipients(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM communication_recipients ORDER BY channel, recipient_key").fetchall()


def list_communication_adapter_configs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM communication_adapter_configs ORDER BY channel").fetchall()


def list_outbound_messages(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT om.*, cr.display_name
        FROM outbound_messages om
        LEFT JOIN communication_recipients cr ON cr.id = om.recipient_id
        ORDER BY om.requested_at DESC, om.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def upsert_asset(conn: sqlite3.Connection, asset: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO assets(code, name, asset_type, market, currency, status, source)
        VALUES (:code, :name, :asset_type, :market, :currency, :status, :source)
        ON CONFLICT(code, asset_type, market, source) DO UPDATE SET
            name = excluded.name,
            asset_type = excluded.asset_type,
            currency = excluded.currency,
            status = excluded.status,
            updated_at = datetime('now')
        RETURNING id
        """,
        asset,
    )
    return int(cursor.fetchone()["id"])


def upsert_price_daily(
    conn: sqlite3.Connection,
    asset_id: int,
    source: str,
    price: dict[str, Any],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO price_daily(
            asset_id, trade_date, open, high, low, close, volume, amount,
            pct_change, adjusted_close, nav, accumulated_nav, source, raw_payload
        )
        VALUES (
            :asset_id, :trade_date, :open, :high, :low, :close, :volume, :amount,
            :pct_change, :adjusted_close, :nav, :accumulated_nav, :source, :raw_payload
        )
        ON CONFLICT(asset_id, trade_date, source) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            amount = excluded.amount,
            pct_change = excluded.pct_change,
            adjusted_close = excluded.adjusted_close,
            nav = excluded.nav,
            accumulated_nav = excluded.accumulated_nav,
            raw_payload = excluded.raw_payload,
            updated_at = datetime('now')
        RETURNING id
        """,
        {**price, "asset_id": asset_id, "source": source},
    )
    return int(cursor.fetchone()["id"])


def upsert_fund_info(
    conn: sqlite3.Connection,
    asset_id: int,
    source: str,
    info: dict[str, Any],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO fund_info(
            asset_id, fund_type, fund_company, manager, custodian,
            management_fee, custody_fee, purchase_fee, scale, inception_date,
            benchmark, strategy, objective, stage_returns_json, source, raw_payload
        )
        VALUES (
            :asset_id, :fund_type, :fund_company, :manager, :custodian,
            :management_fee, :custody_fee, :purchase_fee, :scale, :inception_date,
            :benchmark, :strategy, :objective, :stage_returns_json, :source, :raw_payload
        )
        ON CONFLICT(asset_id, source) DO UPDATE SET
            fund_type = excluded.fund_type,
            fund_company = excluded.fund_company,
            manager = excluded.manager,
            custodian = excluded.custodian,
            management_fee = excluded.management_fee,
            custody_fee = excluded.custody_fee,
            purchase_fee = excluded.purchase_fee,
            scale = excluded.scale,
            inception_date = excluded.inception_date,
            benchmark = excluded.benchmark,
            strategy = excluded.strategy,
            objective = excluded.objective,
            stage_returns_json = excluded.stage_returns_json,
            raw_payload = excluded.raw_payload,
            updated_at = datetime('now')
        RETURNING id
        """,
        {**info, "asset_id": asset_id, "source": source},
    )
    return int(cursor.fetchone()["id"])


def upsert_fund_holding(conn: sqlite3.Connection, holding: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO fund_holdings(
            fund_asset_id, report_period, holding_type, holding_code,
            holding_name, holding_asset_id, weight_pct, shares, market_value,
            rank, source, raw_payload
        )
        VALUES (
            :fund_asset_id, :report_period, :holding_type, :holding_code,
            :holding_name, :holding_asset_id, :weight_pct, :shares, :market_value,
            :rank, :source, :raw_payload
        )
        ON CONFLICT(fund_asset_id, report_period, holding_type, holding_code, source) DO UPDATE SET
            holding_name = excluded.holding_name,
            holding_asset_id = excluded.holding_asset_id,
            weight_pct = excluded.weight_pct,
            shares = excluded.shares,
            market_value = excluded.market_value,
            rank = excluded.rank,
            raw_payload = excluded.raw_payload,
            updated_at = datetime('now')
        RETURNING id
        """,
        holding,
    )
    return int(cursor.fetchone()["id"])


def latest_fund_holdings(conn: sqlite3.Connection, limit: int = 80) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            fh.*,
            f.code AS fund_code,
            f.name AS fund_name,
            h.code AS linked_holding_code,
            h.name AS linked_holding_name,
            h.asset_type AS linked_holding_asset_type
        FROM fund_holdings fh
        JOIN assets f ON f.id = fh.fund_asset_id
        LEFT JOIN assets h ON h.id = fh.holding_asset_id
        WHERE fh.report_period = (
            SELECT MAX(report_period)
            FROM fund_holdings
            WHERE fund_asset_id = fh.fund_asset_id
              AND source = fh.source
        )
        ORDER BY fh.report_period DESC, fh.fund_asset_id, fh.rank, fh.weight_pct DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def get_asset(
    conn: sqlite3.Connection,
    code: str,
    market: str,
    source: str = "manual",
    asset_type: str | None = None,
) -> sqlite3.Row | None:
    if asset_type:
        return conn.execute(
            """
            SELECT *
            FROM assets
            WHERE code = ? AND market = ? AND source = ? AND asset_type = ?
            """,
            (code, market, source, asset_type),
        ).fetchone()
    return conn.execute(
        """
        SELECT *
        FROM assets
        WHERE code = ? AND market = ? AND source = ?
        ORDER BY id
        """,
        (code, market, source),
    ).fetchone()


def list_assets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM assets ORDER BY id").fetchall()


def list_price_history(conn: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            asset_id,
            trade_date,
            COALESCE(adjusted_close, close, nav) AS price_value
        FROM price_daily
        WHERE asset_id = ?
          AND COALESCE(adjusted_close, close, nav) IS NOT NULL
        ORDER BY trade_date
        """,
        (asset_id,),
    ).fetchall()


def upsert_feature_daily(conn: sqlite3.Connection, feature: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO features_daily(
            asset_id, feature_date, return_1d, return_5d, return_20d, return_60d,
            volatility_20d, max_drawdown_60d, sharpe_60d, calmar_60d,
            win_rate_60d, momentum_20d, market_state, source
        )
        VALUES (
            :asset_id, :feature_date, :return_1d, :return_5d, :return_20d, :return_60d,
            :volatility_20d, :max_drawdown_60d, :sharpe_60d, :calmar_60d,
            :win_rate_60d, :momentum_20d, :market_state, :source
        )
        ON CONFLICT(asset_id, feature_date, source) DO UPDATE SET
            return_1d = excluded.return_1d,
            return_5d = excluded.return_5d,
            return_20d = excluded.return_20d,
            return_60d = excluded.return_60d,
            volatility_20d = excluded.volatility_20d,
            max_drawdown_60d = excluded.max_drawdown_60d,
            sharpe_60d = excluded.sharpe_60d,
            calmar_60d = excluded.calmar_60d,
            win_rate_60d = excluded.win_rate_60d,
            momentum_20d = excluded.momentum_20d,
            market_state = excluded.market_state,
            updated_at = datetime('now')
        RETURNING id
        """,
        feature,
    )
    return int(cursor.fetchone()["id"])


def upsert_model_prediction(conn: sqlite3.Connection, prediction: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO model_predictions(
            asset_id, prediction_date, horizon_days, model_version, target,
            up_probability, expected_return, expected_return_low,
            expected_return_high, downside_risk, confidence, input_window_start,
            input_window_end, assumptions
        )
        VALUES (
            :asset_id, :prediction_date, :horizon_days, :model_version, :target,
            :up_probability, :expected_return, :expected_return_low,
            :expected_return_high, :downside_risk, :confidence, :input_window_start,
            :input_window_end, :assumptions
        )
        ON CONFLICT(asset_id, prediction_date, horizon_days, model_version, target) DO UPDATE SET
            up_probability = excluded.up_probability,
            expected_return = excluded.expected_return,
            expected_return_low = excluded.expected_return_low,
            expected_return_high = excluded.expected_return_high,
            downside_risk = excluded.downside_risk,
            confidence = excluded.confidence,
            input_window_start = excluded.input_window_start,
            input_window_end = excluded.input_window_end,
            assumptions = excluded.assumptions
        RETURNING id
        """,
        prediction,
    )
    return int(cursor.fetchone()["id"])


def upsert_model_prediction_reliability(conn: sqlite3.Connection, reliability: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO model_prediction_reliability(
            prediction_id, rank_score, rank_position, rank_count,
            same_category_key, same_category_rank, same_category_count,
            risk_adjusted_score, validation_status, recent_rank_ic,
            bucket_spread, degraded_reason, evidence_json
        )
        VALUES (
            :prediction_id, :rank_score, :rank_position, :rank_count,
            :same_category_key, :same_category_rank, :same_category_count,
            :risk_adjusted_score, :validation_status, :recent_rank_ic,
            :bucket_spread, :degraded_reason, :evidence_json
        )
        ON CONFLICT(prediction_id) DO UPDATE SET
            rank_score = excluded.rank_score,
            rank_position = excluded.rank_position,
            rank_count = excluded.rank_count,
            same_category_key = excluded.same_category_key,
            same_category_rank = excluded.same_category_rank,
            same_category_count = excluded.same_category_count,
            risk_adjusted_score = excluded.risk_adjusted_score,
            validation_status = excluded.validation_status,
            recent_rank_ic = excluded.recent_rank_ic,
            bucket_spread = excluded.bucket_spread,
            degraded_reason = excluded.degraded_reason,
            evidence_json = excluded.evidence_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        {
            "rank_score": None,
            "rank_position": None,
            "rank_count": None,
            "same_category_key": None,
            "same_category_rank": None,
            "same_category_count": None,
            "risk_adjusted_score": None,
            "validation_status": "unvalidated",
            "recent_rank_ic": None,
            "bucket_spread": None,
            "degraded_reason": None,
            "evidence_json": "{}",
            **reliability,
        },
    )
    return int(cursor.fetchone()["id"])


def upsert_backtest_run(conn: sqlite3.Connection, run: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs(
            model_version, asset_scope, start_date, end_date, horizon_days,
            parameters_json, metrics_json
        )
        VALUES (
            :model_version, :asset_scope, :start_date, :end_date, :horizon_days,
            :parameters_json, :metrics_json
        )
        ON CONFLICT(model_version, asset_scope, start_date, end_date, horizon_days) DO UPDATE SET
            parameters_json = excluded.parameters_json,
            metrics_json = excluded.metrics_json
        RETURNING id
        """,
        run,
    )
    return int(cursor.fetchone()["id"])


def update_backtest_metrics(conn: sqlite3.Connection, run_id: int, metrics_json: str) -> None:
    conn.execute("UPDATE backtest_runs SET metrics_json = ? WHERE id = ?", (metrics_json, run_id))


def upsert_backtest_result(conn: sqlite3.Connection, result: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_results(
            run_id, asset_id, prediction_date, horizon_days, predicted_return,
            actual_return, predicted_direction, actual_direction,
            prediction_score, risk_score, advice_score, overall_score, details_json
        )
        VALUES (
            :run_id, :asset_id, :prediction_date, :horizon_days, :predicted_return,
            :actual_return, :predicted_direction, :actual_direction,
            :prediction_score, :risk_score, :advice_score, :overall_score, :details_json
        )
        ON CONFLICT(run_id, asset_id, prediction_date, horizon_days) DO UPDATE SET
            predicted_return = excluded.predicted_return,
            actual_return = excluded.actual_return,
            predicted_direction = excluded.predicted_direction,
            actual_direction = excluded.actual_direction,
            prediction_score = excluded.prediction_score,
            risk_score = excluded.risk_score,
            advice_score = excluded.advice_score,
            overall_score = excluded.overall_score,
            details_json = excluded.details_json
        RETURNING id
        """,
        result,
    )
    return int(cursor.fetchone()["id"])


def latest_model_predictions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    latest_date = conn.execute("SELECT MAX(prediction_date) AS prediction_date FROM model_predictions").fetchone()[
        "prediction_date"
    ]
    if latest_date is None:
        return []
    return conn.execute(
        """
        SELECT p.*, a.code AS asset_code, a.name AS asset_name, a.asset_type,
               r.rank_score, r.rank_position, r.rank_count,
               r.same_category_key, r.same_category_rank, r.same_category_count,
               r.risk_adjusted_score, r.validation_status, r.recent_rank_ic,
               r.bucket_spread, r.degraded_reason, r.evidence_json AS reliability_evidence_json
        FROM model_predictions p
        LEFT JOIN assets a ON a.id = p.asset_id
        LEFT JOIN model_prediction_reliability r ON r.prediction_id = p.id
        WHERE p.prediction_date = ?
        ORDER BY p.asset_id, p.horizon_days
        """,
        (latest_date,),
    ).fetchall()


def latest_backtest_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM backtest_runs
        WHERE model_version = (
            SELECT model_version
            FROM backtest_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        )
        ORDER BY horizon_days
        """
    ).fetchall()


def upsert_daily_advice(conn: sqlite3.Connection, advice: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO daily_advice(
            advice_date, market_summary, risk_level, aggressive_advice,
            balanced_advice, conservative_advice, allocation_json, assumptions,
            risk_warnings, evidence_json, prediction_score, risk_score,
            advice_score, overall_score, model_version
        )
        VALUES (
            :advice_date, :market_summary, :risk_level, :aggressive_advice,
            :balanced_advice, :conservative_advice, :allocation_json, :assumptions,
            :risk_warnings, :evidence_json, :prediction_score, :risk_score,
            :advice_score, :overall_score, :model_version
        )
        ON CONFLICT(advice_date, model_version) DO UPDATE SET
            market_summary = excluded.market_summary,
            risk_level = excluded.risk_level,
            aggressive_advice = excluded.aggressive_advice,
            balanced_advice = excluded.balanced_advice,
            conservative_advice = excluded.conservative_advice,
            allocation_json = excluded.allocation_json,
            assumptions = excluded.assumptions,
            risk_warnings = excluded.risk_warnings,
            evidence_json = excluded.evidence_json,
            prediction_score = excluded.prediction_score,
            risk_score = excluded.risk_score,
            advice_score = excluded.advice_score,
            overall_score = excluded.overall_score,
            updated_at = datetime('now')
        RETURNING id
        """,
        advice,
    )
    return int(cursor.fetchone()["id"])


def upsert_calibration_report(conn: sqlite3.Connection, report: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO model_calibration_reports(
            report_date, candidate_versions, promoted_version, windows_json,
            metrics_json, rationale
        )
        VALUES (
            :report_date, :candidate_versions, :promoted_version, :windows_json,
            :metrics_json, :rationale
        )
        ON CONFLICT(report_date, candidate_versions) DO UPDATE SET
            promoted_version = excluded.promoted_version,
            windows_json = excluded.windows_json,
            metrics_json = excluded.metrics_json,
            rationale = excluded.rationale,
            updated_at = datetime('now')
        RETURNING id
        """,
        report,
    )
    return int(cursor.fetchone()["id"])


def upsert_model_monitoring_report(conn: sqlite3.Connection, report: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO model_monitoring_reports(
            report_date, model_version, status, latest_prediction_date,
            latest_backtest_end_date, prediction_staleness_days,
            backtest_staleness_days, mean_prediction_score, mean_risk_score,
            mean_benchmark_excess, mean_overall_score, score_drift,
            metrics_json, warnings_json
        )
        VALUES (
            :report_date, :model_version, :status, :latest_prediction_date,
            :latest_backtest_end_date, :prediction_staleness_days,
            :backtest_staleness_days, :mean_prediction_score, :mean_risk_score,
            :mean_benchmark_excess, :mean_overall_score, :score_drift,
            :metrics_json, :warnings_json
        )
        ON CONFLICT(report_date, model_version) DO UPDATE SET
            status = excluded.status,
            latest_prediction_date = excluded.latest_prediction_date,
            latest_backtest_end_date = excluded.latest_backtest_end_date,
            prediction_staleness_days = excluded.prediction_staleness_days,
            backtest_staleness_days = excluded.backtest_staleness_days,
            mean_prediction_score = excluded.mean_prediction_score,
            mean_risk_score = excluded.mean_risk_score,
            mean_benchmark_excess = excluded.mean_benchmark_excess,
            mean_overall_score = excluded.mean_overall_score,
            score_drift = excluded.score_drift,
            metrics_json = excluded.metrics_json,
            warnings_json = excluded.warnings_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        report,
    )
    return int(cursor.fetchone()["id"])


def latest_model_monitoring_reports(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    latest_date = conn.execute("SELECT MAX(report_date) AS report_date FROM model_monitoring_reports").fetchone()["report_date"]
    if latest_date is None:
        return []
    return conn.execute(
        """
        SELECT *
        FROM model_monitoring_reports
        WHERE report_date = ?
        ORDER BY CASE status WHEN 'degraded' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, model_version
        """,
        (latest_date,),
    ).fetchall()


def upsert_market_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO market_snapshots(
            snapshot_date, source, index_trend, breadth, liquidity_heat,
            stock_bond_proxy, sentiment, details_json
        )
        VALUES (
            :snapshot_date, :source, :index_trend, :breadth, :liquidity_heat,
            :stock_bond_proxy, :sentiment, :details_json
        )
        ON CONFLICT(snapshot_date, source) DO UPDATE SET
            index_trend = excluded.index_trend,
            breadth = excluded.breadth,
            liquidity_heat = excluded.liquidity_heat,
            stock_bond_proxy = excluded.stock_bond_proxy,
            sentiment = excluded.sentiment,
            details_json = excluded.details_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        snapshot,
    )
    return int(cursor.fetchone()["id"])


def upsert_macro_observation(conn: sqlite3.Connection, observation: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO macro_observations(series_id, observation_date, value, source, raw_payload)
        VALUES (:series_id, :observation_date, :value, :source, :raw_payload)
        ON CONFLICT(series_id, observation_date, source) DO UPDATE SET
            value = excluded.value,
            raw_payload = excluded.raw_payload,
            updated_at = datetime('now')
        RETURNING id
        """,
        observation,
    )
    return int(cursor.fetchone()["id"])


def upsert_capital_flow_observation(conn: sqlite3.Connection, observation: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO capital_flow_observations(
            flow_date, scope, subject_code, subject_name, asset_id, close,
            pct_change, main_net_inflow, main_net_inflow_pct,
            super_large_net_inflow, super_large_net_inflow_pct,
            large_net_inflow, large_net_inflow_pct, medium_net_inflow,
            medium_net_inflow_pct, small_net_inflow, small_net_inflow_pct,
            source, raw_payload
        )
        VALUES (
            :flow_date, :scope, :subject_code, :subject_name, :asset_id, :close,
            :pct_change, :main_net_inflow, :main_net_inflow_pct,
            :super_large_net_inflow, :super_large_net_inflow_pct,
            :large_net_inflow, :large_net_inflow_pct, :medium_net_inflow,
            :medium_net_inflow_pct, :small_net_inflow, :small_net_inflow_pct,
            :source, :raw_payload
        )
        ON CONFLICT(scope, subject_code, flow_date, source) DO UPDATE SET
            subject_name = excluded.subject_name,
            asset_id = excluded.asset_id,
            close = excluded.close,
            pct_change = excluded.pct_change,
            main_net_inflow = excluded.main_net_inflow,
            main_net_inflow_pct = excluded.main_net_inflow_pct,
            super_large_net_inflow = excluded.super_large_net_inflow,
            super_large_net_inflow_pct = excluded.super_large_net_inflow_pct,
            large_net_inflow = excluded.large_net_inflow,
            large_net_inflow_pct = excluded.large_net_inflow_pct,
            medium_net_inflow = excluded.medium_net_inflow,
            medium_net_inflow_pct = excluded.medium_net_inflow_pct,
            small_net_inflow = excluded.small_net_inflow,
            small_net_inflow_pct = excluded.small_net_inflow_pct,
            raw_payload = excluded.raw_payload,
            updated_at = datetime('now')
        RETURNING id
        """,
        observation,
    )
    return int(cursor.fetchone()["id"])


def upsert_news_item(conn: sqlite3.Connection, item: dict[str, Any]) -> tuple[int, bool]:
    if item.get("provider_news_id"):
        existing = conn.execute(
            """
            SELECT id
            FROM news_items
            WHERE provider = ? AND source = ? AND provider_news_id = ?
            """,
            (item["provider"], item["source"], item["provider_news_id"]),
        ).fetchone()
        if existing is not None:
            _update_news_item(conn, int(existing["id"]), item)
            return int(existing["id"]), False

    existing = conn.execute(
        """
        SELECT id
        FROM news_items
        WHERE source = ? AND published_at = ? AND content_hash = ?
        """,
        (item["source"], item["published_at"], item["content_hash"]),
    ).fetchone()
    if existing is not None:
        _update_news_item(conn, int(existing["id"]), item)
        return int(existing["id"]), False

    cursor = conn.execute(
        """
        INSERT INTO news_items(
            provider, source, provider_news_id, published_at, title,
            content_excerpt, content, channels_json, url, content_hash, raw_payload
        )
        VALUES (
            :provider, :source, :provider_news_id, :published_at, :title,
            :content_excerpt, :content, :channels_json, :url, :content_hash, :raw_payload
        )
        RETURNING id
        """,
        item,
    )
    return int(cursor.fetchone()["id"]), True


def _update_news_item(conn: sqlite3.Connection, item_id: int, item: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE news_items
        SET provider_news_id = COALESCE(:provider_news_id, provider_news_id),
            title = :title,
            content_excerpt = :content_excerpt,
            content = :content,
            channels_json = :channels_json,
            url = :url,
            raw_payload = :raw_payload,
            ingested_at = datetime('now'),
            updated_at = datetime('now')
        WHERE id = :id
        """,
        {**item, "id": item_id},
    )


def upsert_news_item_link(conn: sqlite3.Connection, link: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO news_item_links(
            news_item_id, link_key, asset_id, theme_key, theme_label,
            link_type, confidence, reason, source
        )
        VALUES (
            :news_item_id, :link_key, :asset_id, :theme_key, :theme_label,
            :link_type, :confidence, :reason, :source
        )
        ON CONFLICT(news_item_id, link_key, source) DO UPDATE SET
            asset_id = excluded.asset_id,
            theme_key = excluded.theme_key,
            theme_label = excluded.theme_label,
            link_type = excluded.link_type,
            confidence = excluded.confidence,
            reason = excluded.reason,
            updated_at = datetime('now')
        RETURNING id
        """,
        link,
    )
    return int(cursor.fetchone()["id"])


def upsert_news_item_tag(conn: sqlite3.Connection, tag: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO news_item_tags(
            news_item_id, tag_type, tag_value, intensity, freshness_score,
            confidence, reason, source
        )
        VALUES (
            :news_item_id, :tag_type, :tag_value, :intensity, :freshness_score,
            :confidence, :reason, :source
        )
        ON CONFLICT(news_item_id, tag_type, tag_value, source) DO UPDATE SET
            intensity = excluded.intensity,
            freshness_score = excluded.freshness_score,
            confidence = excluded.confidence,
            reason = excluded.reason,
            updated_at = datetime('now')
        RETURNING id
        """,
        tag,
    )
    return int(cursor.fetchone()["id"])


def upsert_news_feature_daily(conn: sqlite3.Connection, feature: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO news_feature_daily(
            feature_date, scope_type, scope_key, window_start, window_end,
            news_count, source_count, positive_count, negative_count,
            neutral_count, risk_event_count, policy_count,
            freshness_weighted_sentiment, evidence_ids_json, source
        )
        VALUES (
            :feature_date, :scope_type, :scope_key, :window_start, :window_end,
            :news_count, :source_count, :positive_count, :negative_count,
            :neutral_count, :risk_event_count, :policy_count,
            :freshness_weighted_sentiment, :evidence_ids_json, :source
        )
        ON CONFLICT(feature_date, scope_type, scope_key, window_start, window_end, source) DO UPDATE SET
            news_count = excluded.news_count,
            source_count = excluded.source_count,
            positive_count = excluded.positive_count,
            negative_count = excluded.negative_count,
            neutral_count = excluded.neutral_count,
            risk_event_count = excluded.risk_event_count,
            policy_count = excluded.policy_count,
            freshness_weighted_sentiment = excluded.freshness_weighted_sentiment,
            evidence_ids_json = excluded.evidence_ids_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        feature,
    )
    return int(cursor.fetchone()["id"])


def latest_capital_flow_observations(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT cf.*, a.code AS asset_code, a.name AS asset_name, a.asset_type
        FROM capital_flow_observations cf
        LEFT JOIN assets a ON a.id = cf.asset_id
        WHERE cf.flow_date = (
            SELECT MAX(flow_date)
            FROM capital_flow_observations
            WHERE scope = cf.scope
              AND subject_code = cf.subject_code
              AND source = cf.source
        )
        ORDER BY cf.flow_date DESC, ABS(COALESCE(cf.main_net_inflow, 0)) DESC, cf.subject_code
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def upsert_data_quality_report(conn: sqlite3.Connection, report: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO data_quality_reports(report_date, scope, status, warnings_json, metadata_json)
        VALUES (:report_date, :scope, :status, :warnings_json, :metadata_json)
        ON CONFLICT(report_date, scope) DO UPDATE SET
            status = excluded.status,
            warnings_json = excluded.warnings_json,
            metadata_json = excluded.metadata_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        report,
    )
    return int(cursor.fetchone()["id"])


def upsert_user_preference(conn: sqlite3.Connection, preference: dict[str, Any]) -> int:
    if int(preference.get("is_active", 0)):
        conn.execute("UPDATE user_preferences SET is_active = 0, updated_at = datetime('now') WHERE is_active = 1")
    cursor = conn.execute(
        """
        INSERT INTO user_preferences(
            profile_name, risk_profile, investment_horizon_days,
            max_equity_pct, min_cash_pct, notes, is_active
        )
        VALUES (
            :profile_name, :risk_profile, :investment_horizon_days,
            :max_equity_pct, :min_cash_pct, :notes, :is_active
        )
        ON CONFLICT(profile_name) DO UPDATE SET
            risk_profile = excluded.risk_profile,
            investment_horizon_days = excluded.investment_horizon_days,
            max_equity_pct = excluded.max_equity_pct,
            min_cash_pct = excluded.min_cash_pct,
            notes = excluded.notes,
            is_active = excluded.is_active,
            updated_at = datetime('now')
        RETURNING id
        """,
        preference,
    )
    return int(cursor.fetchone()["id"])


def active_user_preference(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM user_preferences
        WHERE is_active = 1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()


def list_user_preferences(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM user_preferences
        ORDER BY is_active DESC, updated_at DESC, id DESC
        """
    ).fetchall()


def upsert_jarvis_daily_brief(conn: sqlite3.Connection, brief: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO jarvis_daily_briefs(
            brief_date, version, focus_directions_json, one_line_stance,
            model_summary_json, expert_summary_json, combined_recommendation,
            risk_warnings, evidence_json, missing_evidence_json,
            stale_evidence_json, source
        )
        VALUES (
            :brief_date, :version, :focus_directions_json, :one_line_stance,
            :model_summary_json, :expert_summary_json, :combined_recommendation,
            :risk_warnings, :evidence_json, :missing_evidence_json,
            :stale_evidence_json, :source
        )
        ON CONFLICT(brief_date, version) DO UPDATE SET
            focus_directions_json = excluded.focus_directions_json,
            one_line_stance = excluded.one_line_stance,
            model_summary_json = excluded.model_summary_json,
            expert_summary_json = excluded.expert_summary_json,
            combined_recommendation = excluded.combined_recommendation,
            risk_warnings = excluded.risk_warnings,
            evidence_json = excluded.evidence_json,
            missing_evidence_json = excluded.missing_evidence_json,
            stale_evidence_json = excluded.stale_evidence_json,
            source = excluded.source,
            updated_at = datetime('now')
        RETURNING id
        """,
        brief,
    )
    return int(cursor.fetchone()["id"])


def upsert_ai_analysis_record(conn: sqlite3.Connection, analysis: dict[str, Any]) -> int:
    payload = {
        **analysis,
        "version": analysis.get("version", "ai_analysis_v1"),
        "status": analysis.get("status", "valid"),
        "source": analysis.get("source", "deterministic_ai_analysis_v1"),
        "expert_id": analysis.get("expert_id"),
        "jarvis_brief_id": analysis.get("jarvis_brief_id"),
        "evidence_packet_json": _json_text(analysis["evidence_packet"]),
        "output_json": _json_text(analysis["output"]),
        "validation_json": _json_text(analysis["validation"]),
    }
    cursor = conn.execute(
        """
        INSERT INTO ai_analysis_records(
            analysis_type, analysis_key, analysis_date, expert_id,
            jarvis_brief_id, version, evidence_packet_json, output_json,
            validation_json, status, source
        )
        VALUES (
            :analysis_type, :analysis_key, :analysis_date, :expert_id,
            :jarvis_brief_id, :version, :evidence_packet_json, :output_json,
            :validation_json, :status, :source
        )
        ON CONFLICT(analysis_type, analysis_date, analysis_key, version) DO UPDATE SET
            expert_id = excluded.expert_id,
            jarvis_brief_id = excluded.jarvis_brief_id,
            evidence_packet_json = excluded.evidence_packet_json,
            output_json = excluded.output_json,
            validation_json = excluded.validation_json,
            status = excluded.status,
            source = excluded.source,
            updated_at = datetime('now')
        RETURNING id
        """,
        payload,
    )
    return int(cursor.fetchone()["id"])


def get_ai_analysis_record(
    conn: sqlite3.Connection,
    analysis_type: str,
    analysis_date: str,
    analysis_key: str,
    version: str | None = None,
) -> sqlite3.Row | None:
    if version:
        return conn.execute(
            """
            SELECT *
            FROM ai_analysis_records
            WHERE analysis_type = ?
              AND analysis_date = ?
              AND analysis_key = ?
              AND version = ?
            LIMIT 1
            """,
            (analysis_type, analysis_date, analysis_key, version),
        ).fetchone()
    return conn.execute(
        """
        SELECT *
        FROM ai_analysis_records
        WHERE analysis_type = ?
          AND analysis_date = ?
          AND analysis_key = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (analysis_type, analysis_date, analysis_key),
    ).fetchone()


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def get_jarvis_daily_brief(
    conn: sqlite3.Connection,
    brief_date: str,
    version: str | None = None,
) -> sqlite3.Row | None:
    if version:
        return conn.execute(
            """
            SELECT *
            FROM jarvis_daily_briefs
            WHERE brief_date = ? AND version = ?
            LIMIT 1
            """,
            (brief_date, version),
        ).fetchone()
    return conn.execute(
        """
        SELECT *
        FROM jarvis_daily_briefs
        WHERE brief_date = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (brief_date,),
    ).fetchone()


def latest_jarvis_daily_brief(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM jarvis_daily_briefs
        ORDER BY brief_date DESC, updated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()


def upsert_expert(conn: sqlite3.Connection, expert: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO experts(
            expert_key, name, short_description, style_label, focus_weights_json,
            risk_budget_pct, max_drawdown_tolerance, allowed_asset_categories_json,
            default_cash_buffer_pct, review_cadence_days, lifecycle_state,
            mandate, source
        )
        VALUES (
            :expert_key, :name, :short_description, :style_label, :focus_weights_json,
            :risk_budget_pct, :max_drawdown_tolerance, :allowed_asset_categories_json,
            :default_cash_buffer_pct, :review_cadence_days, :lifecycle_state,
            :mandate, :source
        )
        ON CONFLICT(expert_key) DO UPDATE SET
            name = excluded.name,
            short_description = excluded.short_description,
            style_label = excluded.style_label,
            focus_weights_json = excluded.focus_weights_json,
            risk_budget_pct = excluded.risk_budget_pct,
            max_drawdown_tolerance = excluded.max_drawdown_tolerance,
            allowed_asset_categories_json = excluded.allowed_asset_categories_json,
            default_cash_buffer_pct = excluded.default_cash_buffer_pct,
            review_cadence_days = excluded.review_cadence_days,
            lifecycle_state = excluded.lifecycle_state,
            mandate = excluded.mandate,
            source = excluded.source,
            updated_at = datetime('now')
        RETURNING id
        """,
        expert,
    )
    return int(cursor.fetchone()["id"])


def list_experts(conn: sqlite3.Connection, lifecycle_state: str | None = None) -> list[sqlite3.Row]:
    if lifecycle_state:
        return conn.execute(
            """
            SELECT *
            FROM experts
            WHERE lifecycle_state = ?
            ORDER BY expert_key
            """,
            (lifecycle_state,),
        ).fetchall()
    return conn.execute(
        """
        SELECT *
        FROM experts
        ORDER BY
            CASE lifecycle_state
                WHEN 'active' THEN 0
                WHEN 'probation' THEN 1
                WHEN 'candidate' THEN 2
                WHEN 'retired' THEN 3
                ELSE 4
            END,
            expert_key
        """
    ).fetchall()


def get_expert(conn: sqlite3.Connection, expert_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM experts WHERE expert_key = ?", (expert_key,)).fetchone()


def upsert_advice_outcome_score(conn: sqlite3.Connection, score: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO advice_outcome_scores(
            advice_id, horizon_days, outcome_date, portfolio_return,
            benchmark_return, benchmark_identity, benchmark_source,
            benchmark_excess, drawdown_control,
            prediction_score, risk_score, advice_score, overall_score,
            details_json
        )
        VALUES (
            :advice_id, :horizon_days, :outcome_date, :portfolio_return,
            :benchmark_return, :benchmark_identity, :benchmark_source,
            :benchmark_excess, :drawdown_control,
            :prediction_score, :risk_score, :advice_score, :overall_score,
            :details_json
        )
        ON CONFLICT(advice_id, horizon_days) DO UPDATE SET
            outcome_date = excluded.outcome_date,
            portfolio_return = excluded.portfolio_return,
            benchmark_return = excluded.benchmark_return,
            benchmark_identity = excluded.benchmark_identity,
            benchmark_source = excluded.benchmark_source,
            benchmark_excess = excluded.benchmark_excess,
            drawdown_control = excluded.drawdown_control,
            prediction_score = excluded.prediction_score,
            risk_score = excluded.risk_score,
            advice_score = excluded.advice_score,
            overall_score = excluded.overall_score,
            details_json = excluded.details_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        score,
    )
    conn.execute(
        """
        UPDATE daily_advice
        SET prediction_score = ?,
            risk_score = ?,
            advice_score = ?,
            overall_score = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            score["prediction_score"],
            score["risk_score"],
            score["advice_score"],
            score["overall_score"],
            score["advice_id"],
        ),
    )
    return int(cursor.fetchone()["id"])


def latest_market_snapshot(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM market_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1").fetchone()


def start_task_log(
    conn: sqlite3.Connection,
    task_name: str,
    run_date: str,
    message: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO task_logs(task_name, run_date, status, message)
        VALUES (?, ?, 'running', ?)
        RETURNING id
        """,
        (task_name, run_date, message),
    )
    return int(cursor.fetchone()["id"])


def complete_task_log(
    conn: sqlite3.Connection,
    log_id: int,
    status: str,
    message: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE task_logs
        SET status = ?,
            message = COALESCE(?, message),
            error = ?,
            finished_at = datetime('now'),
            duration_ms = CAST((julianday(datetime('now')) - julianday(started_at)) * 86400000 AS INTEGER)
        WHERE id = ?
        """,
        (status, message, error, log_id),
    )
