"""Resolution chain for the curated provider catalog.

Tries tiers in order:
    1. Private remote (if FAIGATE_METADATA_TOKEN is set) → ETag-cached
    2. Public  remote                                   → ETag-cached
    3. Bundled snapshot shipped in faigate/assets/metadata/

Each tier returns ``ResolvedCatalog(payload, source)``. Downstream code
inspects ``source`` for telemetry but otherwise treats them identically.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from .catalog_cache import CatalogCache
from .metadata_catalog_sync import (
    DEFAULT_TIMEOUT_SECONDS,
    MetadataCatalogSync,
    SyncStatus,
)

logger = logging.getLogger("faigate.catalog_resolver")

DEFAULT_PUBLIC_URL = (
    "https://raw.githubusercontent.com/fusionAIze/fusionaize-metadata-public/main/providers/catalog.v1.json"
)
DEFAULT_PRIVATE_URL = (
    "https://raw.githubusercontent.com/fusionAIze/fusionaize-metadata/master/providers/catalog.v1.json"
)
DEFAULT_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # 24h

ENV_TOKEN = "FAIGATE_METADATA_TOKEN"
ENV_PUBLIC_URL = "FAIGATE_METADATA_PUBLIC_URL"
ENV_PRIVATE_URL = "FAIGATE_METADATA_PRIVATE_URL"
ENV_REFRESH_INTERVAL = "FAIGATE_METADATA_REFRESH_INTERVAL_SECONDS"

_SUCCESS_STATUSES = {SyncStatus.FRESH, SyncStatus.NOT_MODIFIED}


@dataclass
class ResolverConfig:
    public_url: str = DEFAULT_PUBLIC_URL
    private_url: str = DEFAULT_PRIVATE_URL
    token: str | None = None
    refresh_interval_seconds: float = DEFAULT_REFRESH_INTERVAL_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> ResolverConfig:
        token = os.environ.get(ENV_TOKEN, "").strip() or None
        public_url = os.environ.get(ENV_PUBLIC_URL, "").strip() or DEFAULT_PUBLIC_URL
        private_url = os.environ.get(ENV_PRIVATE_URL, "").strip() or DEFAULT_PRIVATE_URL
        refresh = os.environ.get(ENV_REFRESH_INTERVAL, "").strip()
        try:
            refresh_seconds = float(refresh) if refresh else DEFAULT_REFRESH_INTERVAL_SECONDS
        except ValueError:
            refresh_seconds = DEFAULT_REFRESH_INTERVAL_SECONDS
        return cls(
            public_url=public_url,
            private_url=private_url,
            token=token,
            refresh_interval_seconds=refresh_seconds,
        )


@dataclass
class ResolvedCatalog:
    payload: dict[str, Any]
    source: str  # "private", "public", "private-cache", "public-cache", "bundled"
    etag: str | None = None
    fetched_at: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)


def _load_bundled_snapshot() -> dict[str, Any] | None:
    """Load the snapshot shipped inside the wheel, if present."""
    try:
        # Python 3.9+ files() API
        catalog_resource = resources.files("faigate.assets.metadata").joinpath("catalog.v1.json")
        with catalog_resource.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("bundled snapshot load failed: %s", exc)
        return None


class CatalogResolver:
    """Run the private→public→bundled chain with cache + sync."""

    def __init__(
        self,
        *,
        config: ResolverConfig | None = None,
        cache: CatalogCache | None = None,
        sync: MetadataCatalogSync | None = None,
    ) -> None:
        self._config = config or ResolverConfig.from_env()
        self._cache = cache or CatalogCache()
        self._sync = sync or MetadataCatalogSync()

    @property
    def config(self) -> ResolverConfig:
        return self._config

    def resolve(self, *, force_refresh: bool = False) -> ResolvedCatalog:
        """Return the best-available catalog right now."""
        notes: list[str] = []

        # Tier 1: private (only if token configured)
        if self._config.token:
            result = self._try_remote(
                tier="private",
                url=self._config.private_url,
                token=self._config.token,
                force_refresh=force_refresh,
                notes=notes,
            )
            if result is not None:
                return result

        # Tier 2: public (anonymous)
        result = self._try_remote(
            tier="public",
            url=self._config.public_url,
            token=None,
            force_refresh=force_refresh,
            notes=notes,
        )
        if result is not None:
            return result

        # Tier 3: bundled snapshot
        bundled = _load_bundled_snapshot()
        if bundled is not None:
            notes.append("falling back to bundled snapshot")
            logger.info("catalog resolve: using bundled snapshot")
            return ResolvedCatalog(
                payload=bundled,
                source="bundled",
                etag=None,
                notes=notes,
            )

        # Total failure: empty catalog
        notes.append("no catalog source available")
        logger.warning("catalog resolve: no source available — empty catalog")
        return ResolvedCatalog(
            payload={"providers": {}},
            source="empty",
            etag=None,
            notes=notes,
        )

    def _try_remote(
        self,
        *,
        tier: str,
        url: str,
        token: str | None,
        force_refresh: bool,
        notes: list[str],
    ) -> ResolvedCatalog | None:
        cached = self._cache.load(tier)
        ttl = self._config.refresh_interval_seconds

        # Use cache without network roundtrip if it's fresh enough
        if cached is not None and not force_refresh and (time.time() - cached.written_at) < ttl:
            return ResolvedCatalog(
                payload=cached.payload,
                source=f"{tier}-cache",
                etag=cached.etag,
                fetched_at=cached.written_at,
                notes=notes,
            )

        result = self._sync.fetch(
            url,
            etag=cached.etag if cached else None,
            token=token,
            timeout_seconds=self._config.timeout_seconds,
        )
        self._cache.save_state(
            tier,
            status=result.status.value,
            success=result.status in _SUCCESS_STATUSES,
            error=result.error,
        )

        if result.status == SyncStatus.FRESH and result.payload is not None:
            saved = self._cache.save(tier, result.payload, result.etag)
            return ResolvedCatalog(
                payload=saved.payload,
                source=tier,
                etag=saved.etag,
                fetched_at=saved.written_at,
                notes=notes,
            )

        if result.status == SyncStatus.NOT_MODIFIED and cached is not None:
            # Touch mtime so the TTL math counts this as a fresh check
            self._cache.save(tier, cached.payload, cached.etag)
            return ResolvedCatalog(
                payload=cached.payload,
                source=f"{tier}-cache",
                etag=cached.etag,
                fetched_at=time.time(),
                notes=notes,
            )

        # Remote unhealthy but we have stale cache — use it
        if cached is not None:
            notes.append(f"{tier}: remote returned {result.status.value}; using stale cache")
            logger.info(
                "catalog resolve: %s remote %s — falling back to cached",
                tier,
                result.status.value,
            )
            return ResolvedCatalog(
                payload=cached.payload,
                source=f"{tier}-cache",
                etag=cached.etag,
                fetched_at=cached.written_at,
                notes=notes,
            )

        notes.append(f"{tier}: {result.status.value} (no cache)")
        return None

    def status(self) -> dict[str, Any]:
        """Surface cache state for `faigate models status` and dashboards."""
        out: dict[str, Any] = {"tiers": {}}
        for tier in ("private", "public"):
            cached = self._cache.load(tier)
            if cached is None:
                out["tiers"][tier] = {"present": False}
                continue
            out["tiers"][tier] = {
                "present": True,
                "etag": cached.etag,
                "written_at": cached.written_at,
                "age_seconds": time.time() - cached.written_at,
                "providers_count": len(cached.payload.get("providers", {})),
            }
            state = self._cache.load_state(tier)
            if state is not None:
                out["tiers"][tier]["sync"] = {
                    "last_attempt_at": state.last_attempt_at,
                    "last_success_at": state.last_success_at,
                    "last_status": state.last_status,
                    "last_error": state.last_error,
                    "success_count": state.success_count,
                    "failure_count": state.failure_count,
                    "seconds_since_success": (time.time() - state.last_success_at if state.last_success_at else None),
                }
        bundled = _load_bundled_snapshot()
        out["bundled_present"] = bundled is not None
        if bundled is not None:
            out["bundled_providers_count"] = len(bundled.get("providers", {}))
        return out
