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
