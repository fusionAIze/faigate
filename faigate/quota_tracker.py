"""Quota tracker — unifies credit packages, rolling-window subscriptions, and
daily-reset limits into a single `QuotaStatus` that the router, dashboard and
alert engine all consume.

Why this exists
---------------
faigate already carried a simple "credit package" concept in
`provider_catalog._get_packages_for_provider()` with fields ``total_credits``,
``used_credits`` and ``expiry_date``. That covers metered providers like
Kilo/DeepSeek well, but gives nothing for:

* **Subscription-style quotas** (Anthropic Pro, OpenAI Plus) where the real
  constraint is "N messages per rolling 5h window", not credits.
* **Per-model weighting** (1 Opus message counts like ~5 Sonnet messages
  against the Pro plan budget).
* **Multi-source truth** — the same package's `used_credits` may be updated
  from three different mechanisms (API poll, response headers, local
  SQLite count) and we need to know which is the freshest/most reliable.

`QuotaStatus` is the single, stable, UI-facing representation. Callers never
read raw catalog fields; they call :func:`compute_quota_status` and get
everything (remaining, reset time, burn rate, alert color, source,
confidence) in one go.

Package catalog schema (v1.1)
-----------------------------
Extends the existing ``packages/catalog.v1.json``. All new fields optional
(back-compat with v1). Example entries::

  {
    "packages": {
      "kilo-credits-2026q2": {
        "provider_id": "kilocode",
        "package_type": "credits",            # default if omitted
        "total_credits": 25.00,                # USD
        "used_credits": 12.40,
        "expiry_date": "2026-04-27",           # YYYY-MM-DD
        "source": "api_poll",                  # api_poll|header_capture|local_count
        "confidence": "high",                  # high|medium|low|estimated
        "last_updated": "2026-04-17T22:00:00Z"
      },
      "claude-pro-5h-rolling": {
        "provider_id": "claude-code",
        "package_type": "rolling_window",
        "window_hours": 5,
        "limit_per_window": 40,                # messages Sonnet-class
        "model_weights": {
          "claude-opus-4-7": 5,                # 1 Opus counts as 5 Sonnet
          "claude-sonnet-4-6": 1
        },
        "source": "local_count",
        "confidence": "estimated",
        "notes": "Pro plan limit is not published; 40 msg/5h is heuristic."
      },
      "openai-plus-3h-rolling": {
        "provider_id": "openai-codex",
        "package_type": "rolling_window",
        "window_hours": 3,
        "limit_per_window": 40,
        "source": "local_count",
        "confidence": "estimated"
      },
      "gemini-free-daily": {
        "provider_id": "gemini-flash-lite",
        "package_type": "daily",
        "limit_per_day": 1500,
        "source": "local_count",
        "confidence": "estimated"
      }
    }
  }

Alert semantics
---------------
``alert`` is one of:

* ``ok`` — >14 days of runway and no expiry worry.
* ``watch`` — 5–14 days runway, or expiry 14–30 days away.
* ``topup`` — <5 days runway (metered) OR <2 days until expiry with credits
  still unburned.
* ``use_or_lose`` — expiry imminent AND remaining credits will not be
  consumed at current burn rate. Used by router to boost priority.
* ``exhausted`` — remaining <= 0.

Callers
-------
* ``router.py`` — uses ``remaining`` + ``alert`` to score lane preference
  (existing expiry bonus logic lives in router, this module just feeds it
  consistently across all 3 package types).
* ``dashboard.py`` — renders the per-provider quota bar with alert color.
* ``quota_poller.py`` — background task that calls
  :func:`update_package_usage` after fetching balances or counting requests.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("faigate.quota_tracker")

PackageType = Literal["credits", "rolling_window", "daily"]
AlertLevel = Literal["ok", "watch", "topup", "use_or_lose", "exhausted"]
SourceType = Literal["api_poll", "header_capture", "local_count", "manual"]
ConfidenceLevel = Literal["high", "medium", "low", "estimated"]


@dataclass
class QuotaStatus:
    """Unified view of a provider's remaining quota, regardless of package type.

    For ``credits`` packages: ``remaining``/``total`` are USD (or whatever unit
    the catalog uses — faigate is unit-agnostic). For ``rolling_window`` and
    ``daily``: they are request counts.

    ``reset_at`` is only meaningful for window-based types. ``expiry_at`` is
    only meaningful for credits. ``burn_per_day`` is an EWMA over the last
    7 days from the request log.
    """

    provider_id: str
    provider_group: str
    package_id: str
    package_type: PackageType
    total: float
    used: float
    remaining: float
    remaining_ratio: float  # 0.0 – 1.0
    alert: AlertLevel
    source: SourceType
    confidence: ConfidenceLevel
    last_updated: str | None = None  # ISO 8601
    # Window-specific
    window_hours: int | None = None
    reset_at: str | None = None  # ISO 8601, when window resets
    # Credit-specific
    expiry_date: str | None = None  # YYYY-MM-DD
    days_until_expiry: int | None = None
    burn_per_day: float | None = None
    projected_days_left: float | None = None
    # Diagnostics (not part of stable UI contract)
    notes: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_quota_status(
    package: dict[str, Any],
    *,
    now: datetime | None = None,
    sqlite_path: Path | None = None,
) -> QuotaStatus:
    """Translate a raw catalog package entry into a QuotaStatus.

    Inputs:
      * ``package``: a dict exactly as stored in the packages catalog (one
        value from ``packages_catalog.items()``). Must contain at least
        ``provider_id``. Everything else is defaulted or computed.
      * ``now``: injected for test determinism; defaults to ``datetime.now(UTC)``.
      * ``sqlite_path``: faigate.db path for looking up ``used`` for window
        types via local request counts. If ``None`` and the package is
        window-based, ``used`` falls back to the catalog-stored value.
    """
    now = now or datetime.now(UTC)
    package_id = package.get("package_id") or _synthesize_package_id(package)
    provider_id = package.get("provider_id") or "unknown"
    provider_group = package.get("provider_group") or _derive_provider_group(provider_id)
    pkg_type: PackageType = package.get("package_type") or "credits"
    source: SourceType = package.get("source") or "manual"
    confidence: ConfidenceLevel = package.get("confidence") or "medium"
    last_updated = package.get("last_updated")
    notes = package.get("notes")

    if pkg_type == "rolling_window":
        return _status_rolling_window(
            package, package_id, provider_id, provider_group, source, confidence, last_updated, notes, now, sqlite_path
        )
    if pkg_type == "daily":
        return _status_daily(
            package, package_id, provider_id, provider_group, source, confidence, last_updated, notes, now, sqlite_path
        )
    # Default: credits
    return _status_credits(
        package, package_id, provider_id, provider_group, source, confidence, last_updated, notes, now, sqlite_path
    )


def _derive_provider_group(provider_id: str) -> str:
    """Fallback grouping key when the catalog omits provider_group.

    Strips a trailing -<variant> segment (gemini-flash-lite -> gemini-flash;
    deepseek-chat -> deepseek) and collapses common family prefixes. Kept
    deliberately conservative so catalog-specified groups always win."""
    if not provider_id or provider_id == "unknown":
        return "unknown"
    for prefix in ("deepseek", "kilo", "gemini", "openai", "anthropic", "openrouter", "blackbox"):
        if provider_id.startswith(prefix):
            return prefix
    # Otherwise use the first dash-separated token.
    return provider_id.split("-", 1)[0]


# -----------------------------------------------------------------------------
# Per-package-type computation
# -----------------------------------------------------------------------------


def _status_credits(
    package: dict[str, Any],
    package_id: str,
    provider_id: str,
    provider_group: str,
    source: SourceType,
    confidence: ConfidenceLevel,
    last_updated: str | None,
    notes: str | None,
    now: datetime,
    sqlite_path: Path | None,
) -> QuotaStatus:
    total = float(package.get("total_credits") or 0.0)
    used = float(package.get("used_credits") or 0.0)
    remaining = max(0.0, total - used)
    ratio = (remaining / total) if total > 0 else 0.0

    expiry_iso = package.get("expiry_date")
    days_until_expiry: int | None = None
    if expiry_iso:
        try:
            expiry_date = date.fromisoformat(expiry_iso)
            days_until_expiry = (expiry_date - now.date()).days
        except ValueError:
            logger.warning("Invalid expiry_date %r on package %s", expiry_iso, package_id)

    # Burn rate: look at the last 7d of requests for this provider
    burn = _local_burn_per_day_usd(provider_id, now, sqlite_path, days=7)
    projected_days_left: float | None = None
    if burn and burn > 0:
        projected_days_left = remaining / burn

    alert = _classify_credits_alert(remaining, days_until_expiry, projected_days_left)

    return QuotaStatus(
        provider_id=provider_id,
        provider_group=provider_group,
        package_id=package_id,
        package_type="credits",
        total=total,
        used=used,
        remaining=remaining,
        remaining_ratio=ratio,
        alert=alert,
        source=source,
        confidence=confidence,
        last_updated=last_updated,
        expiry_date=expiry_iso,
        days_until_expiry=days_until_expiry,
        burn_per_day=burn,
        projected_days_left=projected_days_left,
        notes=notes,
    )


def _status_rolling_window(
    package: dict[str, Any],
    package_id: str,
    provider_id: str,
    provider_group: str,
    source: SourceType,
    confidence: ConfidenceLevel,
    last_updated: str | None,
    notes: str | None,
    now: datetime,
    sqlite_path: Path | None,
) -> QuotaStatus:
    window_hours = int(package.get("window_hours") or 5)
    limit = float(package.get("limit_per_window") or 0)
    model_weights: dict[str, float] = package.get("model_weights") or {}
    extra_ids = [str(p) for p in (package.get("extra_provider_ids") or [])]
    counted_ids = [provider_id, *extra_ids]

    # Local count: weighted request count over the last window_hours, summed
    # across provider_id + any extra_provider_ids sharing the same quota.
    used = 0.0
    earliest: datetime | None = None
    for pid in counted_ids:
        used += _local_count_in_window(pid, now, sqlite_path, window_hours=window_hours, model_weights=model_weights)
        cand = _earliest_request_in_window(pid, now, sqlite_path, window_hours=window_hours)
        if cand and (earliest is None or cand < earliest):
            earliest = cand
    remaining = max(0.0, limit - used)
    ratio = (remaining / limit) if limit > 0 else 0.0

    if earliest:
        reset_at = (earliest + timedelta(hours=window_hours)).isoformat()
    else:
        reset_at = (now + timedelta(hours=window_hours)).isoformat()

    alert = _classify_window_alert(remaining, limit)

    return QuotaStatus(
        provider_id=provider_id,
        provider_group=provider_group,
        package_id=package_id,
        package_type="rolling_window",
        total=limit,
        used=used,
        remaining=remaining,
        remaining_ratio=ratio,
        alert=alert,
        source=source,
        confidence=confidence,
        last_updated=last_updated,
        window_hours=window_hours,
        reset_at=reset_at,
        notes=notes,
        extras={"model_weights": model_weights} if model_weights else {},
    )


def _status_daily(
    package: dict[str, Any],
    package_id: str,
    provider_id: str,
    provider_group: str,
    source: SourceType,
    confidence: ConfidenceLevel,
    last_updated: str | None,
    notes: str | None,
    now: datetime,
    sqlite_path: Path | None,
) -> QuotaStatus:
    limit = float(package.get("limit_per_day") or 0)
    extra_ids = [str(p) for p in (package.get("extra_provider_ids") or [])]
    counted_ids = [provider_id, *extra_ids]

    # Count requests since UTC midnight — summed across counted_ids so a daily
    # quota shared by multiple router provider IDs (e.g. Gemini free tier
    # covers both gemini-flash and gemini-flash-lite) reads accurately.
    midnight = datetime(now.year, now.month, now.day, tzinfo=UTC)
    hours_since_midnight = (now - midnight).total_seconds() / 3600.0
    window = max(hours_since_midnight, 0.01)
    used = sum(
        _local_count_in_window(pid, now, sqlite_path, window_hours=window, model_weights={}) for pid in counted_ids
    )
    remaining = max(0.0, limit - used)
    ratio = (remaining / limit) if limit > 0 else 0.0

    next_midnight = midnight + timedelta(days=1)
    reset_at = next_midnight.isoformat()

    alert = _classify_window_alert(remaining, limit)

    return QuotaStatus(
        provider_id=provider_id,
        provider_group=provider_group,
        package_id=package_id,
        package_type="daily",
        total=limit,
        used=used,
        remaining=remaining,
        remaining_ratio=ratio,
        alert=alert,
        source=source,
        confidence=confidence,
        last_updated=last_updated,
        reset_at=reset_at,
        notes=notes,
    )


# -----------------------------------------------------------------------------
# Alert classifiers
# -----------------------------------------------------------------------------


def _classify_credits_alert(
    remaining: float,
    days_until_expiry: int | None,
    projected_days_left: float | None,
) -> AlertLevel:
    if remaining <= 0:
        return "exhausted"
    # Use-or-lose: expiring soon AND won't be burned at current rate
    if days_until_expiry is not None and days_until_expiry > 0:
        if projected_days_left is not None and projected_days_left > days_until_expiry:
            # Remaining credits will outlive expiry → waste risk
            if days_until_expiry <= 14:
                return "use_or_lose"
        if days_until_expiry <= 2:
            return "topup"
    if projected_days_left is not None:
        if projected_days_left < 2:
            return "topup"
        if projected_days_left < 14:
            return "watch"
    # No signal either way → assume OK
    return "ok"


def _classify_window_alert(remaining: float, limit: float) -> AlertLevel:
    if limit <= 0:
        return "ok"  # unconfigured
    if remaining <= 0:
        return "exhausted"
    ratio = remaining / limit
    if ratio < 0.1:
        return "topup"
    if ratio < 0.3:
        return "watch"
    return "ok"


# -----------------------------------------------------------------------------
# SQLite-backed counters (read-only)
# -----------------------------------------------------------------------------


def _open_db(sqlite_path: Path | None) -> sqlite3.Connection | None:
    if sqlite_path is None:
        return None
    try:
        # read-only, don't block writers
        uri = f"file:{sqlite_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.debug("quota_tracker: cannot open %s read-only: %s", sqlite_path, e)
        return None


def _local_count_in_window(
    provider_id: str,
    now: datetime,
    sqlite_path: Path | None,
    *,
    window_hours: float,
    model_weights: dict[str, float],
) -> float:
    """Count requests for ``provider_id`` in the last ``window_hours`` hours.

    If ``model_weights`` is non-empty, each row's weight is
    ``model_weights.get(row["model"], 1.0)``. Otherwise every row counts as 1.
    """
    conn = _open_db(sqlite_path)
    if conn is None:
        return 0.0
    try:
        cutoff = int((now - timedelta(hours=window_hours)).timestamp())
        if model_weights:
            cur = conn.execute(
                "SELECT model, COUNT(*) AS n FROM requests WHERE provider = ? AND timestamp >= ? GROUP BY model",
                (provider_id, cutoff),
            )
            total = 0.0
            for row in cur:
                model = row["model"] or ""
                weight = float(model_weights.get(model, 1.0))
                total += weight * int(row["n"])
            return total
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE provider = ? AND timestamp >= ?",
            (provider_id, cutoff),
        )
        row = cur.fetchone()
        return float(row["n"] if row else 0)
    except sqlite3.Error as e:
        logger.debug("quota_tracker: SQL error counting %s: %s", provider_id, e)
        return 0.0
    finally:
        conn.close()


def _earliest_request_in_window(
    provider_id: str,
    now: datetime,
    sqlite_path: Path | None,
    *,
    window_hours: float,
) -> datetime | None:
    conn = _open_db(sqlite_path)
    if conn is None:
        return None
    try:
        cutoff = int((now - timedelta(hours=window_hours)).timestamp())
        cur = conn.execute(
            "SELECT MIN(timestamp) AS t FROM requests WHERE provider = ? AND timestamp >= ?",
            (provider_id, cutoff),
        )
        row = cur.fetchone()
        if row and row["t"] is not None:
            return datetime.fromtimestamp(int(row["t"]), tz=UTC)
        return None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _local_burn_per_day_usd(
    provider_id: str,
    now: datetime,
    sqlite_path: Path | None,
    *,
    days: int = 7,
) -> float | None:
    """Average daily USD burn for ``provider_id`` over last ``days`` days.

    Returns None if there's no data (signals "no burn signal"). Never raises.
    """
    conn = _open_db(sqlite_path)
    if conn is None:
        return None
    try:
        cutoff = int((now - timedelta(days=days)).timestamp())
        cur = conn.execute(
            "SELECT SUM(cost_usd) AS s FROM requests WHERE provider = ? AND timestamp >= ?",
            (provider_id, cutoff),
        )
        row = cur.fetchone()
        if not row or row["s"] is None:
            return None
        total_usd = float(row["s"] or 0.0)
        if total_usd <= 0:
            return None
        return total_usd / max(days, 1)
    except sqlite3.Error:
        return None
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _synthesize_package_id(package: dict[str, Any]) -> str:
    pid = package.get("provider_id") or "unknown"
    pkg_type = package.get("package_type") or "credits"
    return f"{pid}-{pkg_type}"


def update_package_usage(
    package_id: str,
    *,
    used_credits: float | None = None,
    source: SourceType | None = None,
    confidence: ConfidenceLevel | None = None,
    packages_cache: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Mutate the in-memory catalog cache. Used by the balance poller and the
    header-capture middleware. Returns True on success.

    NOTE: This only updates the in-process cache. Persisting to disk is the
    poller's responsibility (it owns the JSON file atomicity).
    """
    if packages_cache is None:
        from .provider_catalog import get_packages_catalog

        packages_cache = get_packages_catalog()
    entry = packages_cache.get(package_id)
    if entry is None:
        logger.warning("quota_tracker.update: unknown package %s", package_id)
        return False
    if used_credits is not None:
        entry["used_credits"] = float(used_credits)
    if source is not None:
        entry["source"] = source
    if confidence is not None:
        entry["confidence"] = confidence
    entry["last_updated"] = datetime.now(UTC).isoformat(timespec="seconds")
    return True


def compute_all_statuses(
    *,
    now: datetime | None = None,
    sqlite_path: Path | None = None,
    packages_cache: dict[str, dict[str, Any]] | None = None,
) -> list[QuotaStatus]:
    """Compute QuotaStatus for every package in the catalog. Convenience
    wrapper for the dashboard."""
    if packages_cache is None:
        from .provider_catalog import get_packages_catalog

        packages_cache = get_packages_catalog()
    statuses: list[QuotaStatus] = []
    for pkg_id, pkg in packages_cache.items():
        # Inject the pkg_id so synthesized ids match
        enriched = dict(pkg)
        enriched.setdefault("package_id", pkg_id)
        try:
            statuses.append(compute_quota_status(enriched, now=now, sqlite_path=sqlite_path))
        except Exception as e:  # pragma: no cover — never let one broken pkg kill the dashboard
            logger.warning("quota_tracker: failed to compute %s: %s", pkg_id, e)
    return statuses


# Convenience for callers that want a single-liner diagnostic string
def format_status_line(status: QuotaStatus) -> str:
    """Short human-readable single-line status — for logs/dashboard tooltip."""
    icon = {
        "ok": "🟢",
        "watch": "🟡",
        "topup": "🟠",
        "use_or_lose": "⚠️",
        "exhausted": "🔴",
    }.get(status.alert, "⚪")
    if status.package_type == "credits":
        tail = ""
        if status.days_until_expiry is not None:
            tail = f" · exp {status.days_until_expiry}d"
        if status.projected_days_left is not None:
            tail += f" · proj {status.projected_days_left:.0f}d burn"
        return (
            f"{icon} {status.provider_id}: "
            f"{status.remaining:.2f}/{status.total:.2f} left"
            f"{tail} [{status.confidence}/{status.source}]"
        )
    # window-based
    return (
        f"{icon} {status.provider_id}: "
        f"{int(status.used)}/{int(status.total)} used "
        f"({status.package_type}, {status.window_hours or 24}h) "
        f"[{status.confidence}/{status.source}]"
    )


__all__ = [
    "AlertLevel",
    "ConfidenceLevel",
    "PackageType",
    "QuotaStatus",
    "SourceType",
    "compute_all_statuses",
    "compute_quota_status",
    "format_status_line",
    "update_package_usage",
]


if __name__ == "__main__":
    # Tiny self-test / demo without network access.
    logging.basicConfig(level=logging.INFO)
    demo_packages = {
        "kilo-q2": {
            "provider_id": "kilocode",
            "package_type": "credits",
            "total_credits": 25.0,
            "used_credits": 12.4,
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
            "source": "api_poll",
            "confidence": "high",
        },
        "claude-pro-5h": {
            "provider_id": "claude-code",
            "package_type": "rolling_window",
            "window_hours": 5,
            "limit_per_window": 40,
            "model_weights": {"claude-opus-4-7": 5, "claude-sonnet-4-6": 1},
            "source": "local_count",
            "confidence": "estimated",
        },
        "gemini-daily": {
            "provider_id": "gemini-flash-lite",
            "package_type": "daily",
            "limit_per_day": 1500,
            "source": "local_count",
            "confidence": "estimated",
        },
    }
    now = datetime.now(UTC)
    for pid, pkg in demo_packages.items():
        pkg["package_id"] = pid
        status = compute_quota_status(pkg, now=now)
        print(format_status_line(status))
        print("  →", status.to_dict())
        print()
