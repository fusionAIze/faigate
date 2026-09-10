"""Tests for short-name derivation and long-form resolution in model identity.

TASK-C6 criteria, each mapped to one or more assertions:

1. a catalog entry without a declared short name is still addressable
2. a declared short name takes precedence over the derived one
3. a kuerzel alias resolves but never surfaces as the canonical identity
4. ambiguity is reported as a candidate list, never silently resolved
"""

from __future__ import annotations

from faigate.model_identity import (
    ModelIdentity,
    ModelIdentityResolver,
    derive_short_name,
    join_identity_path,
)


def _identity(**kwargs) -> ModelIdentity:
    return ModelIdentity.from_fields(**kwargs)


# ── path derivation ──────────────────────────────────────────────────────


def test_derived_short_name_is_vendor_over_model():
    assert derive_short_name("anthropic", "claude-opus-4-6") == "anthropic/claude-opus-4-6"
    assert derive_short_name("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"


def test_long_form_builds_the_canonical_trail():
    assert join_identity_path("anthropic", "claude-opus-4-6") == "anthropic/claude-opus-4-6"
    assert (
        join_identity_path("anthropic", "claude-opus-4.6", hop=["openrouter"]) == "openrouter/anthropic/claude-opus-4.6"
    )
    assert join_identity_path("openai", "gpt-4o", variant="codex") == "openai/gpt-4o:codex"


# ── criterion 1: entry without a declared short name is addressable ──────


def test_entry_without_declared_short_name_is_addressable():
    identity = _identity(vendor="deepseek", model="deepseek-chat")
    resolver = ModelIdentityResolver([identity])

    assert resolver.resolve("deepseek/deepseek-chat").identity == identity
    assert resolver.resolve("deepseek/deepseek-chat").ambiguous == ()


# ── criterion 2: declared short name beats the derived one ───────────────


def test_declared_short_name_beats_derived():
    identity = _identity(vendor="anthropic", model="claude-opus-4-6", short_name="opus")
    resolver = ModelIdentityResolver([identity])

    # The declared short name addresses the identity…
    assert resolver.resolve("opus").identity == identity
    # …while the derived name still works because it is a pure fallback.
    assert resolver.resolve("anthropic/claude-opus-4-6").identity == identity


def test_effective_short_name_prefers_declared():
    derived = _identity(vendor="anthropic", model="claude-opus-4-6")
    declared = _identity(vendor="anthropic", model="claude-opus-4-6", short_name="claude-opus")

    assert derived.effective_short_name == "anthropic/claude-opus-4-6"
    assert declared.effective_short_name == "claude-opus"


# ── criterion 3: kuerzel aliases resolve but are never canonical ─────────


def test_kuerzel_alias_resolves_to_the_long_form():
    identity = _identity(
        vendor="deepseek",
        model="deepseek-chat",
        short_name="deepseek-chat",
        aliases=["ds", "ds-v3"],
    )
    resolver = ModelIdentityResolver([identity])

    resolution = resolver.resolve("ds")
    assert resolution.identity is identity
    assert resolution.identity.long_form == "deepseek/deepseek-chat"
    # The alias is what resolves; what the caller gets back is the long form.
    assert resolution.identity.long_form != "ds"


def test_kuerzel_alias_never_becomes_a_long_form():
    identity = _identity(vendor="kilocode", model="claude-opus-4.6", aliases=["kc"])
    resolver = ModelIdentityResolver([identity])

    resolution = resolver.resolve("kc")
    assert resolution.identity.long_form == "kilocode/claude-opus-4.6"
    assert "kc" not in resolver.long_forms()


# ── criterion 4: ambiguity is reported, never silently resolved ──────────


def test_ambiguous_token_returns_candidate_list():
    first = _identity(vendor="anthropic", model="claude-opus-4-6", aliases=["opus"])
    second = _identity(vendor="deepseek", model="deepseek-reasoner", aliases=["opus"])
    resolver = ModelIdentityResolver([first, second])

    resolution = resolver.resolve("opus")

    assert resolution.identity is None
    assert resolution.ambiguous == (
        "anthropic/claude-opus-4-6",
        "deepseek/deepseek-reasoner",
    )


def test_unknown_token_is_reported_unknown():
    resolver = ModelIdentityResolver([_identity(vendor="anthropic", model="claude-opus-4-6")])

    resolution = resolver.resolve("nonexistent-model-xyz")

    assert resolution.identity is None
    assert resolution.ambiguous == ()
    assert resolution.unknown is True


def test_resolution_is_case_and_whitespace_insensitive():
    identity = _identity(vendor="deepseek", model="deepseek-chat", aliases=["ds"])
    resolver = ModelIdentityResolver([identity])

    assert resolver.resolve("  DS  ").identity is identity
    assert resolver.resolve("DeepSeek/DeepSeek-Chat").identity is identity
