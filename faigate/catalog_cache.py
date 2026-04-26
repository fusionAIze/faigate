"""Filesystem cache for synced provider catalogs.

Stores `catalog.v1.json` per tier (`public`, `private`) plus a sibling
`.etag` file. Writes are atomic (temp + rename). A best-effort lock file
guards concurrent writes from CLI + daemon.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("faigate.catalog_cache")

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "faigate" / "metadata"


@dataclass
class CachedCatalog:
    payload: dict[str, Any]
    etag: str | None
    written_at: float  # epoch seconds
    tier: str


@dataclass
class SyncState:
    tier: str
    last_attempt_at: float
    last_success_at: float | None
    last_status: str
    last_error: str
    success_count: int = 0
    failure_count: int = 0


class CatalogCache:
    """Per-tier filesystem cache. Tier name is e.g. 'public' or 'private'."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root else DEFAULT_CACHE_DIR

    def _tier_dir(self, tier: str) -> Path:
        return self._root / tier

    def _catalog_path(self, tier: str) -> Path:
        return self._tier_dir(tier) / "catalog.v1.json"

    def _etag_path(self, tier: str) -> Path:
        return self._tier_dir(tier) / "catalog.v1.json.etag"

    def _lock_path(self, tier: str) -> Path:
        return self._tier_dir(tier) / "catalog.v1.json.lock"

    def _state_path(self, tier: str) -> Path:
        return self._tier_dir(tier) / "sync-state.json"

    def load(self, tier: str) -> CachedCatalog | None:
        path = self._catalog_path(tier)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("cache load failed tier=%s err=%s", tier, exc)
            return None

        etag: str | None = None
        etag_path = self._etag_path(tier)
        if etag_path.exists():
            try:
                etag = etag_path.read_text(encoding="utf-8").strip() or None
            except OSError:
                etag = None

        return CachedCatalog(
            payload=payload,
            etag=etag,
            written_at=path.stat().st_mtime,
            tier=tier,
        )

    def save(
        self,
        tier: str,
        payload: dict[str, Any],
        etag: str | None,
    ) -> CachedCatalog:
        tier_dir = self._tier_dir(tier)
        tier_dir.mkdir(parents=True, exist_ok=True)

        catalog_path = self._catalog_path(tier)
        etag_path = self._etag_path(tier)

        with self._locked(tier):
            tmp_catalog = catalog_path.with_suffix(catalog_path.suffix + ".tmp")
            with open(tmp_catalog, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp_catalog, catalog_path)

            if etag:
                tmp_etag = etag_path.with_suffix(etag_path.suffix + ".tmp")
                tmp_etag.write_text(etag, encoding="utf-8")
                os.replace(tmp_etag, etag_path)
            elif etag_path.exists():
                etag_path.unlink()

        return CachedCatalog(
            payload=payload,
            etag=etag,
            written_at=catalog_path.stat().st_mtime,
            tier=tier,
        )

    def clear(self, tier: str) -> None:
        for path in (self._catalog_path(tier), self._etag_path(tier), self._state_path(tier)):
            if path.exists():
                path.unlink()

    def age_seconds(self, tier: str) -> float | None:
        path = self._catalog_path(tier)
        if not path.exists():
            return None
        return time.time() - path.stat().st_mtime

    def load_state(self, tier: str) -> SyncState | None:
        path = self._state_path(tier)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("sync state load failed tier=%s err=%s", tier, exc)
            return None
        return SyncState(
            tier=tier,
            last_attempt_at=float(data.get("last_attempt_at") or 0.0),
            last_success_at=(float(data["last_success_at"]) if data.get("last_success_at") not in (None, "") else None),
            last_status=str(data.get("last_status") or ""),
            last_error=str(data.get("last_error") or ""),
            success_count=int(data.get("success_count") or 0),
            failure_count=int(data.get("failure_count") or 0),
        )

    def save_state(
        self,
        tier: str,
        *,
        status: str,
        success: bool,
        error: str = "",
        when: float | None = None,
    ) -> SyncState:
        tier_dir = self._tier_dir(tier)
        tier_dir.mkdir(parents=True, exist_ok=True)
        previous = self.load_state(tier)
        now = float(when or time.time())
        state = SyncState(
            tier=tier,
            last_attempt_at=now,
            last_success_at=now if success else (previous.last_success_at if previous else None),
            last_status=status,
            last_error="" if success else error,
            success_count=(previous.success_count if previous else 0) + (1 if success else 0),
            failure_count=(previous.failure_count if previous else 0) + (0 if success else 1),
        )
        path = self._state_path(tier)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "tier": state.tier,
                    "last_attempt_at": state.last_attempt_at,
                    "last_success_at": state.last_success_at,
                    "last_status": state.last_status,
                    "last_error": state.last_error,
                    "success_count": state.success_count,
                    "failure_count": state.failure_count,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
        return state

    @contextmanager
    def _locked(self, tier: str) -> Iterator[None]:
        """Best-effort exclusive lock for CLI + daemon coordination."""
        lock_path = self._lock_path(tier)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import fcntl

            with open(lock_path, "w", encoding="utf-8") as lock_fd:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except ImportError:
            # Windows: skip locking, rely on atomic rename
            yield
        except OSError as exc:
            logger.debug(
                "cache lock unavailable tier=%s err=%s — proceeding unlocked",
                tier,
                exc,
            )
            yield
