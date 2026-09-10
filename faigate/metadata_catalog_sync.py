"""HTTPS sync for the curated fusionAIze provider catalog.

Distinct layer from `provider_catalog_refresh.py`. The refresher scrapes
vendor doc pages for model discovery; this module pulls the curated
catalog file (`providers/catalog.v1.json`) from a metadata repo over
HTTPS with conditional-GET ETag caching.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from enum import Enum
from importlib import resources
from typing import Any, Protocol

import httpx

logger = logging.getLogger("faigate.metadata_catalog_sync")

DEFAULT_TIMEOUT_SECONDS = 10.0

DEFAULT_MIN_ENTRIES = 10
DEFAULT_MAX_SHRINK_RATIO = 0.5


class SyncStatus(str, Enum):
    FRESH = "fresh"
    NOT_MODIFIED = "not_modified"
    AUTH_FAILED = "auth_failed"
    NOT_FOUND = "not_found"
    INVALID = "invalid"
    ERROR = "error"


class SyncError(Exception):
    """Raised on unrecoverable sync failures (network, parse, schema)."""


class BundledBaselineError(SyncError):
    """Raised when the bundled integrity baseline cannot be loaded.

    This is deliberately a hard error: if the guard cannot read its
    baseline it must fail closed, never silently accept an unverified
    (possibly truncated) catalog.
    """


@dataclass
class FetchResult:
    status: SyncStatus
    payload: dict[str, Any] | None
    etag: str | None
    http_status: int | None = None
    error: str = ""


class HttpFetcher(Protocol):
    """Low-level HTTP protocol — returns (status, headers, body) or raises."""

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, str], bytes]: ...


class HttpxFetcher:
    """Default HTTP fetcher backed by httpx."""

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, str], bytes]:
        timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            return response.status_code, dict(response.headers), response.content


def _redact(token: str | None) -> str:
    if not token:
        return "<none>"
    if len(token) < 12:
        return "<redacted>"
    return f"{token[:4]}…{token[-4:]}"


def _validate_payload_shape(payload: dict[str, Any]) -> None:
    """Cheap structural check. Full schema validation lives elsewhere."""
    schema_version = payload.get("schema_version", "")
    if not isinstance(schema_version, str) or not schema_version.startswith("fusionaize-provider-catalog/"):
        raise SyncError(f"unexpected schema_version: {schema_version!r}")
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        raise SyncError("payload missing 'providers' object")


def _load_bundled_baseline() -> dict[str, Any]:
    """Load the bundled catalog snapshot used as the integrity baseline.

    Only genuinely expected "asset missing or unreadable as JSON" conditions
    are translated into :class:`BundledBaselineError`. Unexpected failures
    (I/O errors, permission errors, programming mistakes) propagate unchanged
    so a broken baseline can never be mistaken for an absent one and silently
    disable the shrink guard.
    """
    try:
        catalog_resource = resources.files("faigate.assets.metadata").joinpath("catalog.v1.json")
        with catalog_resource.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        logger.error("bundled catalog baseline unavailable: %s", exc)
        raise BundledBaselineError(f"bundled catalog baseline unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        logger.error("bundled catalog baseline is not valid JSON: %s", exc)
        raise BundledBaselineError(f"bundled catalog baseline is not valid JSON: {exc}") from exc


def _count_catalog_entries(payload: dict[str, Any]) -> int:
    """Return the number of provider entries, ignoring top-level meta keys."""
    providers = payload.get("providers")
    return len(providers) if isinstance(providers, dict) else 0


def _validate_integrity(
    payload: dict[str, Any],
    *,
    baseline: dict[str, Any] | None,
    min_entries: int,
    max_shrink_ratio: float,
) -> None:
    """Reject a catalog that is too small or shrank too far from the baseline.

    ``baseline`` must be the bundled snapshot, never the last-fetched copy, so
    an already-accepted truncated sync cannot ratchet the next threshold down.
    """
    count = _count_catalog_entries(payload)
    if count < min_entries:
        raise SyncError(f"catalog entry count {count} below minimum {min_entries}")
    if baseline is None:
        return
    baseline_count = _count_catalog_entries(baseline)
    if baseline_count == 0:
        return
    # ceil rounds the retained floor up on purpose: for an odd baseline this
    # makes the effective threshold stricter than max_shrink_ratio suggests
    # (a 47-entry baseline needs 24 entries, i.e. ~51%, not 50%).
    min_retained = math.ceil(baseline_count * (1.0 - max_shrink_ratio))
    if count < min_retained:
        raise SyncError(f"catalog entry count {count} below {min_retained} (bundled baseline has {baseline_count})")


class MetadataCatalogSync:
    """Pull a curated catalog over HTTPS with ETag conditional-GET."""

    def __init__(self, *, fetcher: HttpFetcher | None = None) -> None:
        self._fetcher = fetcher or HttpxFetcher()

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        token: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        min_entries: int = DEFAULT_MIN_ENTRIES,
        max_shrink_ratio: float = DEFAULT_MAX_SHRINK_RATIO,
    ) -> FetchResult:
        """Fetch the catalog. Returns FetchResult; never raises for HTTP errors."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if etag:
            headers["If-None-Match"] = etag
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            status, response_headers, body = self._fetcher.fetch(
                url,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "catalog sync: network error url=%s token=%s err=%s",
                url,
                _redact(token),
                exc,
            )
            return FetchResult(
                status=SyncStatus.ERROR,
                payload=None,
                etag=None,
                error=f"network: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("catalog sync: unexpected error url=%s err=%s", url, exc)
            return FetchResult(
                status=SyncStatus.ERROR,
                payload=None,
                etag=None,
                error=f"unexpected: {exc}",
            )

        new_etag = response_headers.get("etag") or response_headers.get("ETag")

        if status == 304:
            return FetchResult(
                status=SyncStatus.NOT_MODIFIED,
                payload=None,
                etag=etag,
                http_status=status,
            )

        if status in (401, 403):
            logger.info(
                "catalog sync: auth failed url=%s status=%d token=%s",
                url,
                status,
                _redact(token),
            )
            return FetchResult(
                status=SyncStatus.AUTH_FAILED,
                payload=None,
                etag=None,
                http_status=status,
                error=f"http {status}",
            )

        if status == 404:
            return FetchResult(
                status=SyncStatus.NOT_FOUND,
                payload=None,
                etag=None,
                http_status=status,
                error="http 404",
            )

        if status >= 400:
            return FetchResult(
                status=SyncStatus.ERROR,
                payload=None,
                etag=None,
                http_status=status,
                error=f"http {status}",
            )

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            return FetchResult(
                status=SyncStatus.INVALID,
                payload=None,
                etag=None,
                http_status=status,
                error=f"json parse: {exc}",
            )

        if not isinstance(payload, dict):
            return FetchResult(
                status=SyncStatus.INVALID,
                payload=None,
                etag=None,
                http_status=status,
                error="payload is not a JSON object",
            )

        try:
            _validate_payload_shape(payload)
        except SyncError as exc:
            return FetchResult(
                status=SyncStatus.INVALID,
                payload=None,
                etag=None,
                http_status=status,
                error=str(exc),
            )

        try:
            _validate_integrity(
                payload,
                baseline=_load_bundled_baseline(),
                min_entries=min_entries,
                max_shrink_ratio=max_shrink_ratio,
            )
        except SyncError as exc:
            return FetchResult(
                status=SyncStatus.INVALID,
                payload=None,
                etag=None,
                http_status=status,
                error=str(exc),
            )

        return FetchResult(
            status=SyncStatus.FRESH,
            payload=payload,
            etag=new_etag,
            http_status=status,
        )
