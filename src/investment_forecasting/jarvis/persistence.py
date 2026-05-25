from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from investment_forecasting.db import (
    connect,
    get_jarvis_daily_brief,
    latest_jarvis_daily_brief,
    upsert_jarvis_daily_brief,
)


DEFAULT_JARVIS_VERSION = "jarvis_v1"
PROHIBITED_LANGUAGE = ("保本", "稳赚", "必赚", "无风险收益", "保证收益", "guaranteed return")


class JarvisPersistenceError(ValueError):
    pass


def save_jarvis_brief(
    db_path: str | Path,
    *,
    brief_date: str,
    focus_directions: list[dict[str, Any]] | list[str],
    one_line_stance: str,
    model_summary: dict[str, Any] | list[dict[str, Any]],
    expert_summary: dict[str, Any] | list[dict[str, Any]],
    combined_recommendation: str,
    risk_warnings: str,
    evidence: dict[str, Any] | list[dict[str, Any]],
    missing_evidence: list[dict[str, Any]] | list[str] | None = None,
    stale_evidence: list[dict[str, Any]] | list[str] | None = None,
    version: str = DEFAULT_JARVIS_VERSION,
    source: str = "system",
) -> dict[str, Any]:
    record = build_jarvis_brief_record(
        brief_date=brief_date,
        focus_directions=focus_directions,
        one_line_stance=one_line_stance,
        model_summary=model_summary,
        expert_summary=expert_summary,
        combined_recommendation=combined_recommendation,
        risk_warnings=risk_warnings,
        evidence=evidence,
        missing_evidence=missing_evidence,
        stale_evidence=stale_evidence,
        version=version,
        source=source,
    )
    with connect(db_path) as conn:
        brief_id = upsert_jarvis_daily_brief(conn, record)
        row = get_jarvis_daily_brief(conn, brief_date, version)
    if row is None:
        raise JarvisPersistenceError("Jarvis brief was not readable after save")
    return deserialize_jarvis_brief(row, brief_id=brief_id)


def get_jarvis_brief(
    db_path: str | Path,
    *,
    brief_date: str | None = None,
    version: str | None = None,
) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = get_jarvis_daily_brief(conn, brief_date, version) if brief_date else latest_jarvis_daily_brief(conn)
    return deserialize_jarvis_brief(row) if row else None


def build_jarvis_brief_record(
    *,
    brief_date: str,
    focus_directions: list[dict[str, Any]] | list[str],
    one_line_stance: str,
    model_summary: dict[str, Any] | list[dict[str, Any]],
    expert_summary: dict[str, Any] | list[dict[str, Any]],
    combined_recommendation: str,
    risk_warnings: str,
    evidence: dict[str, Any] | list[dict[str, Any]],
    missing_evidence: list[dict[str, Any]] | list[str] | None = None,
    stale_evidence: list[dict[str, Any]] | list[str] | None = None,
    version: str = DEFAULT_JARVIS_VERSION,
    source: str = "system",
) -> dict[str, Any]:
    _require_text("brief_date", brief_date)
    _require_text("version", version)
    _require_text("one_line_stance", one_line_stance)
    _require_text("combined_recommendation", combined_recommendation)
    _require_text("risk_warnings", risk_warnings)
    _require_text("source", source)
    _require_non_empty("focus_directions", focus_directions)
    _require_non_empty("model_summary", model_summary)
    _require_non_empty("evidence", evidence)
    if expert_summary is None:
        raise JarvisPersistenceError("expert_summary is required")
    user_facing = {
        "focus_directions": focus_directions,
        "one_line_stance": one_line_stance,
        "model_summary": model_summary,
        "expert_summary": expert_summary,
        "combined_recommendation": combined_recommendation,
        "risk_warnings": risk_warnings,
    }
    _reject_unsafe_language(user_facing)
    return {
        "brief_date": brief_date,
        "version": version,
        "focus_directions_json": _json_dumps(focus_directions),
        "one_line_stance": one_line_stance,
        "model_summary_json": _json_dumps(model_summary),
        "expert_summary_json": _json_dumps(expert_summary),
        "combined_recommendation": combined_recommendation,
        "risk_warnings": risk_warnings,
        "evidence_json": _json_dumps(evidence),
        "missing_evidence_json": _json_dumps(missing_evidence or []),
        "stale_evidence_json": _json_dumps(stale_evidence or []),
        "source": source,
    }


def deserialize_jarvis_brief(row: sqlite3.Row, brief_id: int | None = None) -> dict[str, Any]:
    return {
        "id": brief_id if brief_id is not None else row["id"],
        "brief_date": row["brief_date"],
        "version": row["version"],
        "focus_directions": json.loads(row["focus_directions_json"]),
        "one_line_stance": row["one_line_stance"],
        "model_summary": json.loads(row["model_summary_json"]),
        "expert_summary": json.loads(row["expert_summary_json"]),
        "combined_recommendation": row["combined_recommendation"],
        "risk_warnings": row["risk_warnings"],
        "evidence": json.loads(row["evidence_json"]),
        "missing_evidence": json.loads(row["missing_evidence_json"]),
        "stale_evidence": json.loads(row["stale_evidence_json"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _require_text(field: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise JarvisPersistenceError(f"{field} is required")


def _require_non_empty(field: str, value: Any) -> None:
    if value is None or value == [] or value == {}:
        raise JarvisPersistenceError(f"{field} is required")


def _reject_unsafe_language(value: Any) -> None:
    strings = _flatten_strings(value)
    for text in strings:
        lowered = text.lower()
        for phrase in PROHIBITED_LANGUAGE:
            if phrase.lower() in lowered:
                raise JarvisPersistenceError(f"unsafe certainty language is not allowed: {phrase}")


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(_flatten_strings(item))
        return result
    if isinstance(value, list | tuple):
        result = []
        for item in value:
            result.extend(_flatten_strings(item))
        return result
    return []
