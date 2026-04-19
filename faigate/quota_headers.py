"""Header-capture middleware — mines rate-limit and quota hints from
provider response headers so Anthropic/OpenAI/OpenRouter/DeepSeek-class
providers get a free, near-realtime quota signal without an extra API call.

Why this exists
---------------
Phase 2 (``quota_poller``) only covers providers with a *dedicated* balance
endpoint. For everything else (Anthropic, OpenAI-compatible gateways,
OpenRouter), the quota signal is folded into every response as HTTP
headers — it's essentially free telemetry that we'd otherwise ignore.

This module is intentionally a **passive observer**: any call site with a
response object can invoke :func:`record_response_headers(provider_name,
headers)` and the module will:

1. Parse recognised rate-limit headers into a structured snapshot.
2. If the provider maps to a ``rolling_window`` package in the external
   catalog, update that package's ``used_credits`` (as used-vs-limit
   ratio × limit) so the router and dashboard see a fresh number.
3. Log at DEBUG; never raise.

Header dialects recognised
--------------------------

OpenAI / DeepSeek / OpenRouter (x-ratelimit family)::

    x-ratelimit-limit-requests   → window size in requests
    x-ratelimit-remaining-requests → remaining requests
    x-ratelimit-reset-requests   → seconds-until-reset, or ISO-8601
    x-ratelimit-limit-tokens     → token budget
    x-ratelimit-remaining-tokens → remaining tokens
    x-ratelimit-reset-tokens     → seconds-until-reset
    retry-after                  → 429 back-off seconds

Anthropic (anthropic-ratelimit-* family)::

    anthropic-ratelimit-requests-limit
    anthropic-ratelimit-requests-remaining
    anthropic-ratelimit-requests-reset   (ISO-8601)
    anthropic-ratelimit-tokens-limit
    anthropic-ratelimit-tokens-remaining
    anthropic-ratelimit-tokens-reset

Google AI (Gemini) — mostly empty. When present we pick up
``x-goog-quota-*`` hints but confidence is low.

Anything unrecognised is silently ignored; the module never fails a
request over a missing/garbled header.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .quota_tracker import update_package_usage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HeaderSnapshot:
    """Parsed rate-limit state from one provider response.

    All fields optional — providers return varying subsets. ``remaining``
    and ``limit`` are the two that actually steer routing; the rest are
    diagnostic.
    """

    provider_id: str
    dialect: str  # "openai" | "anthropic" | "google" | "openrouter" | "unknown"
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_at: datetime | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_at: datetime | None = None
    retry_after_seconds: float | None = None
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def has_useful_signal(self) -> bool:
        """True iff we got at least one of the four steering numbers."""
        return any(
            v is not None
            for v in (
                self.limit_requests,
                self.remaining_requests,
                self.limit_tokens,
                self.remaining_tokens,
            )
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_reset(val: Any, *, now: datetime | None = None) -> datetime | None:
    """Accept either ISO-8601 ('2026-04-18T03:00:00Z') or seconds-until
    (``"59"`` or ``"59s"``) and return an absolute UTC datetime.
    """
    if val is None:
        return None
    raw = str(val).strip()
    if not raw:
        return None
    # Strip optional 's' suffix common in x-ratelimit-reset-*.
    if raw.endswith("s") and raw[:-1].replace(".", "", 1).isdigit():
        raw = raw[:-1]
    # Plain seconds-delta.
    try:
        secs = float(raw)
        if secs < 0:
            return None
        base = now or datetime.now(timezone.utc)
        # Sanity: seconds-delta should fit in ~24h for rate-limit resets.
        if secs < 86400 * 2:
            return base + timedelta(seconds=secs)
    except ValueError:
        pass
    # ISO-8601.
    try:
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _detect_dialect(headers: Mapping[str, str]) -> str:
    """Best-effort dialect tagging based on which key prefixes show up."""
    lower = {k.lower() for k in headers.keys()}
    if any(k.startswith("anthropic-ratelimit-") for k in lower):
        return "anthropic"
    if any(k.startswith("x-goog-") for k in lower):
        return "google"
    # OpenRouter ships both x-ratelimit-* and their own Openrouter-Provider
    # marker; detect via presence of limit-tokens-requests combo.
    if "openrouter-provider" in lower or "x-openrouter-provider" in lower:
        return "openrouter"
    if any(k.startswith("x-ratelimit-") for k in lower):
        return "openai"
    return "unknown"


def parse_headers(provider_id: str, headers: Mapping[str, str]) -> HeaderSnapshot:
    """Parse a single provider response's headers into a ``HeaderSnapshot``.

    Never raises. Missing/garbled fields become ``None`` and are filtered
    out by downstream consumers.
    """
    # Normalise to lowercase keys while keeping original case in raw payload.
    low = {k.lower(): v for k, v in headers.items()}
    dialect = _detect_dialect(headers)
    now = datetime.now(timezone.utc)

    if dialect == "anthropic":
        return HeaderSnapshot(
            provider_id=provider_id,
            dialect=dialect,
            limit_requests=_to_int(low.get("anthropic-ratelimit-requests-limit")),
            remaining_requests=_to_int(low.get("anthropic-ratelimit-requests-remaining")),
            reset_requests_at=_parse_reset(low.get("anthropic-ratelimit-requests-reset"), now=now),
            limit_tokens=_to_int(low.get("anthropic-ratelimit-tokens-limit")),
            remaining_tokens=_to_int(low.get("anthropic-ratelimit-tokens-remaining")),
            reset_tokens_at=_parse_reset(low.get("anthropic-ratelimit-tokens-reset"), now=now),
            retry_after_seconds=_to_float(low.get("retry-after")),
            raw=dict(low),
        )

    # OpenAI / OpenRouter / DeepSeek share the same header naming.
    if dialect in ("openai", "openrouter"):
        return HeaderSnapshot(
            provider_id=provider_id,
            dialect=dialect,
            limit_requests=_to_int(low.get("x-ratelimit-limit-requests") or low.get("x-ratelimit-limit")),
            remaining_requests=_to_int(low.get("x-ratelimit-remaining-requests") or low.get("x-ratelimit-remaining")),
            reset_requests_at=_parse_reset(
                low.get("x-ratelimit-reset-requests") or low.get("x-ratelimit-reset"),
                now=now,
            ),
            limit_tokens=_to_int(low.get("x-ratelimit-limit-tokens")),
            remaining_tokens=_to_int(low.get("x-ratelimit-remaining-tokens")),
            reset_tokens_at=_parse_reset(low.get("x-ratelimit-reset-tokens"), now=now),
            retry_after_seconds=_to_float(low.get("retry-after")),
            raw=dict(low),
        )

    # Fallback: pick up retry-after at least.
    return HeaderSnapshot(
        provider_id=provider_id,
        dialect=dialect,
        retry_after_seconds=_to_float(low.get("retry-after")),
        raw=dict(low),
    )


# ---------------------------------------------------------------------------
# In-process snapshot store (for dashboard, independent of package apply)
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_LATEST: dict[str, HeaderSnapshot] = {}


def latest_snapshot(provider_id: str) -> HeaderSnapshot | None:
    """Return the most recent snapshot seen for this provider, or None."""
    with _LOCK:
        return _LATEST.get(provider_id)


def all_latest_snapshots() -> dict[str, HeaderSnapshot]:
    """Copy of all latest snapshots keyed by provider_id."""
    with _LOCK:
        return dict(_LATEST)


# ---------------------------------------------------------------------------
# Catalog apply
# ---------------------------------------------------------------------------


def _find_rolling_window_package(
    provider_id: str,
    packages_cache: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    """Return ``(pkg_id, entry)`` for the rolling-window package attached
    to this provider, if any. First match wins — we assume one rolling
    window per provider (true for Claude Pro / OpenAI Plus)."""
    for pkg_id, entry in packages_cache.items():
        if entry.get("provider_id") != provider_id:
            continue
        if entry.get("package_type") != "rolling_window":
            continue
        if entry.get("source") != "header_capture":
            # Respect operator's choice: don't override a local_count entry
            # with header data unless they opted in via source=header_capture.
            continue
        return pkg_id, entry
    return None


def _apply_to_rolling_window(
    snapshot: HeaderSnapshot,
    packages_cache: dict[str, dict[str, Any]],
) -> bool:
    """If this provider has a rolling_window package marked
    ``source: header_capture``, refresh its counters from the snapshot.

    Returns True on successful apply. ``used_credits`` semantics on a
    rolling_window package = requests consumed in the current window,
    computed as ``limit - remaining`` (never negative).
    """
    if not snapshot.has_useful_signal:
        return False
    if snapshot.remaining_requests is None or snapshot.limit_requests is None:
        return False
    found = _find_rolling_window_package(snapshot.provider_id, packages_cache)
    if not found:
        return False
    pkg_id, entry = found

    used = max(0, snapshot.limit_requests - snapshot.remaining_requests)
    # Store the limit so quota_tracker can show fresh numbers; operators
    # configured a heuristic default in the catalog, provider's number wins.
    entry["limit_per_window"] = int(snapshot.limit_requests)
    update_package_usage(
        pkg_id,
        used_credits=float(used),
        source="header_capture",
        confidence="high",
        packages_cache=packages_cache,
    )
    logger.debug(
        "quota_headers: %s → %s used=%d/%d (dialect=%s)",
        snapshot.provider_id,
        pkg_id,
        used,
        snapshot.limit_requests,
        snapshot.dialect,
    )
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def record_response_headers(
    provider_id: str,
    headers: Mapping[str, str] | None,
    *,
    packages_cache: dict[str, dict[str, Any]] | None = None,
) -> HeaderSnapshot | None:
    """Ingest a response's headers. Safe to call from any hot path.

    Returns the parsed snapshot (or None if headers was empty) so callers
    that want to log / annotate responses can do so. Never raises — any
    exception is caught and logged at DEBUG.
    """
    if not headers:
        return None
    try:
        snap = parse_headers(provider_id, headers)
    except Exception as exc:  # noqa: BLE001 — observer must not break requests
        logger.debug("quota_headers: parse failed for %s: %s", provider_id, exc)
        return None

    with _LOCK:
        _LATEST[provider_id] = snap

    if snap.has_useful_signal:
        try:
            if packages_cache is None:
                from .provider_catalog import get_packages_catalog

                packages_cache = get_packages_catalog()
            _apply_to_rolling_window(snap, packages_cache)
        except Exception as exc:  # noqa: BLE001
            logger.debug("quota_headers: apply failed for %s: %s", provider_id, exc)

    return snap


__all__ = [
    "HeaderSnapshot",
    "parse_headers",
    "record_response_headers",
    "latest_snapshot",
    "all_latest_snapshots",
]
