"""In-memory adaptive route-pressure tracking for lane-aware routing."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


def _issue_type_from_error(error: str) -> str:
    lowered = str(error or "").lower()
    if any(token in lowered for token in ("quota", "insufficient_quota", "billing hard limit")):
        return "quota-exhausted"
    if any(token in lowered for token in ("429", "rate limit", "rate-limit", "too many requests")):
        return "rate-limited"
    if any(token in lowered for token in ("timeout", "timed out")):
        return "timeout"
    if any(token in lowered for token in ("model", "not found", "unsupported")):
        return "model-unavailable"
    return "error"


@dataclass
class RoutePressure:
    provider_name: str
    consecutive_failures: int = 0
    last_issue_type: str = ""
    last_issue_detail: str = ""
    last_issue_at: float = 0.0
    last_success_at: float = 0.0
    avg_latency_ms: float = 0.0
    _latencies: list[float] = field(default_factory=list)

    def record_success(self, latency_ms: float = 0.0) -> None:
        self.consecutive_failures = 0
        self.last_success_at = time.time()
        if latency_ms > 0:
            self._latencies.append(latency_ms)
            if len(self._latencies) > 20:
                self._latencies = self._latencies[-20:]
            self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_failure(self, error: str) -> None:
        self.consecutive_failures += 1
        self.last_issue_at = time.time()
        self.last_issue_detail = str(error or "")
        self.last_issue_type = _issue_type_from_error(error)

    def penalty(self) -> int:
        penalty = min(self.consecutive_failures * 4, 20)
        if self.last_issue_type == "quota-exhausted":
            penalty += 24
        elif self.last_issue_type == "rate-limited":
            penalty += 16
        elif self.last_issue_type == "timeout":
            penalty += 8
        elif self.last_issue_type == "model-unavailable":
            penalty += 18

        if self.avg_latency_ms >= 4000:
            penalty += 12
        elif self.avg_latency_ms >= 2000:
            penalty += 6
        elif self.avg_latency_ms >= 1200:
            penalty += 3
        return penalty

    def to_dict(self) -> dict[str, Any]:
        return {
            "consecutive_failures": self.consecutive_failures,
            "last_issue_type": self.last_issue_type,
            "last_issue_detail": self.last_issue_detail,
            "last_issue_at": self.last_issue_at,
            "last_success_at": self.last_success_at,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "penalty": self.penalty(),
        }


class AdaptiveRouteState:
    """Lightweight in-memory pressure state for provider routes."""

    def __init__(self) -> None:
        self._routes: dict[str, RoutePressure] = {}

    def _route(self, provider_name: str) -> RoutePressure:
        if provider_name not in self._routes:
            self._routes[provider_name] = RoutePressure(provider_name=provider_name)
        return self._routes[provider_name]

    def record_success(self, provider_name: str, *, latency_ms: float = 0.0) -> None:
        self._route(provider_name).record_success(latency_ms)

    def record_failure(self, provider_name: str, *, error: str) -> None:
        self._route(provider_name).record_failure(error)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: route.to_dict() for name, route in self._routes.items()}

    def provider_snapshot(self, provider_name: str) -> dict[str, Any]:
        return self._route(provider_name).to_dict()
