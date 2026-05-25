from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping


AI_PROVIDER_CONFIG_PREFIX = "INVESTMENT_FORECASTING_AI_"


class AIProviderError(RuntimeError):
    """Raised when an AI provider cannot return a usable response."""


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str = "deterministic"
    model: str = "deterministic-fallback"
    timeout_seconds: float = 15.0
    api_key_present: bool = False
    enabled: bool = False

    @property
    def requires_credentials(self) -> bool:
        return self.provider not in {"deterministic", "fake"}


@dataclass(frozen=True)
class AIProviderRequest:
    analysis_type: str
    schema_version: str
    evidence_packet: dict[str, Any]
    prompt: str
    output_schema: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIProviderResponse:
    ok: bool
    provider: str
    model: str
    source: str
    status: str
    output: dict[str, Any] | None = None
    duration_ms: int = 0
    error: str | None = None
    fallback_reason: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "fallback_reason": self.fallback_reason,
        }


def load_ai_provider_config(env: Mapping[str, str] | None = None) -> AIProviderConfig:
    values = env or os.environ
    provider = values.get(f"{AI_PROVIDER_CONFIG_PREFIX}PROVIDER", "deterministic").strip().lower() or "deterministic"
    model = values.get(f"{AI_PROVIDER_CONFIG_PREFIX}MODEL") or ("fake-structured-json" if provider == "fake" else "deterministic-fallback")
    timeout_raw = values.get(f"{AI_PROVIDER_CONFIG_PREFIX}TIMEOUT_SECONDS", "15")
    try:
        timeout_seconds = max(0.1, float(timeout_raw))
    except ValueError:
        timeout_seconds = 15.0
    api_key_present = bool(values.get(f"{AI_PROVIDER_CONFIG_PREFIX}API_KEY"))
    enabled = provider != "deterministic"
    return AIProviderConfig(
        provider=provider,
        model=model,
        timeout_seconds=timeout_seconds,
        api_key_present=api_key_present,
        enabled=enabled,
    )


def call_ai_provider(request: AIProviderRequest, config: AIProviderConfig | None = None) -> AIProviderResponse:
    resolved = config or load_ai_provider_config()
    start = time.perf_counter()
    try:
        if resolved.provider == "deterministic":
            return _fallback_response(resolved, start, "provider_not_configured")
        if resolved.requires_credentials and not resolved.api_key_present:
            return _fallback_response(resolved, start, "missing_credentials")
        if resolved.provider == "fake":
            return _fake_response(request, resolved, start)
        return _fallback_response(resolved, start, f"unsupported_provider:{resolved.provider}")
    except AIProviderError as exc:
        return _fallback_response(resolved, start, str(exc))


def _fake_response(request: AIProviderRequest, config: AIProviderConfig, start: float) -> AIProviderResponse:
    if request.metadata.get("force_error"):
        raise AIProviderError("forced fake provider error")
    if request.metadata.get("force_timeout"):
        return _fallback_response(config, start, "timeout")
    output = {
        "schema_version": request.schema_version,
        "analysis_type": request.analysis_type,
        "facts": ["仅使用 evidence_packet 中的结构化字段。"],
        "forecast_interpretation": "fake provider dry-run response",
        "risk_boundaries": ["仅作研究辅助，不构成真实买卖指令。"],
        "referenced_evidence_keys": sorted(request.evidence_packet.keys()),
    }
    return AIProviderResponse(
        ok=True,
        provider=config.provider,
        model=config.model,
        source=f"provider:{config.provider}:{config.model}",
        status="success",
        output=output,
        duration_ms=_duration_ms(start),
    )


def _fallback_response(config: AIProviderConfig, start: float, reason: str) -> AIProviderResponse:
    return AIProviderResponse(
        ok=False,
        provider=config.provider,
        model=config.model,
        source="deterministic_fallback",
        status="fallback",
        duration_ms=_duration_ms(start),
        fallback_reason=reason,
    )


def _duration_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))
