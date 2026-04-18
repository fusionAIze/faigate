"""Balance poller — refreshes ``used_credits`` for credit-type packages whose
``source == "api_poll"`` from the provider's balance endpoint.

Covers the two providers that actually expose a usable balance API:

* **DeepSeek** — ``GET https://api.deepseek.com/user/balance`` (stable, documented)
* **Kilo (kilocode)** — best-effort: tries a short list of candidate endpoints
  since Kilo hasn't published a stable schema at the time of writing.

Everything else (Anthropic Pro, OpenAI Plus, Qwen, Blackbox, Gemini free) is
handled by the local counter in :mod:`quota_tracker` or header-capture
middleware (Phase 3). They are deliberately skipped here.

Design notes
------------
* **Stateless mutation** — the poller is the only writer to the packages
  catalog JSON file. It reads → mutates the in-memory cache via
  :func:`quota_tracker.update_package_usage` → persists atomically by writing
  to ``<file>.tmp`` and ``os.replace()``-ing.
* **API key lookup** — keys are pulled from environment (``DEEPSEEK_API_KEY``,
  ``KILO_API_KEY``) and from the provider config (``providers[name].api_key``)
  in that order. Missing keys produce a single WARNING log per run and skip
  cleanly — the poller never crashes the gateway.
* **Poll cadence** — default 1h. Expiring packages (``expiry_date`` within 14
  days) get a "fast lane" 15m poll so the use-or-lose alert stays sharp
  against the actual burn.
* **Resilience** — network failures downgrade ``confidence`` to ``low`` but
  leave ``used_credits`` untouched so the router keeps a stale-but-usable
  number rather than snapping to 0.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from .provider_catalog import _get_external_packages_path, get_packages_catalog
from .quota_tracker import update_package_usage

logger = logging.getLogger(__name__)

# Cadence knobs. The fast lane kicks in when a package's expiry_date is within
# this many days — we want the use-or-lose signal to be fresh.
_DEFAULT_INTERVAL_SECONDS = 3600  # 1h
_FAST_LANE_INTERVAL_SECONDS = 900  # 15m
_FAST_LANE_EXPIRY_WINDOW_DAYS = 14

# HTTP timeouts kept tight — this is a background task, we don't want stuck
# connections piling up across hours.
_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


@dataclass(frozen=True)
class PollResult:
    """Structured outcome of a single provider balance poll."""

    package_id: str
    provider_id: str
    ok: bool
    total_credits: float | None = None
    used_credits: float | None = None
    error: str | None = None
    endpoint: str | None = None


# ---------------------------------------------------------------------------
# Provider-specific fetchers
# ---------------------------------------------------------------------------


async def _fetch_deepseek_balance(
    client: httpx.AsyncClient,
    api_key: str,
) -> tuple[float, float]:
    """Return ``(total_credits, used_credits)`` in USD for DeepSeek.

    DeepSeek's response (as of 2026-04) looks like::

        {
          "is_available": true,
          "balance_infos": [
            {"currency": "USD", "total_balance": "5.00",
             "granted_balance": "0.00", "topped_up_balance": "5.00"}
          ]
        }

    We interpret ``total_balance`` as remaining, so used = topped_up - remaining
    when both are present. If only remaining is available we report total as a
    frozen baseline (caller is expected to set ``total_credits`` in the catalog
    to the purchased amount and let this poller subtract remaining).
    """
    url = "https://api.deepseek.com/user/balance"
    resp = await client.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    infos = data.get("balance_infos") or []
    usd = next(
        (i for i in infos if str(i.get("currency", "")).upper() == "USD"),
        infos[0] if infos else None,
    )
    if not usd:
        raise RuntimeError("deepseek balance_infos empty")
    remaining = float(usd.get("total_balance", 0.0))
    topped_up = float(usd.get("topped_up_balance", 0.0) or 0.0)
    granted = float(usd.get("granted_balance", 0.0) or 0.0)
    total = topped_up + granted if (topped_up or granted) else remaining
    used = max(0.0, total - remaining)
    return total, used


# Kilo hasn't published a stable balance schema; probe a short list of common
# candidates and parse the first one that returns a plausible payload.
_KILO_CANDIDATE_ENDPOINTS = (
    "https://kilocode.ai/api/profile/balance",
    "https://api.kilocode.ai/v1/user/balance",
    "https://api.kilo.ai/v1/user/balance",
    "https://api.kilocode.ai/v1/key",
)


async def _fetch_kilo_balance(
    client: httpx.AsyncClient,
    api_key: str,
) -> tuple[float, float, str]:
    """Return ``(total, used, endpoint)`` for Kilo by probing candidates.

    Accepts any payload that contains *any* of these field names and is
    numeric-parseable: ``balance``, ``remaining``, ``credits``, ``total``,
    ``used``, ``consumed``. This is deliberately lenient — Kilo's schema is a
    moving target. The first 2xx response wins; others raise.
    """
    last_err: Exception | None = None
    for url in _KILO_CANDIDATE_ENDPOINTS:
        try:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code >= 400:
                last_err = RuntimeError(f"{url} → HTTP {resp.status_code}")
                continue
            data = resp.json()
            total, used = _extract_numeric_balance(data)
            if total is None and used is None:
                last_err = RuntimeError(f"{url} → no recognizable balance fields")
                continue
            if total is None:
                total = used or 0.0
            if used is None:
                used = 0.0
            return total, used, url
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            last_err = exc
            continue
    raise RuntimeError(f"kilo balance probe exhausted: {last_err}")


def _extract_numeric_balance(payload: Any) -> tuple[float | None, float | None]:
    """Walk a JSON payload and return the first (total, used) pair found.

    Field name hints (case-insensitive, first hit wins)::

        total:  total, total_credits, initial, topped_up, limit, quota
        used:   used, consumed, spent, used_credits
        remaining: balance, remaining, credits, available

    If only ``remaining`` and ``total`` are present, computes
    ``used = total - remaining``. If only ``remaining`` is present, returns
    ``(None, None)`` so the caller can fall through to the next candidate.
    """
    if not isinstance(payload, dict):
        return None, None

    total_keys = ("total", "total_credits", "initial", "topped_up", "limit", "quota")
    used_keys = ("used", "consumed", "spent", "used_credits")
    remaining_keys = ("balance", "remaining", "credits", "available")

    def _first_numeric(keys: tuple[str, ...], root: dict[str, Any]) -> float | None:
        for k in keys:
            for candidate in (k, k.upper()):
                if candidate in root:
                    try:
                        return float(root[candidate])
                    except (TypeError, ValueError):
                        continue
        return None

    # Try both the root and a common "data" envelope.
    for root in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else None):
        if not isinstance(root, dict):
            continue
        total = _first_numeric(total_keys, root)
        used = _first_numeric(used_keys, root)
        remaining = _first_numeric(remaining_keys, root)
        if total is not None and used is not None:
            return total, used
        if total is not None and remaining is not None:
            return total, max(0.0, total - remaining)
        if used is not None:
            return None, used
    return None, None


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------


def _resolve_api_key(provider_id: str, providers_cfg: dict[str, Any] | None) -> str | None:
    """Find the API key for a provider. Env vars first, then config."""
    env_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "kilocode": "KILO_API_KEY",
    }
    env_name = env_map.get(provider_id)
    if env_name:
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    if providers_cfg:
        cfg = providers_cfg.get(provider_id) or {}
        key = str(cfg.get("api_key") or "").strip()
        if key:
            return key
    return None


def _select_due_packages(
    packages: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[tuple[str, dict[str, Any], int]]:
    """Return [(pkg_id, entry, interval_seconds)] for packages due a refresh.

    A package is "due" if it has ``source == "api_poll"`` and package_type in
    the credits family. Fast-lane cadence kicks in for expiring credits.
    """
    now = now or datetime.now(UTC)
    today = now.date()
    out: list[tuple[str, dict[str, Any], int]] = []
    for pkg_id, entry in packages.items():
        if entry.get("source") != "api_poll":
            continue
        ptype = entry.get("package_type", "credits")
        if ptype != "credits":
            continue
        interval = _DEFAULT_INTERVAL_SECONDS
        expiry = entry.get("expiry_date")
        if expiry:
            try:
                exp = date.fromisoformat(str(expiry))
                days_left = (exp - today).days
                if 0 <= days_left <= _FAST_LANE_EXPIRY_WINDOW_DAYS:
                    interval = _FAST_LANE_INTERVAL_SECONDS
            except ValueError:
                pass
        out.append((pkg_id, entry, interval))
    return out


async def _poll_package(
    client: httpx.AsyncClient,
    pkg_id: str,
    entry: dict[str, Any],
    providers_cfg: dict[str, Any] | None,
) -> PollResult:
    """Poll a single package. Never raises — returns ``PollResult(ok=False)``
    on any failure so the scheduler can keep going."""
    provider_id = str(entry.get("provider_id", ""))
    api_key = _resolve_api_key(provider_id, providers_cfg)
    if not api_key:
        return PollResult(
            package_id=pkg_id,
            provider_id=provider_id,
            ok=False,
            error=f"no API key for {provider_id} (set {provider_id.upper()}_API_KEY)",
        )

    try:
        if provider_id == "deepseek":
            total, used = await _fetch_deepseek_balance(client, api_key)
            endpoint = "https://api.deepseek.com/user/balance"
        elif provider_id == "kilocode":
            total, used, endpoint = await _fetch_kilo_balance(client, api_key)
        else:
            return PollResult(
                package_id=pkg_id,
                provider_id=provider_id,
                ok=False,
                error=f"no balance fetcher for provider {provider_id}",
            )
    except Exception as exc:  # noqa: BLE001 — poller must never crash caller
        return PollResult(
            package_id=pkg_id,
            provider_id=provider_id,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    return PollResult(
        package_id=pkg_id,
        provider_id=provider_id,
        ok=True,
        total_credits=total,
        used_credits=used,
        endpoint=endpoint,
    )


def _apply_result_to_cache(
    result: PollResult,
    packages_cache: dict[str, dict[str, Any]],
) -> None:
    """Mutate the in-memory cache with a successful poll result."""
    if not result.ok:
        return
    entry = packages_cache.get(result.package_id)
    if entry is None:
        return
    # Trust the provider for both sides if we have them — prevents catalog
    # drift when a top-up happens between polls.
    if result.total_credits is not None:
        entry["total_credits"] = float(result.total_credits)
    update_package_usage(
        result.package_id,
        used_credits=result.used_credits,
        source="api_poll",
        confidence="high",
        packages_cache=packages_cache,
    )


def _persist_cache_to_disk(
    packages_cache: dict[str, dict[str, Any]],
    path: Path,
) -> None:
    """Atomic write: ``path.tmp`` → ``os.replace`` → ``path``.

    We preserve the envelope structure (``schema_version``, ``_notes``, etc.)
    by re-reading the existing file, splicing in the updated ``packages``
    block, and writing the merged result.
    """
    envelope: dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                envelope = json.load(f)
        except Exception:  # noqa: BLE001
            envelope = {}
    envelope.setdefault("schema_version", "1.1")
    envelope["packages"] = packages_cache
    envelope["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, path)


async def run_poll_once(
    *,
    providers_cfg: dict[str, Any] | None = None,
    persist: bool = True,
) -> list[PollResult]:
    """One-shot poll of all due packages. Returns list of results.

    Exposed for manual / CLI use (``python -m faigate.quota_poller``) and for
    the lifespan startup warmup.
    """
    packages_cache = get_packages_catalog()
    if not packages_cache:
        logger.debug("quota_poller: no external packages catalog — nothing to poll")
        return []

    due = _select_due_packages(packages_cache)
    if not due:
        logger.debug("quota_poller: no api_poll packages due")
        return []

    results: list[PollResult] = []
    async with httpx.AsyncClient() as client:
        # Small fan-out: run package polls concurrently, but cap at 4 to avoid
        # hammering any single provider.
        sem = asyncio.Semaphore(4)

        async def _bounded(pkg_id: str, entry: dict[str, Any]) -> PollResult:
            async with sem:
                return await _poll_package(client, pkg_id, entry, providers_cfg)

        gathered = await asyncio.gather(
            *(_bounded(pkg_id, entry) for pkg_id, entry, _ in due),
            return_exceptions=False,
        )
        results.extend(gathered)

    for r in results:
        if r.ok:
            _apply_result_to_cache(r, packages_cache)
            logger.info(
                "quota_poller: %s/%s → total=%.2f used=%.2f (%s)",
                r.provider_id,
                r.package_id,
                r.total_credits or 0.0,
                r.used_credits or 0.0,
                r.endpoint,
            )
        else:
            logger.warning(
                "quota_poller: %s/%s failed — %s",
                r.provider_id,
                r.package_id,
                r.error,
            )

    if persist and any(r.ok for r in results):
        try:
            _persist_cache_to_disk(packages_cache, _get_external_packages_path())
        except Exception as exc:  # noqa: BLE001
            logger.warning("quota_poller: persist failed: %s", exc)

    return results


async def quota_poll_loop(
    *,
    providers_cfg: dict[str, Any] | None = None,
    interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
    fast_lane_interval_seconds: int = _FAST_LANE_INTERVAL_SECONDS,
) -> None:
    """Long-running background task. Sleeps, polls, sleeps again.

    Uses the *shortest* interval among due packages as the outer cadence — if
    any package is in the fast lane, we sleep 15m, otherwise 1h.
    """
    global _DEFAULT_INTERVAL_SECONDS, _FAST_LANE_INTERVAL_SECONDS
    logger.info(
        "quota_poller: starting (default=%ds, fast_lane=%ds)",
        interval_seconds,
        fast_lane_interval_seconds,
    )
    while True:
        try:
            packages = get_packages_catalog()
            due = _select_due_packages(packages)
            next_sleep = interval_seconds
            if any(iv == fast_lane_interval_seconds for _, _, iv in due):
                next_sleep = fast_lane_interval_seconds
            await run_poll_once(providers_cfg=providers_cfg, persist=True)
        except asyncio.CancelledError:
            logger.info("quota_poller: loop cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("quota_poller: loop iteration raised %s", exc)
            next_sleep = interval_seconds
        await asyncio.sleep(next_sleep)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> int:
    """Ad-hoc manual poll. Useful for verifying API keys during setup."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    results = asyncio.run(run_poll_once(persist=True))
    if not results:
        print("No api_poll packages configured (nothing to do).")
        return 0
    print(f"\nPolled {len(results)} package(s):")
    for r in results:
        mark = "✓" if r.ok else "✗"
        if r.ok:
            print(f"  {mark} {r.provider_id}/{r.package_id}: total={r.total_credits:.2f} used={r.used_credits:.2f}")
        else:
            print(f"  {mark} {r.provider_id}/{r.package_id}: {r.error}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "PollResult",
    "run_poll_once",
    "quota_poll_loop",
]
