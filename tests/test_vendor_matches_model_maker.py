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
"""

import pytest

from faigate.registry import ALL as PROVIDERS

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
        if vendor and model:
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
