"""SQLite-backed storage for provider catalog snapshots and availability overlays."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("faigate.provider_catalog_store")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS provider_sources (
    provider_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    refresh_interval_seconds INTEGER DEFAULT 21600,
    docs_index_url TEXT DEFAULT '',
    models_url TEXT DEFAULT '',
    pricing_url TEXT DEFAULT '',
    auth_url TEXT DEFAULT '',
    status_url TEXT DEFAULT '',
    billing_notes TEXT DEFAULT '',
    endpoints_json TEXT DEFAULT '[]',
    availability_json TEXT DEFAULT '{}',
    last_checked_at REAL DEFAULT 0,
    last_success_at REAL DEFAULT 0,
    last_error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS provider_model_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    snapshot_at REAL NOT NULL,
    model_id TEXT NOT NULL,
    model_name TEXT DEFAULT '',
    input_cost REAL,
    output_cost REAL,
    context_length INTEGER,
    is_free INTEGER DEFAULT 0,
    raw_source_hash TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_provider_model_snapshots_provider
    ON provider_model_snapshots(provider_id, source_kind, snapshot_at);

CREATE TABLE IF NOT EXISTS provider_availability_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    route_name TEXT NOT NULL,
    checked_at REAL NOT NULL,
    model_id TEXT DEFAULT '',
    available_for_key INTEGER DEFAULT 0,
    request_ready INTEGER DEFAULT 0,
    verified_via TEXT DEFAULT '',
    last_issue_type TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_provider_availability_provider
    ON provider_availability_snapshots(provider_id, route_name, checked_at);

CREATE TABLE IF NOT EXISTS provider_account_profiles (
    provider_id TEXT PRIMARY KEY,
    billing_mode TEXT DEFAULT '',
    subscription_name TEXT DEFAULT '',
    quota_window TEXT DEFAULT '',
    quota_limit REAL,
    quota_remaining REAL,
    renewal_at REAL,
    notes TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    detected_at REAL NOT NULL,
    source_kind TEXT NOT NULL,
    change_type TEXT NOT NULL,
    severity TEXT DEFAULT 'notice',
    model_id TEXT DEFAULT '',
    field_name TEXT DEFAULT '',
    old_value TEXT DEFAULT '',
    new_value TEXT DEFAULT '',
    message TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_provider_change_events_provider
    ON provider_change_events(provider_id, detected_at);
"""


class ProviderCatalogStore:
    """Persistence layer for global provider catalog snapshots and local overlays."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def init(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def upsert_source(self, source: dict[str, Any]) -> None:
        if not self._conn:
            return
        endpoints = list(source.get("endpoints") or [])
        availability = dict(source.get("availability") or {})
        docs_index_url = ""
        models_url = ""
        pricing_url = ""
        auth_url = ""
        status_url = ""
        for endpoint in endpoints:
            kind = str(endpoint.get("kind") or "")
            url = str(endpoint.get("url") or "")
            if kind == "docs-index":
                docs_index_url = url
            elif kind == "models":
                models_url = url
            elif kind == "pricing":
                pricing_url = url
            elif kind == "auth":
                auth_url = url
            elif kind == "status":
                status_url = url
        self._conn.execute(
            """
            INSERT INTO provider_sources(
                provider_id, display_name, refresh_interval_seconds,
                docs_index_url, models_url, pricing_url, auth_url, status_url,
                billing_notes, endpoints_json, availability_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                display_name=excluded.display_name,
                refresh_interval_seconds=excluded.refresh_interval_seconds,
                docs_index_url=excluded.docs_index_url,
                models_url=excluded.models_url,
                pricing_url=excluded.pricing_url,
                auth_url=excluded.auth_url,
                status_url=excluded.status_url,
                billing_notes=excluded.billing_notes,
                endpoints_json=excluded.endpoints_json,
                availability_json=excluded.availability_json
            """,
            (
                str(source.get("provider_id") or ""),
                str(source.get("display_name") or ""),
                int(source.get("refresh_interval_seconds") or 21600),
                docs_index_url,
                models_url,
                pricing_url,
                auth_url,
                status_url,
                str(source.get("billing_notes") or ""),
                json.dumps(endpoints, sort_keys=True),
                json.dumps(availability, sort_keys=True),
            ),
        )
        self._conn.commit()

    def mark_source_check(self, provider_id: str, *, success: bool, error: str = "") -> None:
        if not self._conn:
            return
        now = time.time()
        if success:
            self._conn.execute(
                """
                UPDATE provider_sources
                SET last_checked_at=?, last_success_at=?, last_error=''
                WHERE provider_id=?
                """,
                (now, now, provider_id),
            )
        else:
            self._conn.execute(
                """
                UPDATE provider_sources
                SET last_checked_at=?, last_error=?
                WHERE provider_id=?
                """,
                (now, error, provider_id),
            )
        self._conn.commit()

    def replace_model_snapshot(
        self,
        provider_id: str,
        source_kind: str,
        models: list[dict[str, Any]],
        *,
        snapshot_at: float | None = None,
    ) -> None:
        if not self._conn:
            return
        ts = float(snapshot_at or time.time())
        self._conn.execute(
            (
                "DELETE FROM provider_model_snapshots "
                "WHERE provider_id=? AND source_kind=? AND snapshot_at=?"
            ),
            (provider_id, source_kind, ts),
        )
        for model in models:
            self._conn.execute(
                """
                INSERT INTO provider_model_snapshots(
                    provider_id, source_kind, snapshot_at, model_id, model_name,
                    input_cost, output_cost, context_length, is_free, raw_source_hash, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider_id,
                    source_kind,
                    ts,
                    str(model.get("model_id") or ""),
                    str(model.get("model_name") or ""),
                    model.get("input_cost"),
                    model.get("output_cost"),
                    model.get("context_length"),
                    1 if bool(model.get("is_free")) else 0,
                    str(model.get("raw_source_hash") or ""),
                    json.dumps(dict(model.get("metadata") or {}), sort_keys=True),
                ),
            )
        self._conn.commit()

    def get_latest_models(self, provider_id: str, source_kind: str) -> list[dict[str, Any]]:
        if not self._conn:
            return []
        row = self._conn.execute(
            """
            SELECT MAX(snapshot_at) FROM provider_model_snapshots
            WHERE provider_id=? AND source_kind=?
            """,
            (provider_id, source_kind),
        ).fetchone()
        latest = row[0] if row and row[0] is not None else None
        if latest is None:
            return []
        cur = self._conn.execute(
            """
            SELECT provider_id, source_kind, snapshot_at, model_id, model_name,
                input_cost, output_cost, context_length, is_free, raw_source_hash, metadata_json
            FROM provider_model_snapshots
            WHERE provider_id=? AND source_kind=? AND snapshot_at=?
            ORDER BY model_id
            """,
            (provider_id, source_kind, latest),
        )
        cols = [item[0] for item in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for row in rows:
            row["metadata"] = json.loads(str(row.pop("metadata_json") or "{}"))
        return rows

    def record_availability_snapshot(
        self,
        provider_id: str,
        route_name: str,
        *,
        model_id: str = "",
        available_for_key: bool = False,
        request_ready: bool = False,
        verified_via: str = "",
        last_issue_type: str = "",
        metadata: dict[str, Any] | None = None,
        checked_at: float | None = None,
    ) -> None:
        if not self._conn:
            return
        self._conn.execute(
            """
            INSERT INTO provider_availability_snapshots(
                provider_id, route_name, checked_at, model_id,
                available_for_key, request_ready, verified_via, last_issue_type, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                route_name,
                float(checked_at or time.time()),
                model_id,
                1 if available_for_key else 0,
                1 if request_ready else 0,
                verified_via,
                last_issue_type,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        self._conn.commit()

    def upsert_account_profile(
        self,
        provider_id: str,
        *,
        billing_mode: str = "",
        subscription_name: str = "",
        quota_window: str = "",
        quota_limit: float | None = None,
        quota_remaining: float | None = None,
        renewal_at: float | None = None,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._conn:
            return
        self._conn.execute(
            """
            INSERT INTO provider_account_profiles(
                provider_id, billing_mode, subscription_name, quota_window,
                quota_limit, quota_remaining, renewal_at, notes, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                billing_mode=excluded.billing_mode,
                subscription_name=excluded.subscription_name,
                quota_window=excluded.quota_window,
                quota_limit=excluded.quota_limit,
                quota_remaining=excluded.quota_remaining,
                renewal_at=excluded.renewal_at,
                notes=excluded.notes,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                provider_id,
                billing_mode,
                subscription_name,
                quota_window,
                quota_limit,
                quota_remaining,
                renewal_at,
                notes,
                json.dumps(metadata or {}, sort_keys=True),
                time.time(),
            ),
        )
        self._conn.commit()

    def get_account_profile(self, provider_id: str) -> dict[str, Any]:
        if not self._conn:
            return {}
        cur = self._conn.execute(
            """
            SELECT provider_id, billing_mode, subscription_name, quota_window,
                quota_limit, quota_remaining, renewal_at, notes, metadata_json, updated_at
            FROM provider_account_profiles WHERE provider_id=?
            """,
            (provider_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        cols = [item[0] for item in cur.description]
        data = dict(zip(cols, row))
        data["metadata"] = json.loads(str(data.pop("metadata_json") or "{}"))
        return data

    def record_change_events(self, events: list[dict[str, Any]]) -> None:
        if not self._conn or not events:
            return
        for event in events:
            self._conn.execute(
                """
                INSERT INTO provider_change_events(
                    provider_id, detected_at, source_kind, change_type, severity,
                    model_id, field_name, old_value, new_value, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.get("provider_id") or ""),
                    float(event.get("detected_at") or time.time()),
                    str(event.get("source_kind") or ""),
                    str(event.get("change_type") or ""),
                    str(event.get("severity") or "notice"),
                    str(event.get("model_id") or ""),
                    str(event.get("field_name") or ""),
                    str(event.get("old_value") or ""),
                    str(event.get("new_value") or ""),
                    str(event.get("message") or ""),
                ),
            )
        self._conn.commit()

    def get_recent_change_events(
        self,
        *,
        provider_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not self._conn:
            return []
        params: list[Any] = []
        where_sql = ""
        if provider_id:
            where_sql = " WHERE provider_id=?"
            params.append(provider_id)
        cur = self._conn.execute(
            f"""
            SELECT provider_id, detected_at, source_kind, change_type, severity,
                model_id, field_name, old_value, new_value, message
            FROM provider_change_events{where_sql}
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        cols = [item[0] for item in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def list_sources(self) -> list[dict[str, Any]]:
        if not self._conn:
            return []
        cur = self._conn.execute(
            """
            SELECT provider_id, display_name, refresh_interval_seconds,
                docs_index_url, models_url, pricing_url, auth_url, status_url,
                billing_notes, endpoints_json, availability_json,
                last_checked_at, last_success_at, last_error
            FROM provider_sources
            ORDER BY provider_id
            """
        )
        cols = [item[0] for item in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for row in rows:
            row["endpoints"] = json.loads(str(row.pop("endpoints_json") or "[]"))
            row["availability"] = json.loads(str(row.pop("availability_json") or "{}"))
        return rows
