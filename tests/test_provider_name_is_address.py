"""Tests that a provider name is addressable even without a static rule.

19 of 37 providers have no static rule matching their own name.  Without an
explicit name check in the route path, the heuristic layer claims the request
(e.g. ``simple-query`` matching ``"hello"`` routes to ``gemini-flash-lite``)
and the requested provider name is silently ignored.

The identity gate (``model_requested_is_accepted``) already accepts provider
names by checking ``normalized in provider_map``.  The route path must agree.
"""

import pytest

from faigate.config import load_config
from faigate.router import Router


def _cfg(tmp_path, body: str):
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return load_config(str(path))


BODY = """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  gemini-flash-lite:
    backend: openai-compat
    base_url: "https://example.invalid/v1"
    api_key: "x"
    model: "gemini-flash-lite"
  anthropic-haiku:
    backend: openai-compat
    base_url: "https://example.invalid/v1"
    api_key: "x"
    model: "anthropic-haiku"
  openai-gpt4o:
    backend: openai-compat
    base_url: "https://example.invalid/v1"
    api_key: "x"
    model: "openai-gpt4o"
fallback_chain:
  - gemini-flash-lite
heuristic_rules:
  enabled: true
  rules:
    - match:
        message_keywords:
          any_of:
            - hello
            - hi
          min_matches: 1
      name: simple-query
      route_to: gemini-flash-lite
    - match:
        fallthrough: true
      name: general-default
      route_to: gemini-flash-lite
"""


class TestProviderNameIsItsAddress:
    """RED proof: provider names without static rules are ignored by heuristics.

    Each test sends a request naming a provider that exists in the config but
    has no static rule.  The heuristic layer (simple-query) matches "hello"
    and routes to gemini-flash-lite instead — unless the route path checks
    the requested name against configured providers before consulting heuristics.
    """

    @pytest.mark.asyncio
    async def test_anthropic_haiku_routes_to_anthropic_haiku(self, tmp_path):
        """anthropic-haiku has no static rule — name is the only address."""
        router = Router(_cfg(tmp_path, BODY))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="anthropic-haiku",
        )
        assert d.provider_name == "anthropic-haiku", (
            f"Expected anthropic-haiku, got {d.provider_name} "
            f"(layer: {d.layer}, rule: {d.rule_name})"
        )

    @pytest.mark.asyncio
    async def test_openai_gpt4o_routes_to_openai_gpt4o(self, tmp_path):
        """openai-gpt4o has no static rule — name is the only address."""
        router = Router(_cfg(tmp_path, BODY))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="openai-gpt4o",
        )
        assert d.provider_name == "openai-gpt4o", (
            f"Expected openai-gpt4o, got {d.provider_name} "
            f"(layer: {d.layer}, rule: {d.rule_name})"
        )

    # --- Guard against false positives -------------------------------
    #
    # The named-provider check must NOT claim "auto" or the empty string,
    # so the heuristic layer still wins when no explicit name is given.

    @pytest.mark.asyncio
    async def test_unnamed_request_still_uses_heuristics(self, tmp_path):
        """Without a model name the heuristic layer still wins."""
        router = Router(_cfg(tmp_path, BODY))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="",
        )
        assert d.provider_name == "gemini-flash-lite", (
            f"Expected gemini-flash-lite (heuristic) for unnamed request, "
            f"got {d.provider_name} (layer: {d.layer})"
        )

    @pytest.mark.asyncio
    async def test_auto_request_still_uses_heuristics(self, tmp_path):
        """With model_requested='auto' the heuristic layer still wins."""
        router = Router(_cfg(tmp_path, BODY))
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="auto",
        )
        assert d.provider_name == "gemini-flash-lite", (
            f"Expected gemini-flash-lite (heuristic) for auto request, "
            f"got {d.provider_name} (layer: {d.layer})"
        )
