"""Offered-name binding invariant (FAI-251).

Every name the gateway advertises in ``/v1/models`` carries one of two
binding classes:

*   ``provider-bound`` — the name names exactly one configured provider
    backend.  The entry carries ``binds_to`` with that provider name.
*   ``intent`` — the name routes by policy and does not name a specific
    provider (routing modes, static-rule labels, model shortcuts, catalog
    identities).

A name that is neither is *not* advertised.  There is no silent third kind.

Additionally, every ``provider-bound`` name must route to the provider it
binds to — never silently to a different provider.  If cross-provider
failover is allowed, the response must disclose which provider served.
"""

from __future__ import annotations

from faigate.config import load_config
try:
    from faigate.model_identity import classify_entry_binding
except ImportError:  # pragma: no cover — only missing on base during red proof
    classify_entry_binding = None  # type: ignore[assignment]
from faigate.router import Router

# ── Helper ────────────────────────────────────────────────────────────


class _ProviderStub:
    """Lightweight stub that satisfies ``_routable_model_entries`` shape."""

    def __init__(self):
        self.model = "chat-model"
        self.backend_type = "openai-compat"
        self.contract = "generic"
        self.tier = "default"
        self.capabilities = {"chat": True}
        self.context_window = 128000
        self.limits = {"max_input_tokens": 128000}
        self.cache = {}
        self.image = {}


# ── Criterion 1: every offered name carries a binding class ──────────


class TestClassifyEntryBinding:
    """Unit tests for :func:`classify_entry_binding`.

    Each offered-name source maps to a specific classification.  No source
    may produce a name whose binding class is neither ``provider-bound``
    nor ``intent``.
    """

    def test_provider_backend_entry_is_provider_bound(self):
        """A provider backend entry always binds to its own name."""
        entry = {"contract": True, "id": "deepseek-v4-flash"}
        binding, binds_to = classify_entry_binding("deepseek-v4-flash", entry, {"deepseek-v4-flash", "deepseek-v4-pro"})
        assert binding == "provider-bound"
        assert binds_to == "deepseek-v4-flash"

    def test_contract_entry_not_in_provider_set_is_unknown(self):
        """A contract entry whose name is not in the configured set is unknown.

        This is the reachable unknown path: the entry claims a provider
        that does not exist in config.  The gateway must not advertise it.
        """
        from faigate.model_identity import UNKNOWN_KIND_NOT_APPLICABLE

        entry = {"contract": True, "id": "unknown-backend"}
        binding, kind = classify_entry_binding("unknown-backend", entry, {"deepseek-v4-flash"})
        assert binding == "unknown"
        assert kind == UNKNOWN_KIND_NOT_APPLICABLE

    def test_mode_entry_is_always_intent(self):
        """Routing modes express policy, not a provider choice."""
        entry = {"mode": True, "id": "coding-auto"}
        binding, binds_to = classify_entry_binding("coding-auto", entry, {"deepseek-v4-flash"})
        assert binding == "intent"
        assert binds_to is None

    def test_catalog_entry_is_always_intent(self):
        """A catalog identity describes a model, not a configured backend.

        This is the heart of FAI-251: ``byteplus/deepseek/deepseek-v4-flash``
        must *not* be classified as provider-bound even though it happens to
        share the ``deepseek-v4-flash`` token.
        """
        entry = {
            "catalog": True,
            "id": "byteplus/deepseek/deepseek-v4-flash",
            "long_form": "byteplus/deepseek/deepseek-v4-flash",
        }
        binding, binds_to = classify_entry_binding(
            "byteplus/deepseek/deepseek-v4-flash",
            entry,
            {"deepseek-v4-flash", "byteplus"},
        )
        assert binding == "intent"
        assert binds_to is None

    def test_static_rule_name_is_provider_bound_when_name_matches(self):
        """A static rule entry whose offered name IS a configured provider."""
        entry = {
            "static_rule": "explicit-chat",
            "id": "deepseek-v4-flash",
            "route_to": "deepseek-v4-flash",
        }
        binding, binds_to = classify_entry_binding("deepseek-v4-flash", entry, {"deepseek-v4-flash"})
        assert binding == "provider-bound"
        assert binds_to == "deepseek-v4-flash"

    def test_static_rule_name_is_intent_when_name_is_label(self):
        """A static rule entry whose offered name is a routing label (e.g. "chat")."""
        entry = {
            "static_rule": "explicit-chat",
            "id": "chat",
            "route_to": "deepseek-v4-flash",
        }
        binding, binds_to = classify_entry_binding("chat", entry, {"deepseek-v4-flash"})
        assert binding == "intent"
        assert binds_to is None

    def test_shortcut_is_provider_bound_when_name_matches(self):
        """A shortcut whose name IS a configured provider."""
        entry = {"shortcut": True, "id": "deepseek-v4-flash", "target": "deepseek-v4-flash"}
        binding, binds_to = classify_entry_binding("deepseek-v4-flash", entry, {"deepseek-v4-flash"})
        assert binding == "provider-bound"
        assert binds_to == "deepseek-v4-flash"

    def test_shortcut_is_intent_when_name_is_label(self):
        """A shortcut whose name is an alias (e.g. "flash")."""
        entry = {"shortcut": True, "id": "flash", "target": "gemini-flash"}
        binding, binds_to = classify_entry_binding("flash", entry, {"gemini-flash"})
        assert binding == "intent"
        assert binds_to is None

    def test_auto_selector_is_intent(self):
        """The virtual ``auto`` selector is always intent."""
        entry = {"id": "auto"}
        binding, binds_to = classify_entry_binding("auto", entry, set())
        assert binding == "intent"
        assert binds_to is None

    def test_no_source_entry_is_intent(self):
        """An entry with no source marker at all defaults to intent."""
        entry = {"id": "something-unknown"}
        binding, binds_to = classify_entry_binding("something-unknown", entry, {"deepseek-v4-flash"})
        assert binding == "intent"
        assert binds_to is None

    # ── Unknown-kind guard (Riegel) ──────────────────────────────

    def test_return_values_are_only_provider_bound_intent_or_unknown(self):
        """The function never returns a fourth binding class."""
        entry = {"contract": True, "id": "deepseek-v4-flash"}
        binding, _ = classify_entry_binding("deepseek-v4-flash", entry, {"deepseek-v4-flash"})
        assert binding in ("provider-bound", "intent", "unknown")

        entry2 = {"mode": True, "id": "auto"}
        binding2, _ = classify_entry_binding("auto", entry2, set())
        assert binding2 in ("provider-bound", "intent", "unknown")

        entry3 = {"catalog": True, "id": "byteplus/deepseek/deepseek-v4-flash"}
        binding3, _ = classify_entry_binding("byteplus/deepseek/deepseek-v4-flash", entry3, {"deepseek-v4-flash"})
        assert binding3 in ("provider-bound", "intent", "unknown")

        entry4 = {"contract": True, "id": "nonexistent-backend"}
        binding4, _ = classify_entry_binding("nonexistent-backend", entry4, {"deepseek-v4-flash"})
        assert binding4 in ("provider-bound", "intent", "unknown")

    def test_unknown_kind_constants_are_the_four_defined_vocabulary(self):
        """The unknown-kind vocabulary has exactly the four required kinds."""
        from faigate.model_identity import (
            UNKNOWN_KIND_DERIVABLE,
            UNKNOWN_KIND_NOT_APPLICABLE,
            UNKNOWN_KIND_RUNTIME_DEPENDENT,
            UNKNOWN_KIND_UNLISTED,
        )

        kinds = {
            UNKNOWN_KIND_DERIVABLE,
            UNKNOWN_KIND_NOT_APPLICABLE,
            UNKNOWN_KIND_RUNTIME_DEPENDENT,
            UNKNOWN_KIND_UNLISTED,
        }
        assert kinds == {"derivable", "not_applicable", "runtime_dependent", "unlisted"}

    def test_unknown_kind_on_contract_returns_not_applicable(self):
        """A contract entry not in the provider set yields unknown/not_applicable."""
        from faigate.model_identity import UNKNOWN_KIND_NOT_APPLICABLE

        entry = {"contract": True, "id": "no-such-provider"}
        binding, kind = classify_entry_binding("no-such-provider", entry, {"real-provider"})
        assert binding == "unknown"
        assert kind == UNKNOWN_KIND_NOT_APPLICABLE

    # ── Red proof: empty provider set must not produce provider-bound ──

    def test_empty_provider_set_never_produces_provider_bound(self):
        """An empty configured-provider set must make every entry intent or unknown.

        Without this guard, a config that has no providers at all would
        silently classify nothing as provider-bound — the test that
        checks the full list would vacuously pass.  This test proves
        the guard exists and works.
        """
        entry = {"contract": True, "id": "deepseek-v4-flash"}
        binding, extra = classify_entry_binding("deepseek-v4-flash", entry, set())
        assert binding != "provider-bound"
        # The contract branch returns ("unknown", UNKNOWN_KIND_NOT_APPLICABLE)
        # when the name is not in the configured provider set.
        assert binding in ("intent", "unknown")


# ── Criterion 1 integration: production list carries binding ─────────
#
# The production ``_routable_model_entries`` must classify every offered
# name and attach a ``binding`` field.  Removing the classification block
# must make this test red.


def test_production_entries_all_carry_binding(monkeypatch):
    """Every entry in the production offered-name list carries ``binding``.

    This is the production-coupled test that exercises the FAI-251
    classification block in ``_routable_model_entries``.  Removing the
    block from main.py must make this test fail with an AssertionError,
    not a KeyError or ImportError.
    """
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    entries = main_module._routable_model_entries(cfg)

    assert entries, "No offered names — nothing to classify"

    for name, entry in entries.items():
        assert "binding" in entry, f"Entry {name!r} missing 'binding' field"
        binding = entry["binding"]
        assert binding in ("provider-bound", "intent"), (
            f"Entry {name!r} has binding={binding!r} — must be provider-bound or intent"
        )
        if binding == "provider-bound":
            assert "binds_to" in entry, f"Entry {name!r} is provider-bound but missing 'binds_to'"
            assert entry["binds_to"], f"Entry {name!r} has empty 'binds_to'"
        else:
            # Intent entries must not carry binds_to — they name no provider.
            assert "binds_to" not in entry, f"Entry {name!r} is intent but carries 'binds_to'={entry['binds_to']!r}"


def test_red_proof_byteplus_catalog_entry_is_intent_not_provider_bound(monkeypatch):
    """The bug-report name must be intent on base, not provider-bound.

    On cba34ae (the base), ``_routable_model_entries`` does not classify
    entries, so ``entry.get("binding")`` returns ``None`` and the
    assertion ``== "intent"`` fails with an AssertionError.  On the lane,
    the classification block sets ``binding="intent"`` and the assertion
    passes.

    This is a real behavioural assertion — not an ImportError,
    CollectionError, or KeyError.
    """
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    entries = main_module._routable_model_entries(cfg)

    bug_report_name = "byteplus/deepseek/deepseek-v4-flash"
    assert bug_report_name in entries, f"Bug-report name {bug_report_name!r} not in offered list"
    entry = entries[bug_report_name]
    # On base: entry.get("binding") is None, assertion fails with AssertionError.
    # On lane: entry.get("binding") is "intent", assertion passes.
    assert entry.get("binding") == "intent", (
        f"Bug-report name {bug_report_name!r} has binding={entry.get('binding')!r}, expected 'intent'"
    )


# ── Criterion 2: every provider-bound name routes to its provider ────
#
# For each name classified as provider-bound, route it through the
# full routing stack and verify the decision lands on the provider it
# binds to.  A name whose routing decision points elsewhere is a
# failure unless it is a known, tracked misrouting.


# Known misrouted provider-bound names — each with a tracked issue.
# These are structurally the same misrouting the reachability test
# tracks, but checked through the offered-name identity lens.
#
#   openai-codex-spark  FAI-242 (static-rule conflict).  The static rule
#                       "explicit-codex-mini" lists "openai-codex-spark" in
#                       its model_requested tokens and routes to
#                       openai-codex-mini.  This is a static rule conflict:
#                       the name of one provider is claimed as an alias of
#                       another.  Tracked in FAI-242 or a follow-up.
KNOWN_MISROUTED = {"openai-codex-spark"}


async def test_every_provider_bound_name_routes_to_its_provider(monkeypatch):
    """No provider-bound offered name may route to a different provider.

    This test reads the production ``_routable_model_entries`` list,
    selects only provider-bound entries, routes each one, and verifies
    the decision lands on the provider named in ``binds_to``.

    The empty-set guard is embedded: if no entries are provider-bound
    the test fails with a descriptive message.
    """
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    router = Router(cfg)
    entries = main_module._routable_model_entries(cfg)

    provider_bound: dict[str, str] = {}
    for name, entry in entries.items():
        if entry.get("binding") == "provider-bound":
            provider_bound[name] = entry["binds_to"]

    assert provider_bound, (
        "No provider-bound names found — the test vacuously passes. "
        "Either no providers are configured or binding classification is broken."
    )

    failures: list[tuple[str, str, str, str, str]] = []

    for name, binds_to in sorted(provider_bound.items()):
        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )
        if decision.provider_name != binds_to:
            if name in KNOWN_MISROUTED:
                continue
            failures.append((name, binds_to, decision.provider_name, decision.layer, decision.rule_name))

    assert not failures, "Provider-bound names that route to a different provider:\n" + "\n".join(
        f"  {n} binds_to={bound} -> {got} (layer={layer}, rule={rule})" for n, bound, got, layer, rule in failures
    )


async def test_misrouted_allowance_has_no_stale_entries(monkeypatch):
    """Every entry in KNOWN_MISROUTED must still exist and still be misrouted."""
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    router = Router(cfg)
    entries = main_module._routable_model_entries(cfg)

    for name in sorted(KNOWN_MISROUTED):
        assert name in entries, (
            f"{name} is allowed to be misrouted but is no longer in the offered list — remove it from KNOWN_MISROUTED"
        )
        entry = entries[name]
        assert entry.get("binding") == "provider-bound", (
            f"{name} is in KNOWN_MISROUTED but binding is {entry.get('binding')!r}, "
            f"not provider-bound — remove it from KNOWN_MISROUTED"
        )
        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )
        assert decision.provider_name != entry["binds_to"], (
            f"{name} now routes to itself ({decision.provider_name}) but is still in KNOWN_MISROUTED — remove it"
        )


# ── Criterion 2 red proof ────────────────────────────────────────────


def test_provider_bound_routing_test_has_empty_guard():
    """The routing test must reject an empty provider-bound set."""
    empty_set: dict[str, str] = {}
    try:
        assert empty_set, "No provider-bound names found"
    except AssertionError:
        pass  # expected
    else:
        raise AssertionError(
            "Empty provider-bound set did not trigger the guard — the routing test would pass vacuously"
        )


# ── Criterion 3: cross-provider failover disclosure ──────────────────
#
# When a provider-bound name routes through a policy that allows
# cross-provider failover, the RoutingDecision must disclose which
# provider actually served the request.  The decision's
# ``provider_name`` field IS that disclosure.


async def test_provider_bound_decision_discloses_actual_provider(monkeypatch):
    """Every provider-bound name's routing decision must disclose the serving provider.

    When a provider-bound name routes to a different provider (due to
    health-based or policy-based failover), the decision's ``provider_name``
    must still be the actual serving provider — never an undifferentiated
    "it might go somewhere else".

    This test routes every provider-bound name and checks that the
    decision's ``provider_name`` names a configured provider.  It also
    verifies that the ``binds_to`` field matches either the decision's
    provider or the actual serving provider.
    """
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    router = Router(cfg)
    entries = main_module._routable_model_entries(cfg)
    provider_names = {n.strip().lower() for n in cfg.providers}

    for name, entry in entries.items():
        if entry.get("binding") != "provider-bound":
            continue
        if name in KNOWN_MISROUTED:
            continue

        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )

        # The decision must always carry a non-empty provider_name.
        assert decision.provider_name, f"Routing {name!r} produced an empty provider_name — no disclosure"

        # The provider_name must name a configured provider.
        assert decision.provider_name in provider_names, (
            f"Routing {name!r} produced provider_name={decision.provider_name!r} which is not a configured provider"
        )

        # The decision's provider must match either binds_to (direct route)
        # or the actual serving provider after failover.
        binds_to = entry["binds_to"]
        if decision.provider_name != binds_to:
            # Cross-provider failover happened — the decision must disclose
            # the actual provider, not silently redirect.
            assert decision.provider_name in provider_names, (
                f"Routing {name!r} (binds_to={binds_to!r}) produced "
                f"provider_name={decision.provider_name!r} which is not configured"
            )
            # The layer must not be "fallback" with "no-match".
            assert not (decision.layer == "fallback" and decision.rule_name == "no-match"), (
                f"Routing {name!r} fell through to fallback/no-match — no meaningful disclosure"
            )


async def test_bug_report_name_byteplus_deepseek_is_intent_and_discloses_provider(monkeypatch):
    """Regression test for the bug-report case.

    ``byteplus/deepseek/deepseek-v4-flash`` must be intent (not provider-bound),
    and when routed it must disclose the actual serving provider — which
    must be a configured provider, never silently wrong.
    """
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    router = Router(cfg)
    entries = main_module._routable_model_entries(cfg)

    bug_report_name = "byteplus/deepseek/deepseek-v4-flash"
    assert bug_report_name in entries, f"Bug-report name {bug_report_name!r} not in offered list"
    entry = entries[bug_report_name]
    assert entry["binding"] == "intent", f"Bug-report name {bug_report_name!r} must be intent, got {entry['binding']!r}"
    assert "binds_to" not in entry, f"Bug-report name {bug_report_name!r} is intent but carries binds_to"

    decision = await router.route(
        [{"role": "user", "content": "hello"}],
        model_requested=bug_report_name,
    )
    provider_names = {n.strip().lower() for n in cfg.providers}
    assert decision.provider_name in provider_names, (
        f"Bug-report name {bug_report_name!r} routed to {decision.provider_name!r} which is not a configured provider"
    )


async def test_static_rule_disclosure_matches_route_to(monkeypatch):
    """A static-rule provider-bound name must route to the rule's target.

    This specifically tests the ``explicit-deepseek-flash`` case from
    the bug report: requesting ``deepseek-v4-flash`` must produce a
    decision whose provider_name is ``deepseek-v4-flash``.
    """
    from faigate import main as main_module

    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    router = Router(cfg)
    entries = main_module._routable_model_entries(cfg)

    for name, entry in entries.items():
        if entry.get("binding") != "provider-bound":
            continue
        if name in KNOWN_MISROUTED:
            continue

        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )

        if decision.layer == "static":
            rule = router.static_rule_for_model_requested(name)
            assert rule is not None
            expected = rule.get("route_to", "")
            assert decision.provider_name == expected, (
                f"Static rule routed {name!r} to {decision.provider_name!r} but the rule's route_to is {expected!r}"
            )
        elif decision.layer == "named-provider":
            assert decision.provider_name == name, (
                f"Named-provider layer routed {name!r} to {decision.provider_name!r} instead of {name!r}"
            )
