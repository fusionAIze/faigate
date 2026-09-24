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

from faigate.provider_catalog import get_provider_catalog
from faigate.reachability import model_is_concrete, reachability_model_matches


def _catalog_entries():
    """Yield (provider_id, entry) for every catalog entry."""
    catalog = get_provider_catalog()
    yield from sorted(catalog.items())


def test_catalog_is_not_empty():
    catalog = get_provider_catalog()
    assert catalog, "provider catalog is empty — reachability checks have nothing to verify"


# Entries that still claim a provider-resolved alias, each with the reason it
# has not been fixed. This list is not a way to make the check pass: every entry
# names a decision someone still owes. Removing an entry without fixing the
# catalog turns the test red again, which is the point.
#
#   volcengine-plan  FAI-240. No Volcano Engine account is available here
#                    (ark.cn-beijing.volces.com answers 401), so the plan
#                    endpoint and its model set cannot be measured. A lane
#                    already tried to fill this in by analogy to BytePlus on
#                    2026-09-24 and invented both the path and the model; that
#                    work was rejected.
#   mistral          FAI-241. Measured 2026-09-24 against Mistral's own /models:
#                    'mistral-large-latest' does not exist, and no model with
#                    "large" in its id exists at all. 30 concrete versioned ids
#                    are available (codestral-2508, ministral-14b-2512, ...).
#                    Which one faigate should recommend is a product decision,
#                    not a rename.
KNOWN_ALIAS_CLAIMS = {"volcengine-plan", "mistral"}


def test_catalog_entry_models_are_concrete():
    """No catalog entry may claim a provider-resolved alias as its model."""
    failures: list[tuple[str, str]] = []
    for provider_id, entry in _catalog_entries():
        model = str(entry.get("model") or "")
        if not model:
            continue
        if not model_is_concrete(model):
            if provider_id in KNOWN_ALIAS_CLAIMS:
                continue
            failures.append((provider_id, model))

    assert not failures, "catalog entries with provider-resolved alias models are unreachable:\n" + "\n".join(
        f"  {pid}: model={model!r}" for pid, model in failures
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


def test_allowance_list_has_no_stale_entries():
    """Every allowed entry must still exist and still claim an alias.

    Without this the list would silently outlive the problem it documents, and
    a future entry could inherit an allowance nobody granted it.
    """
    catalog = dict(_catalog_entries())
    for provider_id in sorted(KNOWN_ALIAS_CLAIMS):
        assert provider_id in catalog, (
            f"{provider_id} is allowed to claim an alias but is no longer in the "
            f"catalog — remove it from KNOWN_ALIAS_CLAIMS"
        )
        model = str(catalog[provider_id].get("model") or "")
        assert model and not model_is_concrete(model), (
            f"{provider_id} no longer claims a provider-resolved alias "
            f"(model={model!r}) — remove it from KNOWN_ALIAS_CLAIMS"
        )
