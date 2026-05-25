from __future__ import annotations

import json
from statistics import mean
from typing import Any

from investment_forecasting.advice.generator import check_compliance
from investment_forecasting.ai_providers import AIProviderConfig, AIProviderRequest, AIProviderResponse, call_ai_provider


AI_ANALYSIS_VERSION = "ai_analysis_v1"
EXPERT_ANALYSIS_SCHEMA_VERSION = "expert_analysis_schema_v1"
JARVIS_ANALYSIS_SCHEMA_VERSION = "jarvis_analysis_schema_v1"

EXPERT_ANALYSIS_PROMPT = """你是本地投资研究系统中的独立专家分析器。只能使用 evidence_packet 内的结构化证据。
把事实、预测、专家观点、风险边界分开表达。新闻只能通过 search_news_evidence 显式检索，
不得把未返回的新闻写入结论；如果使用新闻，必须引用 returned evidence_id。
输出必须是符合 expert_analysis_schema_v1 的 JSON，不得给出确定收益、保本承诺或真实买卖指令。"""

JARVIS_ANALYSIS_PROMPT = """你是贾维斯理财助理的日度综合分析器。只能使用 evidence_packet 内的结构化证据。
把系统事实、模型预测、专家独立意见、专家表现、Jarvis 综合、观察触发器和风险边界分开。
新闻只能通过 search_news_evidence 显式检索并引用 evidence_id；不要把批量新闻塞进固定提示。
输出必须是符合 jarvis_analysis_schema_v1 的 JSON，并且只能作为研究辅助，不构成真实买卖指令。"""

EXPERT_ANALYSIS_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["thesis", "stance", "risk_boundaries", "referenced_prediction_ids"],
    "properties": {
        "thesis": {"type": "string"},
        "stance": {"type": "string"},
        "risk_boundaries": {"type": "array", "items": {"type": "string"}},
        "referenced_prediction_ids": {"type": "array", "items": {"type": "integer"}},
        "referenced_news_evidence_ids": {"type": "array", "items": {"type": "integer"}},
    },
}

JARVIS_ANALYSIS_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["system_facts", "final_synthesis", "risk_boundaries", "watch_triggers"],
    "properties": {
        "system_facts": {"type": "object"},
        "final_synthesis": {"type": "string"},
        "risk_boundaries": {"type": "array", "items": {"type": "string"}},
        "watch_triggers": {"type": "array", "items": {"type": "object"}},
        "referenced_news_evidence_ids": {"type": "array", "items": {"type": "integer"}},
    },
}

MODEL_EVIDENCE_PACKET_VERSION = "model_evidence_packet_v1"


class AIAnalysisValidationError(RuntimeError):
    pass


def build_expert_ai_analysis(
    expert: Any,
    portfolio: Any,
    candidates: list[Any],
    market: Any,
    analysis_date: str,
    *,
    provider_config: AIProviderConfig | None = None,
    provider_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not candidates:
        raise AIAnalysisValidationError("Expert AI analysis requires model prediction candidates")
    focus = _loads(expert["focus_weights_json"])
    ranked = sorted(candidates, key=lambda row: _candidate_score(row, focus), reverse=True)
    selected = ranked[:3]
    rejected = ranked[3:6]
    top = selected[0]
    risk_objections = _risk_objections(top, expert, market)
    proposed_action = "buy" if not risk_objections and _candidate_score(top, focus) > 0.03 else "no_trade"
    evidence_packet = {
        "expert": {
            "id": expert["id"],
            "expert_key": expert["expert_key"],
            "name": expert["name"],
            "style_label": expert["style_label"],
            "focus_weights": focus,
            "risk_budget_pct": expert["risk_budget_pct"],
            "max_drawdown_tolerance": expert["max_drawdown_tolerance"],
            "allowed_asset_categories": _loads(expert["allowed_asset_categories_json"]),
        },
        "portfolio": {
            "id": portfolio["id"],
            "cash": portfolio["cash"],
            "initial_capital": portfolio["initial_capital"],
        },
        "market_snapshot_id": market["id"] if market else None,
        "market_sentiment": market["sentiment"] if market else "unknown",
        "candidate_prediction_ids": [row["prediction_id"] for row in candidates],
        "candidates": [_candidate_packet(row, focus) for row in ranked[:8]],
        "style_guidance": _style_guidance(expert["style_label"]),
    }
    output = {
        "thesis": _expert_thesis(expert, top, proposed_action, market),
        "watched_signals": _watched_signals(focus),
        "selected_candidates": [_candidate_view(row, focus) for row in selected],
        "rejected_candidates": [_candidate_view(row, focus) for row in rejected],
        "risk_objections": risk_objections,
        "confidence": _mean(row["confidence"] for row in selected),
        "proposed_action": proposed_action,
        "stance": "小仓位观察" if proposed_action == "buy" else "防守观察",
        "referenced_prediction_ids": [row["prediction_id"] for row in selected],
        "referenced_news_evidence_ids": [],
    }
    provider_response = call_ai_provider(
        build_expert_ai_provider_request(evidence_packet, metadata=provider_metadata),
        provider_config,
    )
    provider_metadata_payload = _validated_provider_metadata(provider_response, evidence_packet)
    if provider_metadata_payload.get("status") == "success" and provider_response.output:
        output["provider_output"] = provider_response.output
        output["provider_summary"] = provider_response.output.get("forecast_interpretation") or provider_response.output.get("final_synthesis")
    analysis = {
        "analysis_type": "expert",
        "analysis_key": expert["expert_key"],
        "analysis_date": analysis_date,
        "expert_id": expert["id"],
        "version": AI_ANALYSIS_VERSION,
        "evidence_packet": evidence_packet,
        "output": output,
        "validation": {
            "supported_prediction_ids": evidence_packet["candidate_prediction_ids"],
            "selected_prediction_ids": output["referenced_prediction_ids"],
            "unsupported_claims": [],
            "compliance_ok": True,
            "provider": provider_metadata_payload,
        },
        "status": "valid" if any(value for key, value in evidence_packet.items() if key.endswith("_ids")) else "fallback",
        "source": provider_response.source if provider_metadata_payload.get("status") == "success" else "deterministic_expert_ai_analysis_v1",
    }
    validate_ai_analysis_record(analysis)
    return analysis


def build_jarvis_ai_analysis(
    analysis_date: str,
    evidence: dict[str, Any],
    payload: dict[str, Any],
    jarvis_brief_id: int | None = None,
    *,
    provider_config: AIProviderConfig | None = None,
    provider_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_evidence = payload["evidence"]
    expert_views = []
    for summary in payload["expert_summary"]:
        expert_views.append(
            {
                "expert_id": summary["expert_id"],
                "expert_name": summary["expert_name"],
                "ai_analysis_id": summary.get("ai_analysis_id"),
                "independent_thesis": summary.get("ai_thesis"),
                "action": summary["action"],
                "score": summary.get("score"),
                "current_return": summary.get("current_return"),
            }
        )
    evidence_packet = {
        "market_snapshot_ids": source_evidence.get("market_snapshot_ids", []),
        "macro_observation_ids": source_evidence.get("macro_observation_ids", []),
        "capital_flow_ids": source_evidence.get("capital_flow_ids", []),
        "model_prediction_ids": source_evidence.get("model_prediction_ids", []),
        "model_evidence_packets": payload["model_summary"].get("top_forecasts", []),
        "model_prediction_count": source_evidence.get("model_prediction_count", 0),
        "backtest_run_ids": source_evidence.get("backtest_run_ids", []),
        "expert_ai_analysis_ids": source_evidence.get("expert_ai_analysis_ids", []),
        "expert_plan_ids": source_evidence.get("expert_plan_ids", []),
        "expert_scorecard_ids": source_evidence.get("expert_scorecard_ids", []),
        "virtual_valuation_ids": source_evidence.get("virtual_valuation_ids", []),
        "user_preference_id": source_evidence.get("user_preference_id"),
        "task_log_ids": source_evidence.get("task_log_ids", []),
        "confidence_gates": source_evidence.get("confidence_gates", []),
    }
    output = {
        "system_facts": {
            "market_snapshot_count": len(evidence_packet["market_snapshot_ids"]),
            "macro_observation_count": len(evidence_packet["macro_observation_ids"]),
            "capital_flow_count": len(evidence_packet["capital_flow_ids"]),
            "missing_evidence": payload["missing_evidence"],
            "stale_evidence": payload["stale_evidence"],
        },
        "model_interpretation": payload["model_summary"],
        "expert_independent_views": expert_views,
        "expert_performance": [
            {
                "expert_id": row["expert_id"],
                "expert_name": row["expert_name"],
                "score": row.get("score"),
                "current_return": row.get("current_return"),
                "max_drawdown": row.get("max_drawdown"),
                "risk_state": row.get("risk_state"),
            }
            for row in payload["expert_summary"]
        ],
        "expert_disagreement": payload["model_summary"].get("disagreement", {}),
        "final_synthesis": payload["combined_recommendation"],
        "risk_boundaries": payload["risk_warnings"],
        "watch_triggers": payload["focus_directions"],
        "referenced_news_evidence_ids": [],
    }
    provider_response = call_ai_provider(
        build_jarvis_ai_provider_request(evidence_packet, metadata=provider_metadata),
        provider_config,
    )
    provider_metadata_payload = _validated_provider_metadata(provider_response, evidence_packet)
    if provider_metadata_payload.get("status") == "success" and provider_response.output:
        output["provider_output"] = provider_response.output
        output["provider_summary"] = provider_response.output.get("forecast_interpretation") or provider_response.output.get("final_synthesis")
    analysis = {
        "analysis_type": "jarvis",
        "analysis_key": "jarvis",
        "analysis_date": analysis_date,
        "jarvis_brief_id": jarvis_brief_id,
        "version": AI_ANALYSIS_VERSION,
        "evidence_packet": evidence_packet,
        "output": output,
        "validation": {
            "required_links": {
                key: value for key, value in evidence_packet.items() if key.endswith("_ids")
            },
            "unsupported_claims": [],
            "compliance_ok": True,
            "provider": provider_metadata_payload,
        },
        "status": "valid",
        "source": provider_response.source if provider_metadata_payload.get("status") == "success" else "deterministic_jarvis_ai_analysis_v1",
    }
    validate_ai_analysis_record(analysis)
    return analysis


def build_expert_ai_provider_request(evidence_packet: dict[str, Any], metadata: dict[str, Any] | None = None) -> AIProviderRequest:
    return AIProviderRequest(
        analysis_type="expert",
        schema_version=EXPERT_ANALYSIS_SCHEMA_VERSION,
        evidence_packet=evidence_packet,
        prompt=EXPERT_ANALYSIS_PROMPT,
        output_schema=EXPERT_ANALYSIS_OUTPUT_SCHEMA,
        metadata=metadata or {},
    )


def build_jarvis_ai_provider_request(evidence_packet: dict[str, Any], metadata: dict[str, Any] | None = None) -> AIProviderRequest:
    return AIProviderRequest(
        analysis_type="jarvis",
        schema_version=JARVIS_ANALYSIS_SCHEMA_VERSION,
        evidence_packet=evidence_packet,
        prompt=JARVIS_ANALYSIS_PROMPT,
        output_schema=JARVIS_ANALYSIS_OUTPUT_SCHEMA,
        metadata=metadata or {},
    )


def deserialize_ai_analysis(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result["evidence_packet"] = json.loads(result.pop("evidence_packet_json"))
    result["output"] = json.loads(result.pop("output_json"))
    result["validation"] = json.loads(result.pop("validation_json"))
    return result


def validate_ai_analysis_record(analysis: dict[str, Any]) -> None:
    if not analysis.get("evidence_packet") or not analysis.get("output"):
        raise AIAnalysisValidationError("AI analysis requires evidence packet and output")
    text = json.dumps(analysis["output"], ensure_ascii=False)
    check_compliance(text)
    unsupported = _unsupported_prediction_claims(analysis)
    if unsupported:
        analysis.setdefault("validation", {})["unsupported_claims"] = unsupported
        raise AIAnalysisValidationError(f"unsupported AI claims: {unsupported}")
    unsupported_news = _unsupported_news_claims(analysis)
    if unsupported_news:
        analysis.setdefault("validation", {})["unsupported_news_claims"] = unsupported_news
        raise AIAnalysisValidationError(f"unsupported news evidence claims: {unsupported_news}")
    if analysis["analysis_type"] == "jarvis" and not _jarvis_has_minimum_links(analysis):
        raise AIAnalysisValidationError("Jarvis AI analysis requires traceable evidence links")


def _provider_validation_metadata(response: AIProviderResponse) -> dict[str, Any]:
    metadata = response.metadata()
    return {key: value for key, value in metadata.items() if value is not None}


def _validated_provider_metadata(response: AIProviderResponse, evidence_packet: dict[str, Any]) -> dict[str, Any]:
    metadata = _provider_validation_metadata(response)
    if not response.ok or response.output is None:
        return metadata
    try:
        check_compliance(json.dumps(response.output, ensure_ascii=False))
        referenced = set(response.output.get("referenced_evidence_keys") or [])
        unsupported_keys = sorted(referenced - set(evidence_packet.keys()))
        if unsupported_keys:
            metadata["status"] = "fallback"
            metadata["fallback_reason"] = f"unsupported_evidence_keys:{','.join(unsupported_keys)}"
    except Exception as exc:
        metadata["status"] = "fallback"
        metadata["fallback_reason"] = f"validation_rejected:{exc}"
    return metadata


def _unsupported_prediction_claims(analysis: dict[str, Any]) -> list[int]:
    if analysis.get("analysis_type") != "expert":
        return []
    evidence = analysis["evidence_packet"]
    output = analysis["output"]
    supported = {int(value) for value in evidence.get("candidate_prediction_ids", []) if value is not None}
    referenced = set()
    for key in ("referenced_prediction_ids",):
        referenced.update(int(value) for value in output.get(key, []) if value is not None)
    for key in ("selected_candidates", "rejected_candidates"):
        for item in output.get(key, []):
            if item.get("prediction_id") is not None:
                referenced.add(int(item["prediction_id"]))
    return sorted(referenced - supported)


def _unsupported_news_claims(analysis: dict[str, Any]) -> list[int]:
    evidence = analysis.get("evidence_packet") or {}
    output = analysis.get("output") or {}
    supported = {int(value) for value in evidence.get("news_evidence_ids", []) if value is not None}
    referenced = {int(value) for value in output.get("referenced_news_evidence_ids", []) if value is not None}
    if output.get("provider_output"):
        referenced.update(int(value) for value in output["provider_output"].get("referenced_news_evidence_ids", []) if value is not None)
    return sorted(referenced - supported)


def _jarvis_has_minimum_links(analysis: dict[str, Any]) -> bool:
    packet = analysis["evidence_packet"]
    output = analysis["output"]
    has_links = bool(packet.get("model_prediction_ids") or packet.get("expert_ai_analysis_ids") or packet.get("expert_plan_ids"))
    has_explicit_missing_state = bool(output.get("system_facts", {}).get("missing_evidence"))
    return has_links or has_explicit_missing_state


def _candidate_packet(row: Any, focus: dict[str, float]) -> dict[str, Any]:
    packet = build_model_evidence_packet(row)
    packet["feature_date"] = row["feature_date"]
    packet["price_date"] = row["price_date"]
    packet["analysis_score"] = _candidate_score(row, focus)
    packet["style_weighting"] = _style_weighting(packet)
    return packet


def _candidate_view(row: Any, focus: dict[str, float]) -> dict[str, Any]:
    packet = _candidate_packet(row, focus)
    return {
        "prediction_id": packet["prediction_id"],
        "asset_id": packet["asset_id"],
        "asset_name": packet["asset_name"],
        "expected_return": packet["expected_return"],
        "downside_risk": packet["downside_risk"],
        "confidence": packet["confidence"],
        "validation_status": packet["validation_status"],
        "recent_rank_ic": packet["recent_rank_ic"],
        "bucket_spread": packet["bucket_spread"],
        "degraded_reason": packet["degraded_reason"],
        "watch_only": packet["watch_only"],
        "analysis_score": packet["analysis_score"],
    }


def build_model_evidence_packet(row: Any) -> dict[str, Any]:
    validation_status = row["validation_status"] if _has_key(row, "validation_status") and row["validation_status"] else "unvalidated"
    recent_rank_ic = row["recent_rank_ic"] if _has_key(row, "recent_rank_ic") else None
    bucket_spread = row["bucket_spread"] if _has_key(row, "bucket_spread") else None
    degraded_reason = row["degraded_reason"] if _has_key(row, "degraded_reason") else None
    watch_reasons = _model_watch_reasons(validation_status, recent_rank_ic, bucket_spread, degraded_reason)
    reliability_evidence = _loads(row["reliability_evidence_json"]) if _has_key(row, "reliability_evidence_json") and row["reliability_evidence_json"] else {}
    return {
        "packet_version": MODEL_EVIDENCE_PACKET_VERSION,
        "prediction_id": row["prediction_id"] if _has_key(row, "prediction_id") else row["id"],
        "model_version": row["model_version"],
        "asset_id": row["asset_id"],
        "asset_code": row["asset_code"] if _has_key(row, "asset_code") else None,
        "asset_name": row["asset_name"] if _has_key(row, "asset_name") else None,
        "asset_type": row["asset_type"] if _has_key(row, "asset_type") else None,
        "prediction_date": row["prediction_date"],
        "horizon_days": row["horizon_days"],
        "expected_return": row["expected_return"],
        "up_probability": row["up_probability"],
        "downside_risk": row["downside_risk"],
        "confidence": row["confidence"],
        "rank_score": row["rank_score"] if _has_key(row, "rank_score") else None,
        "rank_position": row["rank_position"] if _has_key(row, "rank_position") else None,
        "rank_count": row["rank_count"] if _has_key(row, "rank_count") else None,
        "same_category_key": row["same_category_key"] if _has_key(row, "same_category_key") else None,
        "same_category_rank": row["same_category_rank"] if _has_key(row, "same_category_rank") else None,
        "same_category_count": row["same_category_count"] if _has_key(row, "same_category_count") else None,
        "risk_adjusted_score": row["risk_adjusted_score"] if _has_key(row, "risk_adjusted_score") else None,
        "validation_status": validation_status,
        "recent_rank_ic": recent_rank_ic,
        "bucket_spread": bucket_spread,
        "degraded_reason": degraded_reason,
        "watch_only": bool(watch_reasons),
        "watch_reasons": watch_reasons,
        "evidence_ids": {
            "model_prediction_id": row["prediction_id"] if _has_key(row, "prediction_id") else row["id"],
            "reliability_prediction_id": reliability_evidence.get("prediction_id"),
            "backtest_run_ids": reliability_evidence.get("backtest_run_ids", []),
        },
    }


def _model_watch_reasons(
    validation_status: str,
    recent_rank_ic: float | None,
    bucket_spread: float | None,
    degraded_reason: str | None,
) -> list[str]:
    reasons = []
    if validation_status == "degraded":
        reasons.append(degraded_reason or "validation_status=degraded")
    if recent_rank_ic is not None and float(recent_rank_ic) < 0:
        reasons.append("recent_rank_ic_negative")
    if bucket_spread is not None and float(bucket_spread) < 0:
        reasons.append("bucket_spread_negative")
    return reasons


def _style_guidance(style_label: str) -> dict[str, str]:
    if "趋势" in style_label:
        return {"primary": "优先看 rank_score 和 Rank IC；degraded 趋势信号只能观察。"}
    if "防守" in style_label:
        return {"primary": "优先看 downside_risk、risk_adjusted_score 和 bucket_spread；degraded 信号不得加仓。"}
    if "宏观" in style_label:
        return {"primary": "把模型可靠性与市场状态一起解释；单一模型不能覆盖宏观风险。"}
    return {"primary": "均衡比较 expected_return、risk_adjusted_score、Rank IC 和验证状态。"}


def _style_weighting(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank_usable": packet["recent_rank_ic"] is not None and float(packet["recent_rank_ic"]) >= 0,
        "bucket_usable": packet["bucket_spread"] is not None and float(packet["bucket_spread"]) >= 0,
        "must_remain_context": packet["watch_only"],
    }


def _has_key(row: Any, key: str) -> bool:
    try:
        row[key]
        return True
    except (KeyError, IndexError):
        return False


def _candidate_score(row: Any, focus: dict[str, float]) -> float:
    values = {
        "return_20d": row["return_20d"] or 0.0,
        "return_60d": row["return_60d"] or 0.0,
        "up_probability": (row["up_probability"] or 0.5) - 0.5,
        "expected_return": row["expected_return"] or 0.0,
        "confidence": row["confidence"] or 0.0,
        "volatility": -(row["volatility_20d"] or 0.0),
        "max_drawdown": row["max_drawdown_60d"] or 0.0,
        "fund_metadata_quality": 0.02 if row["asset_type"] == "fund" else 0.0,
        "sharpe": row["sharpe_60d"] or 0.0,
        "calmar": row["calmar_60d"] or 0.0,
        "backtest_quality": row["confidence"] or 0.0,
        "prediction_confidence": row["confidence"] or 0.0,
    }
    return sum(float(weight) * values.get(key, 0.0) for key, weight in focus.items())


def _risk_objections(row: Any, expert: Any, market: Any) -> list[str]:
    objections = []
    tolerance = float(expert["max_drawdown_tolerance"])
    if abs(row["downside_risk"] or 0.0) > tolerance:
        objections.append("下行风险超过该专家容忍度")
    if abs(row["max_drawdown_60d"] or 0.0) > tolerance:
        objections.append("历史回撤超过该专家容忍度")
    if market and market["sentiment"] == "risk_off":
        objections.append("市场快照偏风险规避")
    return objections


def _expert_thesis(expert: Any, top: Any, proposed_action: str, market: Any) -> str:
    sentiment = market["sentiment"] if market else "unknown"
    if proposed_action == "buy":
        return (
            f"{expert['name']}基于{expert['style_label']}观察到{top['asset_name']}的模型收益、置信度和风险边界相对匹配，"
            f"市场状态为{sentiment}，仅建议进入虚拟组合的小仓位观察。"
        )
    return (
        f"{expert['name']}基于{expert['style_label']}认为当前候选证据仍需确认，"
        f"市场状态为{sentiment}，优先保持虚拟组合防守观察。"
    )


def _watched_signals(focus: dict[str, float]) -> list[str]:
    return [key for key, _ in sorted(focus.items(), key=lambda item: item[1], reverse=True)[:5]]


def _mean(values: Any) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None


def _loads(raw: Any) -> Any:
    if isinstance(raw, str):
        return json.loads(raw)
    return raw
