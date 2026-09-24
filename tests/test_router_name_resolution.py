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
