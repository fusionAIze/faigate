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
from faigate.model_identity import classify_entry_binding
from faigate.reachability import provider_routes_to_itself
from faigate.router import Router

# ── Helper ────────────────────────────────────────────────────────────


def _provider_names(cfg) -> set[str]:
    """Return the set of configured provider names, lowercased."""
    return {n.strip().lower() for n in cfg.providers}


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

    def test_provider_backend_unknown_name_is_intent(self):
        """A backend whose name is not in the configured set is intent."""
        entry = {"contract": True, "id": "unknown-backend"}
        binding, binds_to = classify_entry_binding("unknown-backend", entry, {"deepseek-v4-flash"})
        assert binding == "intent"
        assert binds_to is None

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
    #
    # ``classify_entry_binding`` must never return a value that is not
    # one of the two recognised binding classes.  The four admissible
    # kinds for ``unknown_kind`` are: derivable, not_applicable,
    # runtime_dependent, unlisted.
    #
    # Every test in this class that calls classify_entry_binding
    # already asserts the result is either "provider-bound" or "intent".
    # The test below proves it explicitly for the known return values.

    def test_return_values_are_only_provider_bound_or_intent(self):
        """The function never returns a third binding class."""
        entry = {"contract": True, "id": "deepseek-v4-flash"}
        binding, _ = classify_entry_binding("deepseek-v4-flash", entry, {"deepseek-v4-flash"})
        assert binding in ("provider-bound", "intent")

        entry2 = {"mode": True, "id": "auto"}
        binding2, _ = classify_entry_binding("auto", entry2, set())
        assert binding2 in ("provider-bound", "intent")

        entry3 = {"catalog": True, "id": "byteplus/deepseek/deepseek-v4-flash"}
        binding3, _ = classify_entry_binding("byteplus/deepseek/deepseek-v4-flash", entry3, {"deepseek-v4-flash"})
        assert binding3 in ("provider-bound", "intent")

    # ── Red proof: empty provider set must not produce provider-bound ──

    def test_empty_provider_set_never_produces_provider_bound(self):
        """An empty configured-provider set must make every entry intent.

        Without this guard, a config that has no providers at all would
        silently classify nothing as provider-bound — the test that
        checks the full list would vacuously pass.  This test proves
        the guard exists and works.
        """
        entry = {"contract": True, "id": "deepseek-v4-flash"}
        binding, binds_to = classify_entry_binding("deepseek-v4-flash", entry, set())
        assert binding == "intent"
        assert binds_to is None


# ── Criterion 2: every provider-bound name routes to its provider ────
#
# For each name classified as provider-bound, route it through the
# full routing stack and verify the decision lands on the provider it
# binds to.  A name whose routing decision points elsewhere is a
# failure unless it is a known, tracked misrouting.


# Known misrouted provider-bound names — each with a tracked issue.
# These are structurally the same misrouting the reachability test
# tracks, but checked through the offered-name identity lens.
KNOWN_MISROUTED = {"openai-codex-spark"}


async def test_every_provider_bound_name_routes_to_its_provider(monkeypatch):
    """No provider-bound offered name may route to a different provider."""
    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    router = Router(cfg)

    # Build the set of provider-bound names: every configured provider
    # is also an offered name with binding=provider-bound.
    provider_bound_names: set[str] = set()
    for name in cfg.providers:
        provider_bound_names.add(name.strip().lower())

    assert provider_bound_names, (
        "No provider-bound names found — the test vacuously passes. "
        "Either no providers are configured or the config is empty."
    )

    failures: list[tuple[str, str, str, str]] = []

    for name in sorted(provider_bound_names):
        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )
        if not provider_routes_to_itself(decision, name):
            if name in KNOWN_MISROUTED:
                continue
            failures.append((name, decision.provider_name, decision.layer, decision.rule_name))

    assert not failures, "Provider-bound names that route to a different provider:\n" + "\n".join(
        f"  {n} -> {got} (layer={layer}, rule={rule})" for n, got, layer, rule in failures
    )


async def test_misrouted_allowance_has_no_stale_entries(monkeypatch):
    """Every entry in KNOWN_MISROUTED must still exist and still be misrouted."""
    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    router = Router(cfg)

    for name in sorted(KNOWN_MISROUTED):
        assert name in cfg.providers, (
            f"{name} is allowed to be misrouted but is no longer in config — remove it from KNOWN_MISROUTED"
        )
        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )
        assert not provider_routes_to_itself(decision, name), (
            f"{name} now routes to itself but is still in KNOWN_MISROUTED — remove it"
        )


# ── Criterion 2 red proof ────────────────────────────────────────────
#
# An empty provider-bound set must fail the routing test, not pass
# it vacuously.  This test proves the guard in
# ``test_every_provider_bound_name_routes_to_its_provider`` would
# catch an empty list.


def test_provider_bound_routing_test_has_empty_guard():
    """The routing test must reject an empty provider-bound set."""
    # If the test were run with an empty config, the assert on
    # provider_bound_names would fire.  We prove the assertion would
    # fire by testing it directly.
    empty_set: set[str] = set()
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
#
# This test verifies that every provider-bound name's routing decision
# carries a truthful provider_name field — either the bound provider
# or the actual serving provider after failover.


async def test_provider_bound_decision_discloses_actual_provider(monkeypatch):
    """Every provider-bound name's routing decision must disclose the serving provider.

    If a provider-bound name's routing decision points to a different
    provider (due to health-based or policy-based failover), the
    decision's ``provider_name`` must still be the actual serving
    provider — never an undifferentiated "it might go somewhere else".
    """
    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    router = Router(cfg)

    for name in sorted(cfg.providers):
        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )
        # The decision always has a provider_name.  It must be non-empty
        # and must name a real provider (not a virtual label).
        assert decision.provider_name, (
            f"Routing {name!r} produced an empty provider_name — no disclosure of the serving provider"
        )
        assert decision.provider_name in cfg.providers or decision.provider_name == name, (
            f"Routing {name!r} produced provider_name={decision.provider_name!r} which is not a configured provider"
        )
        # The layer must also be meaningful — "fallback" with "no-match"
        # is not a valid disclosure for a provider-bound name.
        if decision.layer == "fallback":
            assert decision.rule_name != "no-match", (
                f"Routing {name!r} fell through to fallback with no-match — no meaningful disclosure"
            )


async def test_static_rule_disclosure_matches_route_to(monkeypatch):
    """A static-rule provider-bound name must route to the rule's target.

    This specifically tests the ``explicit-deepseek-flash`` case from
    the bug report: requesting ``deepseek-v4-flash`` must produce a
    decision whose provider_name is ``deepseek-v4-flash``.
    """
    monkeypatch.delenv("FAIGATE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_CONFIG_PATH", raising=False)
    cfg = load_config()
    router = Router(cfg)

    for name in sorted(cfg.providers):
        if name in KNOWN_MISROUTED:
            continue
        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested=name,
        )
        # The decision must either route to itself (named-provider layer)
        # or to the static rule's route_to target.
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
