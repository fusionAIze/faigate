"""Provider reachability invariant: what the catalog claims must be what the provider serves.

A catalog entry is unreachable when it advertises a provider-resolved alias
(like ``*-latest``) because the provider can silently redirect that alias to
any model without the catalog knowing.

On 2026-09-24 the shipped catalog contains two entries whose model claims are
provider-resolved aliases and therefore unreachable by definition:

- ``volcengine-plan``: ``model: "ark-code-latest"``
- ``byteplus-plan``: ``model: "ark-code-latest"``

A live request to ``/v1/models`` advertises ``volcengine-plan/ark-code-latest``;
a chat completion on that model returns HTTP 200 with ``gemini-2.5-flash-lite``.
The catalog asserts one model; the provider serves another. That is the
reachability invariant this module guards.
"""

from __future__ import annotations

import pytest

from faigate.provider_catalog import get_provider_catalog
from faigate.reachability import model_is_concrete, reachability_model_matches


def _catalog_entries():
    """Yield (provider_id, entry) for every catalog entry."""
    catalog = get_provider_catalog()
    for provider_id, entry in sorted(catalog.items()):
        yield provider_id, entry


def test_catalog_is_not_empty():
    catalog = get_provider_catalog()
    assert catalog, "provider catalog is empty — reachability checks have nothing to verify"


def test_catalog_entry_models_are_concrete():
    """No catalog entry may claim a provider-resolved alias as its model."""
    failures: list[tuple[str, str]] = []
    for provider_id, entry in _catalog_entries():
        model = str(entry.get("model") or "")
        if not model:
            continue
        if not model_is_concrete(model):
            failures.append((provider_id, model))

    assert not failures, (
        "catalog entries with provider-resolved alias models are unreachable:\n"
        + "\n".join(f"  {pid}: model={model!r}" for pid, model in failures)
    )


def test_concrete_model_matches_its_own_claim():
    """A concrete catalog model claim must pass the identity check against itself.

    This is a tautology check: a concrete model should match its own claim.
    If it doesn't, the reachability check itself is broken.
    """
    for provider_id, entry in _catalog_entries():
        model = str(entry.get("model") or "")
        if not model or not model_is_concrete(model):
            continue
        assert reachability_model_matches(entry, model), (
            f"{provider_id}: concrete model {model!r} failed the identity "
            f"check against itself — reachability_model_matches is broken"
        )


def test_provider_resolved_alias_never_matches():
    """A provider-resolved alias model claim must never pass the reachability check."""
    for provider_id, entry in _catalog_entries():
        model = str(entry.get("model") or "")
        if not model or model_is_concrete(model):
            continue
        # A provider-resolved alias cannot match any observed model because
        # the provider can silently redirect it. The check must return False
        # even when the observed model is identical to the alias.
        assert not reachability_model_matches(entry, model), (
            f"{provider_id}: alias model {model!r} was accepted by "
            f"reachability_model_matches — provider-resolved aliases are not verifiable"
        )
        # It also must not match a plausible real model like deepseek-v4-flash.
        assert not reachability_model_matches(entry, "deepseek-v4-flash"), (
            f"{provider_id}: alias model {model!r} matched 'deepseek-v4-flash' "
            f"in reachability_model_matches — aliases must never match anything"
        )
