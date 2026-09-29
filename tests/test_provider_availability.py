from __future__ import annotations

from pathlib import Path

import faigate.main as faigate_main
from faigate.provider_availability import (
    build_provider_availability_overlay,
    record_availability_from_config,
    refresh_local_model_availability,
)
from faigate.provider_catalog_store import ProviderCatalogStore
from faigate.providers import ProviderBackend, create_provider_backend
from faigate.reachability import (
    ROUTING_LAYERS,
    addressability_coverage_holds,
    addressable_provider_names,
    static_rule_targets,
    uncovered_addressability_layers,
)
from faigate.router import Router, providers_routed_to_themselves


class FakeJsonFetcher:
    def __init__(self, payloads: dict[str, dict]):
        self._payloads = payloads

    def fetch_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict:
        return dict(self._payloads[url])


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  blackbox-free:
    backend: openai-compat
    base_url: "https://api.blackbox.ai"
    api_key: "secret"
    model: "x-ai/grok-code-fast-1:free"
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
fallback_chain: []
metrics:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def test_local_models_endpoint_overlay_detects_key_specific_mismatch(tmp_path: Path):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.replace_model_snapshot(
        "blackbox",
        "pricing",
        [
            {
                "model_id": "x-ai/grok-code-fast-1:free",
                "model_name": "Grok Code Fast 1 Free",
                "input_cost": 0.0,
                "output_cost": 0.0,
                "context_length": 256000,
                "is_free": True,
                "raw_source_hash": "hash-blackbox",
            }
        ],
    )
    store.replace_model_snapshot(
        "deepseek",
        "models",
        [
            {
                "model_id": "deepseek-chat",
                "model_name": "DeepSeek Chat",
                "input_cost": None,
                "output_cost": None,
                "context_length": None,
                "is_free": False,
                "raw_source_hash": "hash-deepseek",
            }
        ],
    )

    record_availability_from_config(
        store,
        config_path=str(config_path),
        health_payload={
            "providers": {
                "blackbox-free": {
                    "request_readiness": {
                        "ready": False,
                        "status": "degraded",
                        "reason": "last request failed",
                    }
                },
                "deepseek-chat": {
                    "request_readiness": {
                        "ready": True,
                        "status": "ready",
                        "reason": "healthy",
                    }
                },
            }
        },
    )
    refresh_local_model_availability(
        store,
        config_path=str(config_path),
        fetcher=FakeJsonFetcher(
            {
                "https://api.blackbox.ai/v1/models": {"data": [{"id": "x-ai/grok-code-fast-1"}]},
                "https://api.deepseek.com/v1/models": {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]},
            }
        ),
    )

    blackbox_overlay = build_provider_availability_overlay(
        store,
        provider_id="blackbox",
        global_model_ids={"x-ai/grok-code-fast-1:free"},
        global_free_model_ids={"x-ai/grok-code-fast-1:free"},
    )
    deepseek_overlay = build_provider_availability_overlay(
        store,
        provider_id="deepseek",
        global_model_ids={"deepseek-chat", "deepseek-reasoner"},
        global_free_model_ids=set(),
    )

    assert blackbox_overlay["status"] == "intervention-needed"
    assert blackbox_overlay["key_model_mismatches"][0]["route_name"] == "blackbox-free"
    assert blackbox_overlay["local_only_models"] == ["x-ai/grok-code-fast-1"]
    assert blackbox_overlay["free_models_missing_locally"] == ["x-ai/grok-code-fast-1:free"]
    assert deepseek_overlay["status"] == "clear"
    assert deepseek_overlay["visible_models"] == ["deepseek-chat", "deepseek-reasoner"]


# ── Request-readiness names its own states (FAI-237-B) ───────────────────────
#
# ``ready`` currently means "the key resolved and the endpoint answered". The
# field reads as "this route accepts requests". As long as addressability is
# not carried alongside, the field does not mean what it says and an operator
# has no signal for the failure FAI-237-A fixed: a provider no routing layer
# reaches is unreachable by its own name.
#
# The acceptance criteria below pin four things:
#   1. a provider no routing layer addresses reports not-ready and names why,
#   2. 'no key', 'the endpoint did not answer' and 'not addressable' stay their
#      own states, so the reason names a cause the operator can act on,
#   3. the /health roll-up sums the states against the individual providers,
#   4. providers that were ready before stay ready (no readiness regression).
#
# Addressability is derived by the runtime from the whole routing contract —
# ``faigate.reachability.addressable_provider_names`` over the provider keys,
# the static rules and the mode-eligible set — and handed to the production
# factory ``create_provider_backend(addressable_names=...)``. The guards below
# drive that same derivation, so the state under test is the one the runtime
# computes, not a private flag a test flipped behind the product's back.

_PROVIDER_CFG = {
    "backend": "openai-compat",
    "base_url": "https://api.example.com/v1",
    "api_key": "secret",
    "model": "test-model",
}

# A static rules block that addresses exactly one provider by name.
_STATIC_RULES = {
    "enabled": True,
    "rules": [{"name": "addressed", "match": {"fallthrough": True}, "route_to": "addressed-provider"}],
}


def _contract(provider_names, *, static_rules=None, mode_providers=(), named_provider_names=()):
    """Derive the addressable set the runtime would hand the factory.

    This is the shipped derivation, not a fixture: ``provider_names`` is the
    configured key set, ``static_rules`` the layer-1 contract, ``mode_providers``
    the names some routing mode can select and ``named_provider_names`` the keys
    the router resolves to themselves. A configured key that no layer reaches —
    not a rule target, not mode-eligible, not self-routing — falls out of the
    set, and that is exactly the provider the readiness ladder must call
    ``not-addressable``.
    """
    return addressable_provider_names(
        provider_names=provider_names,
        static_rules=static_rules,
        mode_providers=mode_providers,
        named_provider_names=named_provider_names,
    )


def _make_backend(
    name: str,
    *,
    api_key: str = "secret",
    last_error: str = "",
    healthy: bool = True,
    addressable: bool = True,
) -> ProviderBackend:
    """Build a backend through the production factory with an addressability claim.

    ``addressable`` is passed as the full addressable *set* the runtime would
    compute: ``{name}`` when the name is reachable, ``set()`` when it is not.
    That is the factory's real input shape, so the test exercises the shipped
    derivation path rather than a boolean the factory never accepts.
    """
    cfg = {**_PROVIDER_CFG, "api_key": api_key}
    backend = create_provider_backend(name, cfg, addressable_names={name} if addressable else set())
    if last_error:
        backend.health.last_error = last_error
        backend.health.healthy = healthy
    return backend


class TestAddressabilityReadiness:
    """Criterion 1 & 2: not-addressable is a named, distinct readiness state."""

    def test_unaddressed_provider_is_not_ready_and_names_the_reason(self):
        """A configured provider no layer reaches must not report ready.

        The name is real (it is in the configured key set) but no static rule
        targets it, no mode selects it, and it is excluded from the addressable
        set the runtime derives. Readiness must drop and the reason must name
        both the provider and the missing routing target.
        """
        names = ["addressed-provider", "never-by-any-rule"]
        addressable = _contract(names, static_rules=_STATIC_RULES)
        assert addressable == {"addressed-provider"}
        assert "never-by-any-rule" not in addressable

        backend = create_provider_backend("never-by-any-rule", dict(_PROVIDER_CFG), addressable_names=addressable)

        readiness = backend.request_readiness()

        assert readiness["ready"] is False
        assert readiness["status"] == "not-addressable"
        assert "never-by-any-rule" in readiness["reason"]
        assert "routing" in readiness["reason"]
        assert readiness["operator_hint"] == (
            "no routing layer addresses this provider; add a static rule, a mode selector, or route its name explicitly"
        )

    def test_addressable_provider_with_key_is_ready(self):
        """The control case: same shape, its name is addressed, it is ready.

        Without this the previous test would pass even if ``request_readiness``
        returned not-ready for every provider.
        """
        addressable = _contract(["addressed-provider"], static_rules=_STATIC_RULES)
        assert addressable == {"addressed-provider"}

        backend = create_provider_backend("addressed-provider", dict(_PROVIDER_CFG), addressable_names=addressable)

        readiness = backend.request_readiness()

        assert readiness["ready"] is True
        assert readiness["status"] == "ready"

    def test_provider_named_by_a_rule_is_addressable_and_ready(self):
        """Criterion 1's positive half: the rule's own target is addressable.

        One contract, two configured keys: the rule routes to
        ``addressed-provider`` and not to ``never-by-any-rule``. Only the
        addressed one resolves ready.
        """
        names = ["addressed-provider", "never-by-any-rule"]
        addressable = _contract(names, static_rules=_STATIC_RULES)

        addressed = create_provider_backend("addressed-provider", dict(_PROVIDER_CFG), addressable_names=addressable)
        unaddressed = create_provider_backend("never-by-any-rule", dict(_PROVIDER_CFG), addressable_names=addressable)

        assert "addressed-provider" in addressable
        assert "never-by-any-rule" not in addressable
        assert addressed.request_readiness()["ready"] is True
        assert unaddressed.request_readiness()["ready"] is False

    def test_mode_eligible_provider_is_addressable_without_a_static_rule(self):
        """A provider a routing mode can select is addressable, rule or not.

        Addressing is not only static rules: a client that asks for a mode (or
        ``auto``) reaches whichever provider the mode's policy permits. The
        derivation must treat mode eligibility as an address, otherwise such a
        provider would be wrongly reported not-addressable.
        """
        names = ["mode-only-provider"]
        without_modes = _contract(names, static_rules={"enabled": True, "rules": []})
        with_mode = _contract(names, static_rules={"enabled": True, "rules": []}, mode_providers={"mode-only-provider"})

        assert without_modes == set()
        assert with_mode == {"mode-only-provider"}

        backend = create_provider_backend("mode-only-provider", dict(_PROVIDER_CFG), addressable_names=with_mode)
        assert backend.request_readiness()["status"] == "ready"

    def test_a_key_the_router_resolves_to_itself_is_addressable_without_a_rule(self):
        """The named-provider layer is the third address, and it is enough alone.

        A client that asks for a configured provider key by name lands on that
        provider even when no rule and no mode names it. Counting only rules and
        modes would report such a provider not-addressable and hide a reachable
        route behind a failure state.
        """
        names = ["self-routed-provider"]
        empty_rules = {"enabled": True, "rules": []}
        without_name = _contract(names, static_rules=empty_rules)
        with_name = _contract(names, static_rules=empty_rules, named_provider_names={"self-routed-provider"})

        assert without_name == set()
        assert with_name == {"self-routed-provider"}

        backend = create_provider_backend("self-routed-provider", dict(_PROVIDER_CFG), addressable_names=with_name)
        assert backend.request_readiness()["status"] == "ready"

    def test_a_name_a_rule_captures_elsewhere_is_not_addressable_by_its_own_key(self):
        """The measure is the resolved outcome, not the configured key set.

        When a static rule claims one key and routes it to a *different*
        provider (the shipped ``openai-codex-spark`` case), asking for that key
        does not reach that provider. The key is therefore not addressable
        unless some other layer reaches its name; treating the raw key list as
        self-routing would mark it ready and hide the capture.
        """
        names = ["captured-key", "rule-target"]
        rules = {
            "enabled": True,
            "rules": [{"match": {"fallthrough": True}, "route_to": "rule-target"}],
        }
        # The router resolves neither key to itself: ``captured-key`` is
        # captured by the rule, and ``rule-target`` is answered by the same rule.
        addressable = _contract(names, static_rules=rules, named_provider_names=set())

        assert addressable == {"rule-target"}
        assert "captured-key" not in addressable

        captured = create_provider_backend("captured-key", dict(_PROVIDER_CFG), addressable_names=addressable)
        assert captured.request_readiness()["status"] == "not-addressable"

    def test_the_named_provider_layer_measurement_resolves_each_key_by_its_own_name(self):
        """The layer-1b measurement is the router's actual answer, key by key.

        Synthetic, so it pins the measurement itself rather than the shipped
        config's shape: two bare keys and one that a fallthrough rule claims
        for another provider. The empty input is the self-guard — a measurement
        that returned nothing for an empty contract would be indistinguishable
        from a measurement that returns nothing for every contract, so the same
        call must answer ``{"a", "b"}`` when keys are present.
        """
        from faigate.config import Config

        cfg = Config(
            {
                "providers": {"a": {"api_key": "k"}, "b": {"api_key": "k"}, "captured": {"api_key": "k"}},
                "static_rules": {
                    "enabled": True,
                    "rules": [{"name": "capture", "match": {"model_requested": ["captured"]}, "route_to": "a"}],
                },
            }
        )

        assert providers_routed_to_themselves(Router(cfg), {}) == set()
        resolved = providers_routed_to_themselves(Router(cfg), cfg.providers)
        assert {"a", "b"} <= resolved
        assert "captured" not in resolved

    def test_key_endpoint_and_addressability_are_distinct_states(self):
        """The three failure modes must be their own status, not one bucket.

        'no key', 'the endpoint did not answer' and 'not addressable' are
        different operator problems with different fixes. Collapsing them into
        one status would make the readiness field name a cause it cannot
        distinguish.
        """
        missing_key = _make_backend("no-key-provider", api_key="", addressable=True)
        endpoint_down = _make_backend(
            "down-provider",
            last_error="Probe connection error: [Errno 61] Connection refused",
            healthy=False,
            addressable=True,
        )
        not_addressable = _make_backend("never-by-any-rule", addressable=False)

        states = {model.request_readiness()["status"] for model in (missing_key, endpoint_down, not_addressable)}

        # A signal must be present for every input, otherwise the guard below
        # would pass on an empty set.
        assert len(states) == 3, f"expected three distinct states, got {states}"
        assert "missing-key" in states
        assert "not-addressable" in states
        assert "connection_error" in states or "transport-error" in states

    def test_default_construction_keeps_the_historical_ready_state(self):
        """A caller that supplies no contract makes no addressability claim.

        ``create_provider_backend`` without ``addressable_names`` (and a bare
        ``ProviderBackend``) must stay ready, so existing callers of the factory
        are not silently regraded by this change.
        """
        backend = create_provider_backend("no-contract-provider", dict(_PROVIDER_CFG))

        assert backend.request_readiness()["ready"] is True
        assert backend.request_readiness()["status"] == "ready"


class TestReadinessSummaryRollup:
    """Criterion 3: /health sums the states against the individual providers.

    ``_request_readiness_summary`` is what ``/health`` and ``/api/providers``
    publish under ``request_readiness``. A roll-up that does not match the
    per-provider states is a lying dashboard: the operator sees a total that
    cannot be reconstructed from the detail.
    """

    def test_summary_counts_each_provider_state_exactly_once(self, monkeypatch):
        providers = {
            "ready-a": _make_backend("ready-a", addressable=True),
            "ready-b": _make_backend("ready-b", addressable=True),
            "no-key": _make_backend("no-key", api_key="", addressable=True),
            "unaddressed": _make_backend("unaddressed", addressable=False),
            "down": _make_backend(
                "down",
                last_error="Probe connection error: refused",
                healthy=False,
                addressable=True,
            ),
        }
        monkeypatch.setattr(faigate_main, "_providers", providers, raising=False)

        summary = faigate_main._request_readiness_summary()

        # The states counted in the roll-up must be exactly the states the
        # individual providers report — no invented states, none dropped.
        expected_statuses = {p.request_readiness()["status"] for p in providers.values()}
        assert set(summary["statuses"]) == expected_statuses
        assert sum(summary["statuses"].values()) == len(providers)

        assert summary["providers_total"] == len(providers)
        assert summary["providers_ready"] == 2
        assert summary["providers_not_ready"] == len(providers) - 2
        assert summary["statuses"]["not-addressable"] == 1
        assert summary["statuses"]["missing-key"] == 1

    def test_summary_does_not_invent_states_for_an_unknown_provider(self, monkeypatch):
        """A provider whose readiness carries no status lands under 'unknown'.

        The roll-up must never silently drop a provider: total, ready and
        not-ready have to stay consistent even for a status-less provider.
        """

        class _Statusless:
            name = "statusless"

            def request_readiness(self):
                return {"ready": False}

        monkeypatch.setattr(faigate_main, "_providers", {"statusless": _Statusless()}, raising=False)

        summary = faigate_main._request_readiness_summary()

        assert summary["providers_total"] == 1
        assert summary["providers_not_ready"] == 1
        assert summary["statuses"] == {"unknown": 1}
        assert sum(summary["statuses"].values()) == summary["providers_total"]


# ── No readiness regression (FAI-237-B criterion 4) ──────────────────────────
#
# The addressability signal must be additive: a provider that reported ready
# before this change has to keep reporting ready. The guards below materialise
# the shipped config's providers through the runtime factory with the runtime's
# own addressability derivation (which, measured here, addresses every shipped
# provider) and require every one to stay ready.

READY_STATUSES = {"ready", "ready-verified", "ready-compat"}


def _shipped_config_provider_names() -> list[str]:
    """The provider keys of the repository's shipped ``config.yaml``."""
    from faigate.config import load_config

    return list(load_config(str(Path(__file__).resolve().parents[1] / "config.yaml")).providers)


class TestNoReadinessRegression:
    """Criterion 4: addressable providers keep the status they had before."""

    def test_previously_ready_providers_stay_ready(self):
        """The ladder's ready branches are unchanged by the new gate.

        Three shapes of ready provider — bare config-ready, probe-verified
        and compatibility-backed — must all still report ready when the
        addressability set contains them. Sorted comparison so the guard fails
        loudly if the set is empty or a branch silently flips.
        """
        addressable = {"bare-ready", "probe-verified", "compat-ready"}
        bare_ready = create_provider_backend("bare-ready", dict(_PROVIDER_CFG), addressable_names=addressable)
        probe_verified = create_provider_backend("probe-verified", dict(_PROVIDER_CFG), addressable_names=addressable)
        probe_verified._last_probe_verified = True
        probe_verified._last_probe_strategy = "models"
        compat_ready = create_provider_backend("compat-ready", dict(_PROVIDER_CFG), addressable_names=addressable)
        compat_ready.transport["compatibility"] = "openai-compat"
        compat_ready.transport["probe_confidence"] = "medium"

        statuses = sorted(
            backend.request_readiness()["status"] for backend in (bare_ready, probe_verified, compat_ready)
        )

        assert statuses == ["ready", "ready-compat", "ready-verified"]
        assert set(statuses) <= READY_STATUSES
        assert len(statuses) > 0

    def test_previously_not_ready_providers_keep_their_specific_status(self):
        """The non-ready branches must not be rerouted into 'not-addressable'.

        'no key' and 'endpoint did not answer' were already their own states
        before addressability existed. The new gate sits after them, so an
        addressable provider with a missing key still says 'missing-key' and
        a failing endpoint still says 'transport-error'.
        """
        missing_key = _make_backend("missing-key", api_key="", addressable=True)
        endpoint_down = _make_backend(
            "endpoint-down",
            last_error="Probe connection error: [Errno 61] Connection refused",
            healthy=False,
            addressable=True,
        )

        assert missing_key.request_readiness()["status"] == "missing-key"
        assert endpoint_down.request_readiness()["status"] == "transport-error"

    def test_the_runtime_derivation_addresses_every_shipped_provider(self):
        """Measured, not synthetic: the shipped contract addresses all keys.

        The derivation runs over the real ``config.yaml`` key set with the
        repository's own static rules *and* the mode-eligible set
        ``faigate.main._mode_eligible_provider_names`` computes from the same
        config. Rules alone are a half-measure here: the shipped contract routes
        many providers through the policy modes, so a rules-only derivation
        reports a wall of false positives. An empty candidate set fails rather
        than passing vacuously.
        """
        from faigate.config import load_config
        from faigate.main import _mode_eligible_provider_names
        from faigate.providers import create_provider_backend

        cfg = load_config(str(Path(__file__).resolve().parents[1] / "config.yaml"))
        names = list(cfg.providers)
        assert names, "shipped config produced no providers; the guard has nothing to check"

        # The mode-eligible set needs the backend view the runtime holds, so the
        # guard builds providers the same way ``lifespan`` does before asking.
        providers = {name: create_provider_backend(name, dict(cfg.provider(name) or {})) for name in names}
        mode_providers = _mode_eligible_provider_names(config=cfg, providers=providers)
        assert mode_providers, "no mode can select any provider; the layer is unmeasured"

        # The named-provider layer is measured, not inferred from the key list:
        # a bare token a static rule redirects (openai-codex-spark) does reach
        # itself, so it must not be counted by assumption.
        name_targets = providers_routed_to_themselves(Router(cfg), cfg.providers)
        assert name_targets, "the router resolves no provider to its own name; the layer is unmeasured"
        assert "openai-codex-spark" not in name_targets, (
            "openai-codex-spark is captured by a static rule and must not be counted as self-routing"
        )

        addressable = _contract(
            names,
            static_rules=cfg.static_rules,
            mode_providers=mode_providers,
            named_provider_names=name_targets,
        )
        assert addressable, "no shipped provider is addressable; the derivation is broken"

        # Coverage is a precondition, not a formality: if a routing layer
        # reaches nothing the derivation has not read the whole contract, and
        # any "all addressed" claim below would be about the layers we happened
        # to implement.
        layer_coverage = {
            "static-rules": static_rule_targets(cfg.static_rules) & set(names),
            "policy-modes": set(mode_providers) & set(names),
            "named-provider": name_targets & set(names),
        }
        assert addressability_coverage_holds(provider_names=names, layer_coverage=layer_coverage), (
            uncovered_addressability_layers(layer_coverage=layer_coverage)
        )

        unaddressed = sorted(set(names) - addressable)
        assert unaddressed == [], f"shipped providers no layer addresses: {unaddressed}"

    def test_shipped_config_providers_all_stay_ready(self):
        """The measured regression guard: the shipped config's providers all
        keep reporting ready under the runtime's addressability derivation.

        This is a real measurement, not a synthetic one: it loads the same
        ``config.yaml`` the runtime loads, derives the addressable set the same
        way the runtime does — over the static-rule and mode layers together —
        builds one backend per configured provider through the runtime factory,
        and requires every backend to report ready. An empty candidate set fails
        rather than passing vacuously.
        """
        from faigate.config import load_config
        from faigate.main import _mode_eligible_provider_names
        from faigate.providers import create_provider_backend

        cfg = load_config(str(Path(__file__).resolve().parents[1] / "config.yaml"))
        names = list(cfg.providers)
        assert names, "shipped config produced no providers; the guard has nothing to check"

        providers = {name: create_provider_backend(name, dict(cfg.provider(name) or {})) for name in names}
        mode_providers = _mode_eligible_provider_names(config=cfg, providers=providers)
        assert mode_providers, "no mode can select any provider; the layer is unmeasured"

        name_targets = providers_routed_to_themselves(Router(cfg), cfg.providers)

        addressable = _contract(
            names,
            static_rules=cfg.static_rules,
            mode_providers=mode_providers,
            named_provider_names=name_targets,
        )
        backends = [create_provider_backend(name, dict(_PROVIDER_CFG), addressable_names=addressable) for name in names]
        assert len(backends) == len(names)

        not_ready = [b.name for b in backends if not b.request_readiness()["ready"]]
        assert not_ready == [], f"providers regressed to not-ready: {not_ready}"


class TestAddressabilityCoverageGate:
    """The counter-check: a measurement over an unread layer must fail.

    Every 'all providers are addressed' guard above is only as good as the
    layer set it measures. The failure shapes below are the ones that make such
    a guard pass while measuring nothing, so the gate must reject them.
    """

    def test_an_unmeasured_layer_cannot_claim_coverage(self):
        """A layer that reaches zero providers must fail, not be assumed.

        This is the shape the change first shipped: ``mode_providers`` was an
        empty set because the layer was never implemented, so an
        addressed-name set derived from the static rules alone looked complete
        while most shipped providers were unaddressed by any rule.
        """
        names = ["a", "b"]
        only_rules = {"static-rules": {"a"}, "policy-modes": set(), "named-provider": set()}

        assert addressability_coverage_holds(provider_names=names, layer_coverage=only_rules) is False
        assert uncovered_addressability_layers(layer_coverage=only_rules) == ("policy-modes", "named-provider")

    def test_no_layer_measured_at_all_cannot_claim_coverage(self):
        """The empty-iteration shape: nothing measured, so everything is missing."""
        assert (
            addressability_coverage_holds(
                provider_names=["a"],
                layer_coverage={"static-rules": 0, "policy-modes": 0, "named-provider": 0},
            )
            is False
        )
        assert addressability_coverage_holds(provider_names=["a"], layer_coverage={}) is False
        assert addressability_coverage_holds(provider_names=[], layer_coverage={}) is False

    def test_an_omitted_declared_layer_is_reported_not_ignored(self):
        """Declaring a layer covers it: leaving it out of the mapping fails.

        The gate is asked to check the declared layers, so a caller that
        measures only some of them is caught rather than passing on the
        mapping's keys.
        """
        assert uncovered_addressability_layers(layer_coverage={"static-rules": {"a"}}) == (
            "policy-modes",
            "named-provider",
        )
        assert ROUTING_LAYERS, "an empty layer tuple would make the gate vacuous"

    def test_a_fully_measured_contract_passes_so_the_gate_is_not_always_false(self):
        """The control: the gate can succeed, so the failures above mean something."""
        names = ["addressed-provider", "never-by-any-rule"]
        addressed = _contract(names, static_rules=_STATIC_RULES)
        assert addressed == {"addressed-provider"}

        layer_coverage = {
            "static-rules": static_rule_targets(_STATIC_RULES) & set(names),
            "policy-modes": {"addressed-provider", "never-by-any-rule"} & set(names),
            "named-provider": {"never-by-any-rule"} & set(names),
        }
        assert layer_coverage["static-rules"] == {"addressed-provider"}
        assert layer_coverage["policy-modes"] == set(names)
        assert layer_coverage["named-provider"] == {"never-by-any-rule"}

        assert addressability_coverage_holds(provider_names=names, layer_coverage=layer_coverage) is True
        assert uncovered_addressability_layers(layer_coverage=layer_coverage) == ()
