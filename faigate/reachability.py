"""Provider reachability invariants.

A catalog entry is *reachable* when its model claim can be verified against
the provider's actual response. The entry claims a specific model identity
(vendor + model); when the provider returns a different model, the entry is
not reachable — it advertises a model that doesn't exist at that endpoint.

Provider-resolved aliases (like ``*-latest``) break this invariant by design:
the provider can silently redirect them to any model without the catalog
knowing, so the catalog cannot hold a stable fact about what they serve.
"""

from __future__ import annotations

from typing import Any

# The routing engine carries two non-names: ``auto`` asks the layers to decide
# and the empty string means "no name given".  Router._layer_named_provider
# treats both as "not a named provider", so neither can address a provider.
_NON_ADDRESS_NAMES = frozenset({"auto", ""})


def static_rule_targets(static_rules: dict[str, Any] | None) -> set[str]:
    """Return the provider names that any static rule routes to."""
    return {
        str(rule.get("route_to") or "").strip()
        for rule in (static_rules or {}).get("rules", []) or []
        if str(rule.get("route_to") or "").strip()
    }


def is_addressable_provider_name(provider_name: str | None, static_rules: dict[str, Any] | None) -> bool:
    """Return True when a request can reach *provider_name* by this name.

    A provider is addressable when the routing engine can send a request to it:

    - a static rule routes to the provider name (``static_rules``), or
    - the named-provider layer accepts the name itself — the requested model
      equals a configured provider key (``Router._layer_named_provider``).

    ``auto`` and ``""`` are reachable by no name and are therefore never
    addressable, matching the layer that excludes them.
    """
    if not provider_name_is_its_own_address(provider_name):
        return False
    return str(provider_name or "").strip() in static_rule_targets(static_rules)


def addressable_provider_names(
    *,
    provider_names: Any,
    static_rules: dict[str, Any] | None,
    mode_providers: Any = (),
) -> set[str]:
    """Return the provider names a request can reach in the given routing contract.

    This is the *name-reachability* half of "can a request get here": the set of
    configured provider keys the runtime can address. It is deliberately narrower
    than the raw config keys, because a config key is a routing target, not yet
    an address (see the identity gate in ``main._is_known_model_identity``).

    A configured provider is addressable when **any** routing layer can send a
    request to its name:

    - a static rule routes to it (``static_rules`` — layer 1), or
    - a routing mode's policy selector lists it among that mode's eligible
      providers (layer 0 — the mode resolves to the name when a client asks for
      the mode or for ``auto``), or
    - the named-provider layer accepts the name itself: a request that asks for
      the provider key by name resolves to it (layer 1b), which every name-shaped
      key satisfies except ``auto`` and ``""``.

    ``mode_providers`` is the set of names some routing mode can select. It is
    precomputed by the caller because eligibility is a property of the policy
    selector, not of the routing contract alone. Passing it empty means "no mode
    can route anywhere", not "every name is unreachable by mode" — which is why
    a caller that reports coverage must gate on
    :func:`addressability_coverage_holds`: an unmeasured layer would otherwise
    look like a layer that addresses nothing.

    The caller must therefore answer the routing layers, not ask each provider
    whether it is reachable — a provider's own readiness is what this answer
    describes, and asking it here would make the signal circular.
    """
    names = {str(name).strip() for name in (provider_names or {}) if str(name).strip()}
    reachable = {str(name).strip() for name in (mode_providers or []) if str(name).strip()}
    return {
        name for name in names if name in reachable or is_addressable_provider_name(name, static_rules)
    }


#: The routing layers that give a configured provider key an address. Coverage
#: is reported per layer and every layer is *declared* here, so the check must
#: fail while a layer reaches nothing — not pass because the only layer it
#: happens to measure addresses everything. See
#: :func:`uncovered_addressability_layers` for why the declaration cannot be
#: taken on faith.
ROUTING_LAYERS = ("static-rules", "policy-modes")


def uncovered_addressability_layers(
    *,
    layer_coverage: Any,
    declared_layers: tuple[str, ...] = ROUTING_LAYERS,
) -> tuple[str, ...]:
    """Return declared layers that address no configured provider.

    Addressability is only measurable over the whole contract. A layer that no
    provider name reaches leaves the contract incomplete — the derived
    addressable set is then missing every provider that layer would address —
    so a caller must treat a non-empty result as "cannot measure yet", not as
    "nothing is unreachable".

    The counter-check this exists for: the layer set is a *claim*, and iterating
    that claim while reporting "no violations" proves nothing when the iteration
    is empty (no layer implemented) or when the claim omits a layer the
    derivation depends on. So this compares two independently measured things —
    the layers the derivation declares it covers (``declared_layers``) and the
    number of configured providers each actually reaches (``layer_coverage``,
    a mapping of layer name to reach count) — and returns the declared layers
    with no reach. An unmeasured layer reports zero and therefore shows up here
    instead of passing silently.

    ``layer_coverage`` must be keyed by the names in ``declared_layers``; a
    declared layer absent from the mapping is reported as uncovered.
    """
    coverage = layer_coverage if isinstance(layer_coverage, dict) else {}
    return tuple(
        layer
        for layer in declared_layers
        if _layer_reach_count(coverage.get(layer)) == 0
    )


def _layer_reach_count(measurement: Any) -> int:
    """Return how many configured providers a layer addresses, from either shape.

    Callers record the measurement as an int reach count or as the set of names
    they reached; both are accepted so a guard cannot pass by handing over the
    wrong shape and being silently read as zero.
    """
    if isinstance(measurement, bool) or measurement is None:
        return 0
    if isinstance(measurement, int):
        return measurement
    return len({str(name).strip() for name in measurement if str(name).strip()})


def addressability_coverage_holds(
    *,
    provider_names: Any,
    layer_coverage: Any,
    declared_layers: tuple[str, ...] = ROUTING_LAYERS,
) -> bool:
    """Return False while the addressability measurement cannot be trusted.

    True requires, all measured and none assumed:

    - at least one provider name is configured, and
    - **every** layer in ``declared_layers`` addresses at least one of them.

    A caller that reports "no provider is unreachable" must gate on this first,
    or the result is a claim over a contract it has not read.
    """
    names = {str(name).strip() for name in (provider_names or {}) if str(name).strip()}
    if not names:
        return False
    return not uncovered_addressability_layers(
        layer_coverage=layer_coverage, declared_layers=declared_layers
    )


def model_is_concrete(model_id: str) -> bool:
    """Return True if *model_id* is a concrete identifier, not a provider-resolved alias."""
    return "latest" not in str(model_id or "")


def reachability_model_matches(entry: dict[str, Any], observed_model: str) -> bool:
    """Check whether the catalog entry's model claim matches the observed response model.

    Returns False when:
    - The claimed model is a provider-resolved alias (``*-latest``)
    - The claimed model differs from the observed model
    """
    claimed = str(entry.get("model") or "").strip()
    observed = str(observed_model or "").strip()
    if not claimed or not observed:
        return False
    if not model_is_concrete(claimed):
        return False
    return claimed == observed


def provider_routes_to_itself(decision: Any, provider_name: str) -> bool:
    """Return True when *decision* routes *provider_name* to itself.

    The named-provider layer (layer 1b) sends a request to the provider whose
    name matches ``model_requested``.  A provider is reachable by its own name
    when the route decision's ``provider_name`` matches *provider_name*.

    ``auto`` and the empty string are intentionally excluded: they mean "let
    the routing decide", not "I name this specific provider".
    """
    if not provider_name or provider_name == "auto":
        return False
    return decision.provider_name == provider_name


def provider_name_is_its_own_address(provider_name: str | None) -> bool:
    """Return True when naming *provider_name* can address a provider.

    The named-provider layer accepts a request whose model equals a configured
    provider key; ``auto`` and ``""`` are excluded there (see
    ``provider_routes_to_itself``).  This is the pure name-side half of that
    contract: whether the name *could* be used as an address at all.
    """
    name = str(provider_name or "").strip()
    return bool(name) and name not in _NON_ADDRESS_NAMES


def builtin_provider_names(providers: dict[str, Any] | None) -> set[str]:
    """Return the built-in provider names, excluding the ``kilo-auto/*`` modes.

    These are always addressable by their own name: the named-provider layer
    matches the configured key, and the ``kilo-auto/*`` routing modes resolve
    to them rather than being addressed themselves.
    """
    return {str(name) for name in (providers or {}) if not str(name).startswith("kilo-auto/")}
