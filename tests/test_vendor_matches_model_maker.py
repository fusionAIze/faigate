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

KNOWN_ALIAS_CLAIMS
-------------------
Providers listed here carry runtime-dependent model names (``*-latest``,
``*-auto``, ``*-default``).  Their vendor claims are alias claims — the
identifier the provider resolves at runtime is not a stable catalog fact,
so the vendor field is a best-effort convention rather than an independently
verifiable statement.

``byteplus`` and ``volcengine`` serve ByteDance's own Seed and Doubao models
under ``vendor="volcengine"``, which confuses the platform with the
manufacturer.  The convention is acknowledged here rather than silently
accepted or silently rejected.

This set is a barrier against unsubstantiated alias claims.  It must never
be emptied to make tests pass — that is the mistake that sank a lane on
2026-09-24.
"""

import pytest

from faigate.registry import ALL as PROVIDERS
from faigate.registry import is_runtime_dependent_model

# Providers whose vendor claims are alias claims because the model is
# runtime-resolved.  Must never be emptied.
KNOWN_ALIAS_CLAIMS: frozenset[str] = frozenset({"volcengine-plan", "mistral"})

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
