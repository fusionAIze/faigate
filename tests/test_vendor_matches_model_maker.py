"""``vendor`` names who built the model, not the platform that serves it.

``registry.py`` documents the field as "Model manufacturer (part of the
canonical ID path)", and ``model_identity`` builds the canonical long form as
``[hop/]vendor/model``. ``hop`` already carries the intermediary, so naming the
platform again in ``vendor`` does not add information -- it replaces the one
piece of information the field exists for.

Six resellers serve DeepSeek's R1 and every one of them names the maker:
fireworks, huggingface, hyperbolic, nebius, nvidia-nim and siliconflow all use
``deepseek`` or ``deepseek-ai``. An entry that serves a DeepSeek model under a
different vendor contradicts its own registry.

This guard exists because of a concrete mistake. ``byteplus-plan`` shipped
``vendor="volcengine"`` while its model was ``ark-code-latest`` -- a provider
resolved alias, so the vendor claim was empty rather than wrong. Replacing the
alias with the real model ``deepseek-v4-flash`` on 2026-09-23 turned that empty
claim into a false one: ``byteplus/volcengine/deepseek-v4-flash`` asserts that
Volcano Engine built DeepSeek V4. Nothing caught it.

The platform-versus-maker convention
-------------------------------------
``vendor`` names who built the model; ``hop`` names every intermediary that
serves it, including the platform.  ``byteplus`` and ``volcengine`` serve
ByteDance's own Seed and Doubao models, so their ``vendor`` reads ``bytedance``
and ``volcengine`` sits in ``hop``.  The convention was settled on 2026-09-29
under FAI-241-A and is enforced by ``test_platform_is_named_in_hop_not_vendor``.

KNOWN_ALIAS_CLAIMS
-------------------
Providers listed here carry runtime-dependent model names (``*-latest``,
``*-auto``, ``*-default``).  Their vendor claims are alias claims — the
identifier the provider resolves at runtime is not a stable catalog fact,
so the vendor field is a best-effort convention rather than an independently
verifiable statement.

This set is a barrier against unsubstantiated alias claims.  It must never
be emptied to make tests pass — that is the mistake that sank a lane on
2026-09-24.
"""

import pytest

from faigate.registry import ALL as PROVIDERS
from faigate.registry import is_runtime_dependent_model

# Providers whose vendor claims are alias claims because the model is
# runtime-resolved.  Must never be emptied.  This is the registry's actual
# state, not an aspiration: criterion 6b fails if it drifts from the entries
# that carry runtime-dependent model names (FAI-241-A).
KNOWN_ALIAS_CLAIMS: frozenset[str] = frozenset({"volcengine-plan", "mistral"})

# The platform-versus-maker convention, as settled under FAI-241-A.
#
# The mapping is not extrapolated from these two providers: it is the evidence
# registered on 2026-09-23 and 2026-09-24, when BytePlus's own ``/models``
# endpoint (``GET https://ark.ap-southeast.bytepluses.com/api/v3/models``,
# recorded in ``tests/fixtures/models_probe/byteplus_models.json``) returned
# models with ``"owned_by": "byteplus"``. BytePlus is the platform, not the
# maker: the maker claim for those models is registered elsewhere in the
# registry (``deepseek-v4-flash`` -> DeepSeek, ``seed-*`` -> ByteDance).
#
# The map is deliberately narrow.  It carries two providers because two
# platforms have a registered, independent maker claim; a third platform
# without one would be a guess, and belongs here only once its own evidence
# does.
PLATFORM_PROVIDERS: dict[str, str] = {
    # provider -> the platform its identifier names
    "volcengine": "volcengine",
    "byteplus": "byteplus",
    # ``volcengine-plan`` is deliberately absent: its model is a
    # provider-resolved alias, so there is no maker fact for the pair to
    # contradict, and its remaining ``vendor="volcengine"`` is documented at
    # the entry.
}

# The models the registry registers as ByteDance's own, each with the
# independent maker claim that puts it there.  Volcengine-plan's
# ``ark-code-latest`` is absent for a reason specific to it and recorded at
# that entry: a provider-resolved alias carries no maker in its name.
BYTEDANCE_MODELS: frozenset[str] = frozenset(
    {
        "doubao-seed-1-8-251228",
        "seed-2-0-pro",
        "seed-2-0-code",
        "seed-2-0-lite",
    }
)

# Model-name prefix -> the vendor spellings the registry already uses for that
# maker. Deliberately small: a family belongs here once the registry carries at
# least one entry for it, so the map documents practice instead of predicting it.
FAMILY_VENDORS: dict[str, set[str]] = {
    "claude": {"anthropic"},
    "deepseek": {"deepseek", "deepseek-ai"},
    "gemini": {"google"},
    "glm": {"z-ai", "zai", "zhipu"},
    "gpt": {"openai"},
    "kimi": {"moonshot"},
    "llama": {"meta", "meta-llama"},
    "mistral": {"mistral", "mistralai"},
    "qwen": {"alibaba", "qwen"},
}


def _entries() -> list[tuple[str, str, str]]:
    out = []
    for name, entry in sorted(PROVIDERS.items()):
        vendor = str(entry.get("vendor") or "")
        model = str(entry.get("model") or "")
        if vendor and model and name not in KNOWN_ALIAS_CLAIMS:
            out.append((name, vendor, model))
    return out


def _family(model: str) -> str | None:
    lowered = model.lower()
    for family in FAMILY_VENDORS:
        if lowered.startswith(family):
            return family
    return None


def test_the_map_actually_matches_something() -> None:
    # A family map that matches no entry would let every assertion below pass.
    matched = [name for name, _, model in _entries() if _family(model)]
    assert matched, "no registry entry matches any known model family"


# ---------------------------------------------------------------------------
# Criterion 6: KNOWN_ALIAS_CLAIMS guard — barrier against unsubstantiated
# alias claims.  Must never be emptied.
# ---------------------------------------------------------------------------


def test_known_alias_claims_must_not_be_empty() -> None:
    """Criterion 6a: KNOWN_ALIAS_CLAIMS must never be emptied.

    Emptying this set would let runtime-dependent entries pass vendor
    validation without acknowledging their alias status — the exact
    mistake that sank a lane on 2026-09-24.
    """
    assert KNOWN_ALIAS_CLAIMS, "KNOWN_ALIAS_CLAIMS must not be empty"


def test_known_alias_claims_matches_runtime_dependent_entries() -> None:
    """Criterion 6b: KNOWN_ALIAS_CLAIMS must exactly match runtime-dependent entries.

    Every provider with a runtime-dependent model must be listed, and
    every listed provider must still have a runtime-dependent model.
    """
    runtime_dep = {
        name for name, entry in PROVIDERS.items() if is_runtime_dependent_model(str(entry.get("model") or ""))
    }
    missing = runtime_dep - KNOWN_ALIAS_CLAIMS
    extra = KNOWN_ALIAS_CLAIMS - runtime_dep
    assert not missing, "entries with runtime-dependent models not in KNOWN_ALIAS_CLAIMS:\n" + "\n".join(
        f"  {n}" for n in sorted(missing)
    )
    assert not extra, "entries in KNOWN_ALIAS_CLAIMS no longer have runtime-dependent models:\n" + "\n".join(
        f"  {n}" for n in sorted(extra)
    )


# ---------------------------------------------------------------------------
# Criterion 6: platform and maker are kept apart
# ---------------------------------------------------------------------------


def _vendored_entries() -> list[tuple[str, str, str]]:
    """Registry entries the platform convention must actually cover.

    Empty is a failure, not a free pass: a guard that inspects nothing reports
    no violations for the same reason an unplugged smoke alarm reports no fire.
    """
    return [
        (name, str(entry.get("vendor") or ""), str(entry.get("model") or ""))
        for name, entry in sorted(PROVIDERS.items())
        if name in PLATFORM_PROVIDERS
    ]


def test_platform_convention_covers_entries() -> None:
    """Guard: the convention must have entries to check before it checks them."""
    assert _vendored_entries(), (
        "PLATFORM_PROVIDERS names no registry entry — the platform/maker check has nothing to verify"
    )


def test_byteplus_measured_its_own_models_as_platform_owned() -> None:
    """The convention rests on a measurement, not on a preference.

    BytePlus's ``GET /models`` (recorded 2026-09-24) reports each model with
    ``"owned_by": "byteplus"`` — the platform, not the maker.  The registry
    therefore may not read that value as a maker claim.  Recorded payload, no
    network access.
    """
    import json
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "models_probe" / "byteplus_models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    recorded = [str(model.get("owned_by") or "") for model in payload.get("data", [])]
    assert recorded, f"no models recorded in {fixture.name} — the measurement this convention rests on is gone"
    assert all(owner == "byteplus" for owner in recorded), (
        "BytePlus /models no longer reports its models as platform-owned: " + ", ".join(sorted(set(recorded)))
    )


def test_platform_is_named_in_hop_not_vendor() -> None:
    """Criterion 6: a platform's entries name the maker in ``vendor``.

    BytePlus and Volcano Engine serve ByteDance's own Doubao and Seed models.
    The platform belongs in ``hop``; ``vendor`` must not name it again, or the
    field stops saying who built the model.

    A provider in :data:`PLATFORM_PROVIDERS` whose model belongs to
    :data:`BYTEDANCE_MODELS` fails when its ``vendor`` is the platform name.
    Registrable exceptions (a runtime-resolved alias) are recorded with their
    reason at the entry, not expressed by weakening this check.
    """
    failures: list[str] = []
    checked = 0
    for name, vendor, model in _vendored_entries():
        if model not in BYTEDANCE_MODELS:
            # Not one of the two sources' own models; the family map above
            # already covers the maker claim for every other model.
            continue
        checked += 1
        platform = PLATFORM_PROVIDERS[name]
        if vendor.lower() == platform:
            failures.append(
                f"  {name} serves ByteDance's '{model}' but names the platform "
                f"as maker (vendor='{vendor}'); the maker belongs in vendor, the platform in hop"
            )
    assert checked, "no PLATFORM_PROVIDERS entry serves a BYTEDANCE_MODEL — the convention check inspected nothing"
    assert not failures, "platform read as manufacturer:\n" + "\n".join(failures)


@pytest.mark.parametrize("name,vendor,model", _entries())
def test_vendor_names_the_maker_not_the_platform(name: str, vendor: str, model: str) -> None:
    family = _family(model)
    if family is None:
        pytest.skip(f"{name}: '{model}' belongs to no family in FAMILY_VENDORS")
    expected = FAMILY_VENDORS[family]
    assert vendor.lower() in expected, (
        f"{name} serves '{model}', built by {sorted(expected)}, but claims "
        f"vendor='{vendor}'. The canonical form would read "
        f"'{'/'.join(list(PROVIDERS[name].get('hop') or []) + [vendor, model])}'."
    )
