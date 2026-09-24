"""Acceptance tests for faigate.capability_probe.

FAI-238-A: Each provider uses a different field name for the context window
in its /models response. The mapping lives in the curated catalog, and the
probe extracts the value by walking a dotted field path.
"""

from __future__ import annotations

import json
from pathlib import Path

from faigate.capability_probe import extract_context_window

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "models_probe"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / f"{name}_models.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_byteplus_token_limits_context_window() -> None:
    """BytePlus nests the window under token_limits.context_window."""
    data = _load_fixture("byteplus")
    result = extract_context_window(data, "token_limits.context_window")
    assert result == 131072


def test_deepseek_context_window() -> None:
    """DeepSeek uses a top-level context_window field."""
    data = _load_fixture("deepseek")
    result = extract_context_window(data, "context_window")
    assert result == 65536


def test_openrouter_context_length() -> None:
    """OpenRouter calls it context_length."""
    data = _load_fixture("openrouter")
    result = extract_context_window(data, "context_length")
    assert result == 200000


def test_mistral_max_context_length() -> None:
    """Mistral uses max_context_length."""
    data = _load_fixture("mistral")
    result = extract_context_window(data, "max_context_length")
    assert result == 131072


def test_nvidia_provides_no_context_window() -> None:
    """NVIDIA's /models response carries no context window field."""
    data = _load_fixture("nvidia")
    result = extract_context_window(data, "context_window")
    assert result is None


def test_missing_field_returns_none() -> None:
    """A field path with no match in the data returns None."""
    result = extract_context_window({"data": []}, "context_window")
    assert result is None


def test_empty_data_returns_none() -> None:
    """Empty dict returns None for any path."""
    result = extract_context_window({}, "context_window")
    assert result is None


def test_nested_field_with_intermediate_none() -> None:
    """A dotted path where an intermediate segment is missing returns None."""
    result = extract_context_window({"outer": None}, "outer.inner.key")
    assert result is None


def test_non_integer_leaf_returns_none() -> None:
    """A string leaf value is not a context window."""
    result = extract_context_window({"key": "not_a_number"}, "key")
    assert result is None


def test_probe_without_mapping_is_skipped() -> None:
    """An empty field path means the provider has no mapping — skip, don't guess."""
    result = extract_context_window({"data": [{"context_window": 4096}]}, "")
    assert result is None
