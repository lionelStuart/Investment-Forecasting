from __future__ import annotations

from math import sqrt
from statistics import mean, stdev

from investment_forecasting.quant.features import PricePoint


PRIMARY_MODEL_VERSION = "baseline_mean_v1"
CANDIDATE_MODEL_VERSIONS = ("momentum_reversal_v1", "risk_adjusted_factor_v1")
MODEL_VERSIONS = (PRIMARY_MODEL_VERSION, *CANDIDATE_MODEL_VERSIONS)
MODEL_STATES = {
    PRIMARY_MODEL_VERSION: "baseline",
    "momentum_reversal_v1": "candidate",
    "risk_adjusted_factor_v1": "candidate",
}


def forecast_expected_return(model_version: str, history: list[PricePoint], horizon_days: int) -> float:
    returns = daily_returns(history)
    if model_version == PRIMARY_MODEL_VERSION:
        return mean(returns) * horizon_days
    if model_version == "momentum_reversal_v1":
        return momentum_reversal_return(returns, horizon_days)
    if model_version == "risk_adjusted_factor_v1":
        return risk_adjusted_factor_return(returns, horizon_days)
    raise ValueError(f"Unknown model version: {model_version}")


def daily_returns(history: list[PricePoint]) -> list[float]:
    if len(history) < 2:
        raise ValueError("At least two historical prices are required")
    return [(history[index].value / history[index - 1].value) - 1.0 for index in range(1, len(history))]


def momentum_reversal_return(returns: list[float], horizon_days: int) -> float:
    short_window = returns[-min(5, len(returns)) :]
    medium_window = returns[-min(20, len(returns)) :]
    short_momentum = mean(short_window)
    medium_trend = mean(medium_window)
    # Interpretable candidate: respect recent momentum while fading crowded
    # medium-term moves through a partial reversal term.
    return ((short_momentum * 0.7) - (medium_trend * 0.3)) * horizon_days


def risk_adjusted_factor_return(returns: list[float], horizon_days: int) -> float:
    avg_return = mean(returns)
    volatility = stdev(returns) if len(returns) >= 2 else 0.0
    win_rate = sum(1 for value in returns if value > 0) / len(returns)
    low_win_rate_penalty = max(0.0, 0.5 - win_rate) * 0.01
    return (avg_return * horizon_days) - (volatility * sqrt(horizon_days) * 0.5) - low_win_rate_penalty
