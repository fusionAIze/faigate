"""Runtime-resolved aliases carry no concrete vendor facts.

A runtime-resolved alias is a model identifier that does not name a specific
model — it resolves at runtime to whatever model the upstream endpoint assigns.
For example, ``ark-code-latest`` on Volcano Engine resolves to the current
coding model, which may be DeepSeek, GLM, or a Seed model depending on the
upstream's current mapping.

An entry whose ``model`` is such an alias must not carry a ``vendor`` claim,
because the resolved model's manufacturer is unknown at registry-write time.
The ``byteplus-plan`` entry originally had ``vendor="volcengine"`` with alias
``ark-code-latest`` — when the alias was replaced with the real model
``deepseek-v4-flash``, the vendor claim silently became false
(``byteplus/volcengine/deepseek-v4-flash`` asserts Volcano Engine built
DeepSeek V4). This guard prevents that class of bug.
"""

import pytest

from faigate.registry import ALL as PROVIDERS

# Model names that are runtime-resolved aliases — they do not identify a
# specific model and must not carry concrete vendor or model claims.
RUNTIME_ALIASES: set[str] = {
    "ark-code-latest",
}


def _alias_entries() -> list[tuple[str, str, str]]:
    out = []
    for name, entry in sorted(PROVIDERS.items()):
        model = str(entry.get("model") or "")
        if model in RUNTIME_ALIASES:
            vendor = str(entry.get("vendor") or "")
            out.append((name, vendor, model))
    return out


def test_runtime_aliases_are_identified() -> None:
    """Self-guard: fail if no entry uses a known runtime alias."""
    entries = _alias_entries()
    assert entries, "no registry entry uses a known runtime-resolved alias"


@pytest.mark.parametrize("name,vendor,model", _alias_entries())
def test_runtime_alias_carries_no_vendor(
    name: str, vendor: str, model: str
) -> None:
    """A runtime-resolved alias must not claim a concrete vendor."""
    assert not vendor, (
        f"{name} uses runtime-resolved alias '{model}' but claims "
        f"vendor='{vendor}'. Runtime aliases must carry no concrete vendor "
        f"because the resolved model's manufacturer is unknown."
    )
