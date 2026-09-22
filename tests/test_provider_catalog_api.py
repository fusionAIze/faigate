from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.modules.pop("faigate.main", None)

import faigate.main as main_module  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.provider_catalog import get_provider_catalog  # noqa: E402
from faigate.provider_catalog_store import ProviderCatalogStore  # noqa: E402
from faigate.providers import ProviderBackend  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def provider_catalog_api_state(tmp_path: Path, monkeypatch):
    # Clear any FAIGATE_CONFIG_FILE leaked from test_main_uses_explicit_config_arg
    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    db_path = tmp_path / "faigate.db"
    cfg = load_config(
        _write_config(
            tmp_path,
            f"""
server:
  host: "127.0.0.1"
  port: 8090
providers:
  blackbox-free:
    backend: openai-compat
    base_url: "https://api.blackbox.ai"
    api_key: "secret"
    model: "blackboxai/x-ai/grok-code-fast-1"
fallback_chain:
  - blackbox-free
metrics:
  enabled: false
  db_path: "{db_path}"
provider_source_refresh:
  enabled: true
  on_startup: false
  providers:
    - blackbox
""",
        )
    )

    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.upsert_source(
        {
            "provider_id": "blackbox",
            "display_name": "BLACKBOX",
            "refresh_interval_seconds": 21600,
            "billing_notes": "free and paid tracks can drift by key",
            "endpoints": [
                {
                    "kind": "pricing",
                    "url": "https://docs.blackbox.ai/api-reference/models/chat-pricing",
                    "parser_type": "markdown-pricing-table",
                }
            ],
            "availability": {},
        }
    )
    store.mark_source_check("blackbox", success=False, error="404 from pricing source")
    store.record_change_events(
        [
            {
                "provider_id": "blackbox",
                "detected_at": 1.0,
                "source_kind": "pricing",
                "change_type": "model-removed",
                "severity": "warning",
                "model_id": "x-ai/grok-code-fast-1:free",
                "field_name": "model_id",
                "old_value": "x-ai/grok-code-fast-1:free",
                "new_value": "",
                "message": ("blackbox: model 'x-ai/grok-code-fast-1:free' disappeared from pricing."),
            }
        ]
    )

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", {}, raising=False)
    monkeypatch.setattr(main_module, "_provider_catalog_store", store, raising=False)
    yield
    store.close()


def test_provider_catalog_endpoint_includes_source_alerts(provider_catalog_api_state):
    body = asyncio.run(main_module.provider_catalog())

    assert body["source_catalog"]["tracked_sources"] == 1
    assert body["source_catalog"]["error_sources"] == 1
    assert body["source_alert_summary"]["status"] == "intervention-needed"
    assert body["source_alert_summary"]["fix_now"] == 2
    assert body["source_catalog"]["alerts"][0]["kind"] == "source-refresh-error"
    assert any(alert["kind"] == "catalog-change" for alert in body["source_alerts"])
    assert any(
        "verify the source URL, parser, or auth assumptions" in alert["suggestion"] for alert in body["source_alerts"]
    )


# ---------------------------------------------------------------------------
# FAI-228: the display marks an unverified provider window
# ---------------------------------------------------------------------------


def _catalog_provider_with_level(level: str) -> str:
    """Name one catalog provider whose ``context_window`` carries ``level``.

    Read from the catalog rather than hardcoded: which providers are unverified
    is a fact about the catalog data, which is refreshed independently of this
    test. The promise under test is that *whatever* level the catalog records
    reaches the display, not that a particular provider holds it today.
    """
    for name, entry in get_provider_catalog().items():
        recorded = str((entry.get("context_evidence") or {}).get("level") or "").strip()
        if recorded == level and entry.get("context_window"):
            return name
    pytest.skip(f"catalog records no provider with context_evidence.level={level!r}")


@pytest.fixture
def provider_window_state(monkeypatch):
    """Merge the queried providers onto the shared, module-level provider map.

    ``_providers`` is a module global, so ``{**existing, **ours}`` publishes the
    fixtures without erasing providers another test in this module registered.
    """
    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    existing = dict(getattr(main_module, "_providers", {}) or {})

    def publish(names: list[str]) -> dict[str, ProviderBackend]:
        backends = {
            name: ProviderBackend(
                name,
                {"base_url": "https://example.invalid/v1", "model": "fixture-model"},
            )
            for name in names
        }
        monkeypatch.setattr(
            main_module,
            "_providers",
            {**existing, **backends},
            raising=False,
        )
        return backends

    return publish


def test_unverified_window_is_marked_in_the_provider_inventory(provider_window_state):
    """An ``unconfirmed`` catalog window is shown *as an operating assumption*.

    The window is still the unverified catalog number, and the evidence block
    sits next to it so the operator can read it as an assumption. Before FAI-228
    the inventory carried the bare number with nothing to say where it came from.
    """
    name = _catalog_provider_with_level("unconfirmed")
    provider_window_state([name])

    rows = {row["name"]: row for row in main_module._build_provider_inventory()}
    row = rows[name]

    catalog_window = int(get_provider_catalog()[name]["context_window"])
    assert row["context_window"] == catalog_window, (
        "the window must stay visible next to its tag: hiding an unverified "
        "number would leave the operator unable to tell what the gateway "
        "computes with"
    )
    assert row["context_window_evidence"]["level"] == "unconfirmed", (
        f"provider {name!r} shows context_window={row['context_window']} without "
        "marking it unverified; the operator cannot tell the number is an "
        "operating assumption rather than a fact"
    )


def test_unverified_window_is_marked_on_the_serialized_provider(provider_window_state):
    """``/api/providers/{name}`` — one provider snapshot — carries the tag too."""
    name = _catalog_provider_with_level("unconfirmed")
    provider_window_state([name])

    snapshot = main_module._serialize_provider(name)

    assert snapshot is not None
    assert snapshot["context_window_evidence"]["level"] == "unconfirmed", (
        f"/api/providers/{name} reports context_window={snapshot['context_window']} "
        "with evidence "
        f"{snapshot.get('context_window_evidence')!r}; an unverified window must "
        "be labelled as such"
    )


def test_all_provider_surfaces_agree_on_the_evidence_level(provider_window_state):
    """Inventory, single snapshot and ``/v1/models`` relay the same level.

    One catalog level, relayed — not three judgements. If a surface derived its
    own verdict from the number, these would be free to disagree.
    """
    unconfirmed = _catalog_provider_with_level("unconfirmed")
    confirmed = _catalog_provider_with_level("confirmed")
    provider_window_state([unconfirmed, confirmed])

    inventory = {row["name"]: row for row in main_module._build_provider_inventory()}
    catalog = get_provider_catalog()

    for name in (unconfirmed, confirmed):
        expected = catalog[name]["context_evidence"]["level"]

        from_inventory = inventory[name]["context_window_evidence"]["level"]
        from_snapshot = main_module._serialize_provider(name)["context_window_evidence"]["level"]

        assert from_inventory == expected, f"inventory for {name!r} says {from_inventory!r}, catalog says {expected!r}"
        assert from_snapshot == expected, f"snapshot for {name!r} says {from_snapshot!r}, catalog says {expected!r}"

    assert inventory[unconfirmed]["context_window_evidence"]["level"] == "unconfirmed"
    assert inventory[confirmed]["context_window_evidence"]["level"] == "confirmed", (
        "a confirmed window must be marked confirmed, not left blank"
    )


def test_health_reports_the_evidence_level_too(provider_window_state, tmp_path):
    """``/health`` is the fourth surface and relays the same tag.

    Dashboard and inventory read ``/api/providers``, but an operator watching
    ``/health`` must not get a barer answer than the other surfaces.
    """
    unconfirmed = _catalog_provider_with_level("unconfirmed")
    provider_window_state([unconfirmed])
    main_module._config = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8099
providers:
  ollama:
    backend: openai-compat
    base_url: "https://x.invalid"
    model: "m"
""",
        )
    )

    body = asyncio.run(main_module.health())
    reported = body["providers"][unconfirmed]

    assert reported["context_window_evidence"]["level"] == "unconfirmed", (
        f"/health reports context_window={reported['context_window']} for {unconfirmed!r} "
        f"with evidence {reported.get('context_window_evidence')!r}; the surface an "
        "operator watches most must mark an unverified window as well"
    )


def test_operator_declared_window_is_not_labelled_with_catalog_evidence(provider_window_state):
    """A window the operator declared is not catalog evidence — it is not tagged.

    The catalog never vouched for the operator's number, so it has no level to
    relay. Tagging it with a catalog level would attach a provenance to a value
    the catalog never saw.
    """
    name = _catalog_provider_with_level("confirmed")
    backends = provider_window_state([name])

    backend = ProviderBackend(
        name,
        {
            "base_url": "https://example.invalid/v1",
            "model": "fixture-model",
            "context_window": 4096,
        },
    )
    main_module._providers[name] = backend

    assert backends[name].context_window_evidence["level"] == "confirmed"
    assert backend.context_window == 4096
    assert backend.context_window_evidence is None, (
        "an operator-declared window must not carry catalog evidence; the "
        f"catalog never judged 4096, yet the backend tagged it "
        f"{backend.context_window_evidence!r}"
    )


def test_evidence_block_is_passed_through_not_re_judged(provider_window_state):
    """The block is relayed verbatim, including the catalog's own note and date."""
    name = _catalog_provider_with_level("unconfirmed")
    provider_window_state([name])

    catalog_evidence = dict(get_provider_catalog()[name]["context_evidence"])
    relayed = main_module._serialize_provider(name)["context_window_evidence"]

    assert relayed == catalog_evidence, (
        "the display must relay the catalog's evidence block unchanged; a "
        f"different block means the display judged the fact itself.\n"
        f"  catalog: {catalog_evidence!r}\n"
        f"  display: {relayed!r}"
    )


def test_served_dashboard_marks_the_window_it_renders():
    """The HTML the dashboard route actually serves carries the evidence tag.

    Asserted against the string the route returns, not against the module the
    helper lives in. ``main`` builds its own ``_DASHBOARD_HTML`` literal and then
    rebinds the name to the extracted cockpit template, so a change made to one
    and not the other is invisible at runtime. Reading the served template keeps
    this guard aimed at what the operator's browser receives.
    """
    served = asyncio.run(main_module.dashboard())

    assert "context_window_evidence" in served, (
        "the served dashboard renders the provider inventory but never reads "
        "context_window_evidence; an unverified window would reach the operator "
        "as a bare number"
    )
    assert "function formatContextWindow" in served, (
        "the served dashboard has no window formatter, so the evidence level cannot be shown next to the number"
    )
    provider_row = served.split("function providerRow", 1)[1].split("function ", 1)[0]
    assert "formatContextWindow(row)" in provider_row, (
        "the provider row does not call the window formatter; the tag exists in "
        "the template but never reaches a rendered row"
    )


def test_payload_too_large_response_names_no_context_window():
    """The 413 stays as it was: it never mentions the provider window.

    FAI-228 changes display surfaces only. A 413 answers with the per-model
    input cap (or nothing), never with ``context_window`` or its evidence.
    """
    models = [
        _catalog_provider_with_level("unconfirmed"),
        _catalog_provider_with_level("plausible"),
        "gpt-5.6-sol",
        "totally-unknown-model",
        None,
    ]

    for model_id in models:
        response = main_module._payload_too_large_response("payload too large", model_id=model_id)
        body = json.loads(response.body)

        assert response.status_code == 413
        assert "context_window" not in body, (
            f"413 for model_id={model_id!r} now reports context_window={body.get('context_window')!r}; "
            "the error output must stay unchanged and keep naming no window"
        )
        assert "context_window_evidence" not in body, (
            f"413 for model_id={model_id!r} leaked the evidence tag; the error path was not in scope"
        )
