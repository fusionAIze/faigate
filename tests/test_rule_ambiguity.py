"""Tests for ambiguous static rule detection.

When two static rules can both match the same ``model_requested`` value, the
router picks the first in file order.  These tests verify that the decision
reason reports the ambiguity so an operator can see both rule names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faigate.config import load_config
from faigate.router import Router


AMBIGUOUS_CONFIG = """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  gemini-flash:
    backend: openai-compat
    base_url: "https://example.invalid/v1"
    api_key: "x"
    model: "gemini-flash"
  deepseek-v4-flash:
    backend: openai-compat
    base_url: "https://example.invalid/v1"
    api_key: "x"
    model: "deepseek-v4-flash"
fallback_chain:
  - gemini-flash
static_rules:
  enabled: true
  rules:
    - match:
        model_requested:
          - flash
      name: explicit-flash
      route_to: gemini-flash
    - match:
        model_requested:
          - flash
      name: also-flash
      route_to: deepseek-v4-flash
"""


def _cfg(tmp_path, body: str) -> Config:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return load_config(str(path))


class TestAmbiguousStaticRules:
    """RED proof: these assertions fail when ambiguity is silent."""

    @pytest.mark.asyncio
    async def test_ambiguous_match_reason_mentions_both_rules(self, tmp_path):
        """When two rules match the same model_requested, both names appear."""
        router = Router(_cfg(tmp_path, AMBIGUOUS_CONFIG))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="flash",
        )
        assert d.layer == "static"
        assert d.rule_name == "explicit-flash"
        # RED PROOF: base code returns "Static rule 'explicit-flash' matched"
        # without mentioning the second matching rule.  This assertion fails
        # against the base.
        assert "also matched by" in d.reason, (
            f"Expected 'also matched by' in reason, got: {d.reason}"
        )
        assert "also-flash" in d.reason, (
            f"Expected 'also-flash' mentioned in reason, got: {d.reason}"
        )

    @pytest.mark.asyncio
    async def test_ambiguous_match_uses_first_rule(self, tmp_path):
        """First matching rule in file order is used even when ambiguous."""
        router = Router(_cfg(tmp_path, AMBIGUOUS_CONFIG))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="flash",
        )
        assert d.rule_name == "explicit-flash"
        assert d.provider_name == "gemini-flash"

    @pytest.mark.asyncio
    async def test_no_ambiguity_when_no_overlap(self, tmp_path):
        """Single-match rules produce a clean reason."""
        config = AMBIGUOUS_CONFIG.replace(
            "          - flash\n      name: also-flash",
            "          - other-model\n      name: also-flash",
        )
        router = Router(_cfg(tmp_path, config))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="flash",
        )
        assert d.rule_name == "explicit-flash"
        assert "also matched by" not in d.reason, (
            f"Expected clean reason without 'also matched by', got: {d.reason}"
        )

    @pytest.mark.asyncio
    async def test_ambiguous_match_logs_warning(self, tmp_path, caplog):
        """Ambiguity is logged at WARNING level."""
        caplog.set_level("WARNING", logger="faigate.router")
        router = Router(_cfg(tmp_path, AMBIGUOUS_CONFIG))
        await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="flash",
        )
        warnings = [
            rec.message for rec in caplog.records
            if "Ambiguous match in static rules" in rec.message
        ]
        assert len(warnings) == 1, (
            f"Expected exactly one WARNING about ambiguous static rules, "
            f"got {len(warnings)}: {warnings}"
        )
        assert "explicit-flash" in warnings[0]
        assert "also-flash" in warnings[0]


class TestAmbiguousConfigWarning:
    """Config-load warnings for ambiguous rule pairs."""

    def test_config_load_warns_on_ambiguous_rules(self, tmp_path, caplog):
        """Loading config with ambiguous rules logs a warning."""
        import logging

        caplog.set_level("WARNING", logger="faigate.config")
        _cfg(tmp_path, AMBIGUOUS_CONFIG)

        ambiguous = [
            r for r in caplog.records
            if "Ambiguous static rules" in r.getMessage()
        ]
        assert len(ambiguous) >= 1, (
            f"Expected at least one 'Ambiguous static rules' warning, "
            f"got {len(ambiguous)}"
        )
        msg = ambiguous[0].getMessage()
        assert "explicit-flash" in msg
        assert "also-flash" in msg
