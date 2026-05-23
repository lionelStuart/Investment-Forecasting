from __future__ import annotations

import sqlite3
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
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
            "VALUES (?, datetime('now'))",
            ("001_init",),
        )
    return path


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
        SELECT p.*, a.code AS asset_code, a.name AS asset_name, a.asset_type
        FROM model_predictions p
        LEFT JOIN assets a ON a.id = p.asset_id
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


def upsert_advice_outcome_score(conn: sqlite3.Connection, score: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO advice_outcome_scores(
            advice_id, horizon_days, outcome_date, portfolio_return,
            benchmark_return, benchmark_excess, drawdown_control,
            prediction_score, risk_score, advice_score, overall_score,
            details_json
        )
        VALUES (
            :advice_id, :horizon_days, :outcome_date, :portfolio_return,
            :benchmark_return, :benchmark_excess, :drawdown_control,
            :prediction_score, :risk_score, :advice_score, :overall_score,
            :details_json
        )
        ON CONFLICT(advice_id, horizon_days) DO UPDATE SET
            outcome_date = excluded.outcome_date,
            portfolio_return = excluded.portfolio_return,
            benchmark_return = excluded.benchmark_return,
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
