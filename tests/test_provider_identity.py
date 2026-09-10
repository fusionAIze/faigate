"""Tests for the provider-block disentangling in ``faigate.registry``.

Three TASK-C5 criteria:

1. every provider block carries ``vendor`` and ``model`` as separate fields
2. the generated canonical paths repeat no segment
3. resolution delivers the same providers before and after the split — proven
   with a comparison against the retained ``example_model`` field, not asserted
"""

from __future__ import annotations

from faigate import registry


def _model_segment(example_model: str) -> str:
    """Return the model part of a legacy fused ``example_model`` string."""
    raw = str(example_model or "").split("/")[-1]
    return raw.split(":")[0]


def test_every_provider_block_carries_vendor_and_model_separately():
    for name, entry in registry.ALL.items():
        assert entry.get("vendor"), f"{name} is missing a separate vendor field"
        assert entry.get("model"), f"{name} is missing a separate model field"


def test_generated_paths_do_not_repeat_a_segment():
    for name, entry in registry.ALL.items():
        vendor = entry["vendor"]
        model = entry["model"]
        hops = [str(seg) for seg in (entry.get("hop") or [])]
        segments = [*hops, vendor, model]
        assert len(segments) == len(set(segments)), f"{name} repeats a segment in its path: {segments}"


def test_canonical_path_prepends_hop_and_omits_variant_when_absent():
    assert registry.canonical_path("anthropic") == "anthropic/claude-opus-4-6"
    assert registry.canonical_path("openrouter") == "openrouter/anthropic/claude-opus-4.6"
    assert registry.canonical_path("github-copilot") == "github-copilot/openai/gpt-4o"
    assert registry.canonical_path("unknown-provider") is None


def test_resolution_delivers_the_same_providers_after_the_split():
    """Compare the pre-split ``example_model`` against the split fields.

    The legacy ``example_model`` string is retained verbatim, so it is the
    untouched "before" artifact. If the split changed which model a provider
    resolves to, the model segment would no longer match the new ``model``
    field. Every provider name must also survive the split unchanged.
    """
    for name, entry in registry.ALL.items():
        before_model = _model_segment(entry.get("example_model", ""))
        after_model = entry["model"]
        assert before_model == after_model, (
            f"{name}: split changed the resolution from {before_model!r} to {after_model!r}"
        )

    assert set(registry.ALL) == set(registry.known_names())


def test_no_two_providers_claim_the_same_canonical_path():
    seen: dict[str, str] = {}
    for name in registry.known_names():
        path = registry.canonical_path(name)
        assert path, name
        assert path not in seen, f"{name} collides with {seen[path]} on {path}"
        seen[path] = name
