"""Metrics store with cost tracking, time-series queries, and aggregations."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("faigate.metrics")


def calc_cost(
    prompt_tokens: int,
    completion_tokens: int,
    pricing: dict,
    cache_hit: int = 0,
    cache_miss: int = 0,
) -> float:
    """Calculate USD cost. If cache_hit/miss provided, use cache pricing."""
    out = pricing.get("output", 0)
    if cache_hit or cache_miss:
        # Cache-aware pricing: hit tokens at cache_read rate, miss at input rate
        cache_rate = pricing.get("cache_read", pricing.get("input", 0))
        miss_rate = pricing.get("input", 0)
        input_cost = (cache_hit * cache_rate + cache_miss * miss_rate) / 1_000_000
    else:
        input_cost = (prompt_tokens * pricing.get("input", 0)) / 1_000_000
    return input_cost + (completion_tokens * out) / 1_000_000


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL    NOT NULL,
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    layer       TEXT    NOT NULL,
    rule_name   TEXT    NOT NULL,
    prompt_tok  INTEGER DEFAULT 0,
    compl_tok   INTEGER DEFAULT 0,
    cache_hit   INTEGER DEFAULT 0,
    cache_miss  INTEGER DEFAULT 0,
    cost_usd    REAL    DEFAULT 0,
    latency_ms  REAL    DEFAULT 0,
    success     INTEGER DEFAULT 1,
    error       TEXT    DEFAULT '',
    requested_model TEXT DEFAULT 'auto',
    modality        TEXT DEFAULT 'chat',
    client_profile  TEXT DEFAULT 'generic',
    client_tag      TEXT DEFAULT '',
    decision_reason TEXT DEFAULT '',
    confidence      REAL DEFAULT 0,
    canonical_model TEXT DEFAULT '',
    lane_family     TEXT DEFAULT '',
    route_type      TEXT DEFAULT '',
    lane_cluster    TEXT DEFAULT '',
    selection_path  TEXT DEFAULT '',
    runtime_window_state TEXT DEFAULT '',
    recovered_recently INTEGER DEFAULT 0,
    last_recovered_issue_type TEXT DEFAULT '',
    decision_details TEXT DEFAULT '{}',
    attempt_order   TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_req_ts       ON requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_req_provider ON requests(provider);
CREATE INDEX IF NOT EXISTS idx_req_layer    ON requests(layer);

CREATE TABLE IF NOT EXISTS operator_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          REAL    NOT NULL,
    event_type         TEXT    NOT NULL,
    action             TEXT    NOT NULL,
    client_tag         TEXT    DEFAULT '',
    status             TEXT    DEFAULT '',
    update_type        TEXT    DEFAULT '',
    target_version     TEXT    DEFAULT '',
    eligible           INTEGER DEFAULT 0,
    recommended_action TEXT    DEFAULT '',
    detail             TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_op_ts        ON operator_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_op_action    ON operator_events(action);
CREATE INDEX IF NOT EXISTS idx_op_status    ON operator_events(status);
"""

_OPTIONAL_COLUMNS: dict[str, str] = {
    "requested_model": "TEXT DEFAULT 'auto'",
    "modality": "TEXT DEFAULT 'chat'",
    "client_profile": "TEXT DEFAULT 'generic'",
    "client_tag": "TEXT DEFAULT ''",
    "decision_reason": "TEXT DEFAULT ''",
    "confidence": "REAL DEFAULT 0",
    "canonical_model": "TEXT DEFAULT ''",
    "lane_family": "TEXT DEFAULT ''",
    "route_type": "TEXT DEFAULT ''",
    "lane_cluster": "TEXT DEFAULT ''",
    "selection_path": "TEXT DEFAULT ''",
    "runtime_window_state": "TEXT DEFAULT ''",
    "recovered_recently": "INTEGER DEFAULT 0",
    "last_recovered_issue_type": "TEXT DEFAULT ''",
    "decision_details": "TEXT DEFAULT '{}'",
    "attempt_order": "TEXT DEFAULT '[]'",
    "route_summary": "TEXT DEFAULT '{}'",
}


class MetricsStore:
    """Synchronous SQLite store with cost tracking."""

    def __init__(self, db_path: str = "/var/lib/faigate/faigate.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> str:
        return self._db_path

    def init(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._ensure_optional_columns()
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_req_profile ON requests(client_profile)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_req_client ON requests(client_tag)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_req_modality ON requests(modality)")
        self._conn.commit()
        logger.info("Metrics DB ready: %s", self._db_path)

    def _ensure_optional_columns(self) -> None:
        """Add newer columns to an existing metrics DB without destroying data."""
        if not self._conn:
            return

        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(requests)").fetchall()}
        for column_name, column_sql in _OPTIONAL_COLUMNS.items():
            if column_name in existing:
                continue
            self._conn.execute(f"ALTER TABLE requests ADD COLUMN {column_name} {column_sql}")

    def log_request(
        self,
        provider: str,
        model: str,
        layer: str,
        rule_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: int = 0,
        cache_miss: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        success: bool = True,
        error: str = "",
        requested_model: str = "auto",
        modality: str = "chat",
        client_profile: str = "generic",
        client_tag: str = "",
        decision_reason: str = "",
        confidence: float = 0.0,
        canonical_model: str = "",
        lane_family: str = "",
        route_type: str = "",
        lane_cluster: str = "",
        selection_path: str = "",
        runtime_window_state: str = "",
        recovered_recently: bool = False,
        last_recovered_issue_type: str = "",
        decision_details: dict[str, Any] | None = None,
        attempt_order: list[str] | None = None,
        route_summary: dict[str, Any] | None = None,
    ) -> int | None:
        if not self._conn:
            return None
        try:
            cur = self._conn.execute(
                """INSERT INTO requests
                   (timestamp,provider,model,layer,rule_name,
                   prompt_tok,compl_tok,cache_hit,cache_miss,
                   cost_usd,latency_ms,success,error,
                    requested_model,modality,client_profile,client_tag,
                    decision_reason,confidence,canonical_model,lane_family,route_type,lane_cluster,
                    selection_path,runtime_window_state,recovered_recently,last_recovered_issue_type,
                    decision_details,attempt_order,route_summary)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    time.time(),
                    provider,
                    model,
                    layer,
                    rule_name,
                    prompt_tokens,
                    completion_tokens,
                    cache_hit,
                    cache_miss,
                    cost_usd,
                    latency_ms,
                    1 if success else 0,
                    error,
                    requested_model,
                    modality,
                    client_profile,
                    client_tag,
                    decision_reason,
                    confidence,
                    canonical_model,
                    lane_family,
                    route_type,
                    lane_cluster,
                    selection_path,
                    runtime_window_state,
                    1 if recovered_recently else 0,
                    last_recovered_issue_type,
                    json.dumps(decision_details or {}, sort_keys=True),
                    json.dumps(attempt_order or []),
                    json.dumps(route_summary or {}, sort_keys=True),
                ),
            )
            self._conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.warning("Metrics write failed: %s", e)
            return None

    def log_operator_event(
        self,
        *,
        event_type: str,
        action: str,
        client_tag: str = "",
        status: str = "",
        update_type: str = "",
        target_version: str = "",
        eligible: bool = False,
        recommended_action: str = "",
        detail: str = "",
    ) -> None:
        """Persist one operator event such as an update check or apply attempt."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                """INSERT INTO operator_events
                   (timestamp,event_type,action,client_tag,status,update_type,
                    target_version,eligible,recommended_action,detail)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    time.time(),
                    event_type,
                    action,
                    client_tag,
                    status,
                    update_type,
                    target_version,
                    1 if eligible else 0,
                    recommended_action,
                    detail,
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.warning("Operator metrics write failed: %s", e)

    def get_provider_summary(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT provider,
                COUNT(*)                                        AS requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)     AS failures,
                SUM(prompt_tok)                                 AS prompt_tokens,
                SUM(compl_tok)                                  AS compl_tokens,
                SUM(prompt_tok+compl_tok)                       AS total_tokens,
                SUM(cache_hit)                                  AS cache_hit_tokens,
                SUM(cache_miss)                                 AS cache_miss_tokens,
                ROUND(CASE WHEN SUM(cache_hit+cache_miss)>0
                    THEN SUM(cache_hit)*100.0/SUM(cache_hit+cache_miss)
                    ELSE 0 END, 1)                              AS cache_hit_pct,
                ROUND(SUM(cost_usd),6)                          AS cost_usd,
                ROUND(AVG(latency_ms),1)                        AS avg_latency_ms,
                MAX(canonical_model)                            AS canonical_model,
                MAX(lane_family)                                AS lane_family,
                MAX(route_type)                                 AS route_type,
                MAX(lane_cluster)                               AS lane_cluster
            FROM requests{where_sql} GROUP BY provider ORDER BY requests DESC
        """,
            params,
        )

    def get_routing_breakdown(self, **filters: Any) -> list[dict]:
        filters = {
            **filters,
            "success": 1 if filters.get("success") is None else filters["success"],
        }
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT layer, rule_name, provider,
                canonical_model, lane_family, route_type, lane_cluster, selection_path,
                runtime_window_state, recovered_recently, last_recovered_issue_type,
                COUNT(*)                  AS requests,
                ROUND(SUM(cost_usd),6)    AS cost_usd,
                ROUND(AVG(latency_ms),1)  AS avg_latency_ms
            FROM requests{where_sql}
            GROUP BY layer, rule_name, provider,
                canonical_model, lane_family, route_type, lane_cluster, selection_path,
                runtime_window_state, recovered_recently, last_recovered_issue_type
            ORDER BY requests DESC
        """,
            params,
        )

    def get_lane_family_breakdown(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT lane_family,
                COUNT(*) AS requests,
                COUNT(DISTINCT provider) AS providers,
                ROUND(SUM(cost_usd),6) AS cost_usd,
                SUM(
                    CASE WHEN runtime_window_state='cooldown' THEN 1 ELSE 0 END
                ) AS cooldown_requests,
                SUM(
                    CASE WHEN runtime_window_state='degraded' THEN 1 ELSE 0 END
                ) AS degraded_requests,
                SUM(CASE WHEN recovered_recently=1 THEN 1 ELSE 0 END) AS recovered_requests,
                GROUP_CONCAT(DISTINCT selection_path) AS selection_paths
            FROM requests{where_sql}
            GROUP BY lane_family
            ORDER BY requests DESC, providers DESC, cost_usd DESC
        """,
            params,
        )

    def get_selection_path_breakdown(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT selection_path,
                lane_family,
                runtime_window_state,
                recovered_recently,
                COUNT(*) AS requests,
                ROUND(SUM(cost_usd),6) AS cost_usd,
                ROUND(AVG(latency_ms),1) AS avg_latency_ms
            FROM requests{where_sql}
            GROUP BY selection_path, lane_family, runtime_window_state, recovered_recently
            ORDER BY requests DESC, cost_usd DESC
        """,
            params,
        )

    def get_client_breakdown(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT modality,
                client_profile,
                client_tag,
                provider,
                layer,
                COUNT(*)                 AS requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                ROUND(CASE WHEN COUNT(*)>0
                    THEN (COUNT(*) - SUM(CASE WHEN success=0 THEN 1 ELSE 0 END))*100.0/COUNT(*)
                    ELSE 0 END, 1)       AS success_pct,
                SUM(prompt_tok)          AS prompt_tokens,
                SUM(compl_tok)           AS compl_tokens,
                SUM(prompt_tok+compl_tok) AS total_tokens,
                ROUND(SUM(cost_usd),6)   AS cost_usd,
                ROUND(CASE WHEN COUNT(*)>0 THEN SUM(cost_usd)/COUNT(*) ELSE 0 END, 6)
                    AS cost_per_request_usd,
                ROUND(AVG(latency_ms),1) AS avg_latency_ms
            FROM requests{where_sql}
            GROUP BY modality, client_profile, client_tag, provider, layer
            ORDER BY requests DESC, modality ASC, client_profile ASC, client_tag ASC
        """,
            params,
        )

    def get_client_totals(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT client_profile,
                client_tag,
                COUNT(*)                 AS requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                ROUND(CASE WHEN COUNT(*)>0
                    THEN (COUNT(*) - SUM(CASE WHEN success=0 THEN 1 ELSE 0 END))*100.0/COUNT(*)
                    ELSE 0 END, 1)       AS success_pct,
                SUM(prompt_tok)          AS prompt_tokens,
                SUM(compl_tok)           AS compl_tokens,
                SUM(prompt_tok+compl_tok) AS total_tokens,
                ROUND(SUM(cost_usd),6)   AS cost_usd,
                ROUND(CASE WHEN COUNT(*)>0 THEN SUM(cost_usd)/COUNT(*) ELSE 0 END, 6)
                    AS cost_per_request_usd,
                ROUND(AVG(latency_ms),1) AS avg_latency_ms,
                GROUP_CONCAT(DISTINCT modality) AS modalities,
                GROUP_CONCAT(DISTINCT provider) AS providers
            FROM requests{where_sql}
            GROUP BY client_profile, client_tag
            ORDER BY requests DESC, client_profile ASC, client_tag ASC
        """,
            params,
        )

    def get_modality_breakdown(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        return self._q(
            f"""
            SELECT modality,
                provider,
                layer,
                COUNT(*)                 AS requests,
                ROUND(SUM(cost_usd),6)   AS cost_usd,
                ROUND(AVG(latency_ms),1) AS avg_latency_ms
            FROM requests{where_sql}
            GROUP BY modality, provider, layer
            ORDER BY requests DESC, modality ASC, provider ASC
        """,
            params,
        )

    def get_hourly_series(self, hours: int = 24) -> list[dict]:
        cutoff = time.time() - hours * 3600
        return self._q(
            """
            SELECT CAST((timestamp-?)/3600 AS INTEGER) AS hour_offset,
                COUNT(*)                    AS requests,
                ROUND(SUM(cost_usd),6)      AS cost_usd,
                SUM(prompt_tok+compl_tok)    AS tokens
            FROM requests WHERE timestamp>=?
            GROUP BY hour_offset ORDER BY hour_offset
        """,
            (cutoff, cutoff),
        )

    def get_daily_totals(self, days: int = 30) -> list[dict]:
        cutoff = time.time() - days * 86400
        return self._q(
            """
            SELECT DATE(timestamp,'unixepoch','localtime') AS day,
                COUNT(*)                                    AS requests,
                ROUND(SUM(cost_usd),6)                      AS cost_usd,
                SUM(prompt_tok+compl_tok)                    AS tokens,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)  AS failures
            FROM requests WHERE timestamp>=?
            GROUP BY day ORDER BY day
        """,
            (cutoff,),
        )

    def get_operator_events(self, limit: int = 50, **filters: Any) -> list[dict]:
        where_sql, params = self._build_operator_where_clause(filters)
        return self._q(
            f"SELECT * FROM operator_events{where_sql} ORDER BY timestamp DESC LIMIT ?",
            (*params, limit),
        )

    def get_operator_breakdown(self, **filters: Any) -> list[dict]:
        where_sql, params = self._build_operator_where_clause(filters)
        return self._q(
            f"""
            SELECT event_type,
                action,
                client_tag,
                status,
                update_type,
                eligible,
                COUNT(*) AS events
            FROM operator_events{where_sql}
            GROUP BY event_type, action, client_tag, status, update_type, eligible
            ORDER BY events DESC, action ASC
        """,
            params,
        )

    def get_recent(self, limit: int = 50, **filters: Any) -> list[dict]:
        where_sql, params = self._build_where_clause(filters)
        rows = self._q(
            f"SELECT * FROM requests{where_sql} ORDER BY timestamp DESC LIMIT ?",
            (*params, limit),
        )
        for row in rows:
            attempt_order = row.get("attempt_order")
            if isinstance(attempt_order, str) and attempt_order:
                try:
                    row["attempt_order"] = json.loads(attempt_order)
                except json.JSONDecodeError:
                    row["attempt_order"] = []
            decision_details = row.get("decision_details")
            if isinstance(decision_details, str) and decision_details:
                try:
                    row["decision_details"] = json.loads(decision_details)
                except json.JSONDecodeError:
                    row["decision_details"] = {}
            route_summary = row.get("route_summary")
            if isinstance(route_summary, str) and route_summary:
                try:
                    row["route_summary"] = json.loads(route_summary)
                except json.JSONDecodeError:
                    row["route_summary"] = {}
        return rows

    def get_totals(self, **filters: Any) -> dict:
        where_sql, params = self._build_where_clause(filters)
        rows = self._q(
            f"""
            SELECT COUNT(*)                                        AS total_requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)        AS total_failures,
                SUM(prompt_tok)                                    AS total_prompt_tokens,
                SUM(compl_tok)                                     AS total_compl_tokens,
                SUM(cache_hit)                                     AS total_cache_hit,
                SUM(cache_miss)                                    AS total_cache_miss,
                ROUND(CASE WHEN SUM(cache_hit+cache_miss)>0
                    THEN SUM(cache_hit)*100.0/SUM(cache_hit+cache_miss)
                    ELSE 0 END, 1)                                 AS cache_hit_pct,
                ROUND(SUM(cost_usd),6)                             AS total_cost_usd,
                ROUND(AVG(latency_ms),1)                           AS avg_latency_ms,
                MIN(timestamp)                                     AS first_request,
                MAX(timestamp)                                     AS last_request
            FROM requests{where_sql}
        """,
            params,
        )
        return rows[0] if rows else {}

    def _build_where_clause(self, filters: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        """Build a WHERE clause for common dashboard and API filters."""
        clauses = []
        params: list[Any] = []
        mapping = {
            "provider": "provider",
            "modality": "modality",
            "client_profile": "client_profile",
            "client_tag": "client_tag",
            "layer": "layer",
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value in (None, ""):
                continue
            clauses.append(f"{column} = ?")
            params.append(value)

        success = filters.get("success")
        if success not in (None, ""):
            clauses.append("success = ?")
            params.append(1 if bool(success) else 0)

        if not clauses:
            return "", ()
        return f" WHERE {' AND '.join(clauses)}", tuple(params)

    def _build_operator_where_clause(self, filters: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        """Build a WHERE clause for operator-event filters."""
        clauses = []
        params: list[Any] = []
        mapping = {
            "event_type": "event_type",
            "action": "action",
            "client_tag": "client_tag",
            "status": "status",
            "update_type": "update_type",
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value in (None, ""):
                continue
            clauses.append(f"{column} = ?")
            params.append(value)

        eligible = filters.get("eligible")
        if eligible not in (None, ""):
            clauses.append("eligible = ?")
            params.append(1 if bool(eligible) else 0)

        if not clauses:
            return "", ()
        return f" WHERE {' AND '.join(clauses)}", tuple(params)

    def get_client_cost_since(self, client_profile: str, since_ts: float) -> float:
        """Return total cost_usd for a client_profile since a given Unix timestamp.

        Used for budget enforcement: check daily/monthly spend before routing.
        Returns 0.0 if the database is not available.
        """
        if not self._conn:
            return 0.0
        rows = self._q(
            "SELECT ROUND(SUM(cost_usd),6) AS cost FROM requests WHERE client_profile=? AND timestamp>=?",
            (client_profile, since_ts),
        )
        return float((rows[0].get("cost") or 0.0)) if rows else 0.0

    def get_anomalies(self, lookback_hours: int = 1, baseline_hours: int = 24) -> list[dict]:
        """Detect anomalies by comparing recent window to a rolling baseline.

        Returns a list of anomaly dicts with keys:
          type, severity, description, current_value, baseline_value, threshold
        """
        if not self._conn:
            return []

        now = time.time()
        recent_since = now - lookback_hours * 3600
        baseline_since = now - baseline_hours * 3600

        recent = self._q(
            """SELECT COUNT(*) AS reqs,
                      SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                      ROUND(AVG(latency_ms),1) AS avg_latency,
                      ROUND(SUM(cost_usd),6) AS cost
               FROM requests WHERE timestamp>=?""",
            (recent_since,),
        )
        baseline = self._q(
            """SELECT COUNT(*) AS reqs,
                      SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                      ROUND(AVG(latency_ms),1) AS avg_latency,
                      ROUND(SUM(cost_usd),6) AS cost
               FROM requests WHERE timestamp>=? AND timestamp<?""",
            (baseline_since, recent_since),
        )

        if not recent or not baseline:
            return []

        r = recent[0]
        b = baseline[0]

        anomalies: list[dict] = []

        # Normalize baseline to the same time window length as lookback
        baseline_window_factor = baseline_hours / max(lookback_hours, 1)
        b_reqs_norm = (b.get("reqs") or 0) / baseline_window_factor
        b_cost_norm = (b.get("cost") or 0.0) / baseline_window_factor

        r_reqs = r.get("reqs") or 0
        r_failures = r.get("failures") or 0
        r_latency = r.get("avg_latency") or 0.0
        r_cost = r.get("cost") or 0.0
        b_latency = b.get("avg_latency") or 0.0

        # Error rate spike (>20% failure rate and significantly worse than baseline)
        if r_reqs > 5:
            r_error_rate = r_failures / r_reqs
            b_failures = b.get("failures") or 0
            b_reqs = b.get("reqs") or 1
            b_error_rate = b_failures / b_reqs
            if r_error_rate > 0.2 and r_error_rate > b_error_rate * 2:
                anomalies.append({
                    "type": "error_rate_spike",
                    "severity": "high" if r_error_rate > 0.5 else "medium",
                    "description": f"Error rate {r_error_rate:.0%} in last {lookback_hours}h (baseline: {b_error_rate:.0%})",
                    "current_value": round(r_error_rate, 4),
                    "baseline_value": round(b_error_rate, 4),
                    "threshold": 0.2,
                })

        # Latency spike (>2x baseline, and >500ms)
        if b_latency > 0 and r_latency > 500 and r_latency > b_latency * 2:
            anomalies.append({
                "type": "latency_spike",
                "severity": "medium",
                "description": f"Avg latency {r_latency:.0f}ms in last {lookback_hours}h (baseline: {b_latency:.0f}ms)",
                "current_value": r_latency,
                "baseline_value": b_latency,
                "threshold": b_latency * 2,
            })

        # Cost spike (>3x normalized baseline, and >$0.01 absolute)
        if b_cost_norm > 0 and r_cost > 0.01 and r_cost > b_cost_norm * 3:
            anomalies.append({
                "type": "cost_spike",
                "severity": "high",
                "description": f"Cost ${r_cost:.4f} in last {lookback_hours}h (baseline rate: ${b_cost_norm:.4f}/h)",
                "current_value": r_cost,
                "baseline_value": b_cost_norm,
                "threshold": b_cost_norm * 3,
            })

        # Traffic spike (>5x normalized baseline)
        if b_reqs_norm > 0 and r_reqs > b_reqs_norm * 5:
            anomalies.append({
                "type": "traffic_spike",
                "severity": "low",
                "description": f"{r_reqs} requests in last {lookback_hours}h (baseline: ~{b_reqs_norm:.0f}/h)",
                "current_value": r_reqs,
                "baseline_value": b_reqs_norm,
                "threshold": b_reqs_norm * 5,
            })

        return anomalies

    def _q(self, sql: str, params: tuple = ()) -> list[dict]:
        if not self._conn:
            return []
        cur = self._conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
