from __future__ import annotations

import json

from investment_forecasting.ai_analysis import (
    EXPERT_ANALYSIS_SCHEMA_VERSION,
    JARVIS_ANALYSIS_SCHEMA_VERSION,
    MODEL_EVIDENCE_PACKET_VERSION,
    build_expert_ai_provider_request,
    build_jarvis_ai_provider_request,
    build_model_evidence_packet,
)
from investment_forecasting.ai_providers import AIProviderRequest, call_ai_provider, load_ai_provider_config
from investment_forecasting.cli import main as cli_main


def provider_request(**metadata):
    return AIProviderRequest(
        analysis_type="expert",
        schema_version="test_schema_v1",
        evidence_packet={"candidate_prediction_ids": [1], "expert_id": 1},
        prompt="Return structured JSON only.",
        output_schema={"type": "object"},
        metadata=metadata,
    )


def test_missing_provider_config_uses_deterministic_fallback(monkeypatch):
    monkeypatch.delenv("INVESTMENT_FORECASTING_AI_PROVIDER", raising=False)
    monkeypatch.delenv("INVESTMENT_FORECASTING_AI_API_KEY", raising=False)

    config = load_ai_provider_config()
    response = call_ai_provider(provider_request(), config)

    assert response.ok is False
    assert response.status == "fallback"
    assert response.provider == "deterministic"
    assert response.fallback_reason == "provider_not_configured"


def test_fake_provider_returns_structured_response(monkeypatch):
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_PROVIDER", "fake")
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_MODEL", "fake-model")

    response = call_ai_provider(provider_request(), load_ai_provider_config())

    assert response.ok is True
    assert response.status == "success"
    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert response.output["schema_version"] == "test_schema_v1"
    assert "risk_boundaries" in response.output


def test_fake_provider_error_is_auditable_fallback(monkeypatch):
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_PROVIDER", "fake")

    response = call_ai_provider(provider_request(force_error=True), load_ai_provider_config())

    assert response.ok is False
    assert response.status == "fallback"
    assert response.fallback_reason == "forced fake provider error"


def test_credentialed_provider_without_key_falls_back(monkeypatch):
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_PROVIDER", "openai")
    monkeypatch.delenv("INVESTMENT_FORECASTING_AI_API_KEY", raising=False)

    response = call_ai_provider(provider_request(), load_ai_provider_config())

    assert response.ok is False
    assert response.provider == "openai"
    assert response.fallback_reason == "missing_credentials"


def test_cli_provider_check_reports_fallback(monkeypatch, capsys):
    monkeypatch.delenv("INVESTMENT_FORECASTING_AI_PROVIDER", raising=False)
    monkeypatch.delenv("INVESTMENT_FORECASTING_AI_API_KEY", raising=False)

    assert cli_main(["ai", "provider-check"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "fallback"
    assert payload["fallback_reason"] == "provider_not_configured"


def test_cli_provider_check_reports_fake_success(monkeypatch, capsys):
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_PROVIDER", "fake")

    assert cli_main(["ai", "provider-check", "--analysis-type", "jarvis"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["provider"] == "fake"
    assert payload["output"]["analysis_type"] == "jarvis"


def test_ai_prompt_schema_contracts_include_news_retrieval_policy():
    expert_request = build_expert_ai_provider_request({"candidate_prediction_ids": [1], "news_evidence_ids": [10]})
    jarvis_request = build_jarvis_ai_provider_request({"model_prediction_ids": [1], "news_evidence_ids": [10]})

    assert expert_request.schema_version == EXPERT_ANALYSIS_SCHEMA_VERSION
    assert jarvis_request.schema_version == JARVIS_ANALYSIS_SCHEMA_VERSION
    assert "search_news_evidence" in expert_request.prompt
    assert "search_news_evidence" in jarvis_request.prompt
    assert "referenced_news_evidence_ids" in expert_request.output_schema["properties"]
    assert "referenced_news_evidence_ids" in jarvis_request.output_schema["properties"]


def test_model_evidence_packet_contains_reliability_fields():
    packet = build_model_evidence_packet(
        {
            "id": 7,
            "asset_id": 3,
            "asset_code": "510300",
            "asset_name": "沪深300ETF",
            "asset_type": "etf",
            "prediction_date": "2026-05-23",
            "horizon_days": 20,
            "model_version": "momentum_reversal_v1",
            "expected_return": 0.08,
            "up_probability": 0.62,
            "downside_risk": -0.03,
            "confidence": 0.9,
            "rank_score": 0.93,
            "rank_position": 1,
            "rank_count": 10,
            "same_category_key": "etf:broad_market",
            "same_category_rank": 1,
            "same_category_count": 4,
            "risk_adjusted_score": 0.88,
            "validation_status": "degraded",
            "recent_rank_ic": -0.04,
            "bucket_spread": -0.01,
            "degraded_reason": "negative_rank_ic",
            "reliability_evidence_json": json.dumps({"prediction_id": 7, "backtest_run_ids": [11]}),
        }
    )

    assert packet["packet_version"] == MODEL_EVIDENCE_PACKET_VERSION
    assert packet["model_version"] == "momentum_reversal_v1"
    assert packet["rank_score"] == 0.93
    assert packet["same_category_rank"] == 1
    assert packet["risk_adjusted_score"] == 0.88
    assert packet["validation_status"] == "degraded"
    assert packet["watch_only"] is True
    assert {"model_prediction_id": 7, "reliability_prediction_id": 7, "backtest_run_ids": [11]} == packet["evidence_ids"]
