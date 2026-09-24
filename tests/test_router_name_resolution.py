"""Tests for exact model name resolution in static routing.

The static router uses substring matching (p in ctx.model_requested), which
causes collisions: model_requested="deepseek-v4-flash" matches pattern
"flash" in the explicit-flash rule and gets misrouted to gemini-flash.

These tests verify that the fix (exact match) resolves such collisions.
"""

from pathlib import Path

import pytest

from faigate.config import load_config
from faigate.router import Router


@pytest.fixture
def router():
    return Router(load_config(Path(__file__).parent.parent / "config.yaml"))


class TestExactModelNameResolution:
    """RED proof: these assertions fail with substring matching."""

    @pytest.mark.asyncio
    async def test_deepseek_v4_flash_routes_to_deepseek_v4_flash(self, router):
        """deepseek-v4-flash must route to deepseek-v4-flash, not gemini-flash.

        With substring matching, "flash" in "deepseek-v4-flash" is True, so
        the explicit-flash rule (route_to: gemini-flash) matches first.
        """
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="deepseek-v4-flash",
        )
        assert d.provider_name == "deepseek-v4-flash", (
            f"Expected deepseek-v4-flash, got {d.provider_name} (rule: {d.rule_name})"
        )


# --- FAI-244-A, remaining acceptance criteria -------------------------------
#
# Criterion 2: substring matching stays available, but only when a rule asks
# for it by name. Criterion 3: the switch from substring to equality must say
# which addresses it costs, because a route that disappears without a word is
# the failure this change exists to remove.


def _cfg(tmp_path, body: str):
    from faigate.config import load_config

    path = tmp_path / "config.yaml"
    path.write_text(body)
    return load_config(str(path))


BODY = """
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
"""


def test_a_fragment_only_matches_when_the_rule_asks_for_it(tmp_path):
    """model_requested_contains is the opt-in for the old behaviour."""
    from faigate.router import Router

    exact = Router(_cfg(tmp_path, BODY))
    assert exact.static_rule_for_model_requested("deepseek-v4-flash") is None, (
        "'flash' must no longer claim 'deepseek-v4-flash' through model_requested"
    )

    loose = Router(_cfg(tmp_path, BODY.replace("model_requested:", "model_requested_contains:")))
    rule = loose.static_rule_for_model_requested("deepseek-v4-flash")
    assert rule is not None and rule["name"] == "explicit-flash", (
        "model_requested_contains must still claim it — that is what the key is for"
    )


def test_the_switch_names_every_address_it_costs(tmp_path):
    """A claim dropped by the switch is reported, never dropped in silence."""
    from faigate.router import report_substring_only_matches

    cfg = _cfg(tmp_path, BODY)
    findings = report_substring_only_matches(cfg.static_rules, cfg.providers)
    lost = {name for name, _rule, _token in findings}
    assert "deepseek-v4-flash" in lost, "the switch drops explicit-flash's claim on deepseek-v4-flash and must say so"
    assert "gemini-flash" in lost, (
        "explicit-flash routes TO gemini-flash but only ever claimed the address "
        "'gemini-flash' by substring, so that claim is lost too — this is the live "
        "case measured on 2026-09-24, where gemini-flash fell through to "
        "gemini-flash-lite after the switch"
    )


def test_the_reporter_is_quiet_when_nothing_changes(tmp_path):
    """Guard against a reporter that always finds something."""
    from faigate.router import report_substring_only_matches

    body = BODY.replace("          - flash\n", "          - gemini-flash\n")
    cfg = _cfg(tmp_path, body)
    assert report_substring_only_matches(cfg.static_rules, cfg.providers) == [], (
        "with exact tokens nothing is lost — a reporter that still speaks is broken"
    )
