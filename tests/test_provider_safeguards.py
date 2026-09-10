"""Provider-level safeguard tests for ChatGPT plan-tier and DeepSeek V4 thinking.

Two regressions from the 2026-04-26 incident:

1. The Codex effective-model mapping unconditionally translated `gpt-5.4` →
   `gpt-5-codex`, which the chatgpt.com Codex backend rejects for ChatGPT
   Plus accounts (Pro-only model). The new mapping reads the cached
   `~/.codex/auth.json` JWT once and maps to the variant the account can
   actually use.

2. DeepSeek V4 made `reasoning_content` round-trip mandatory whenever
   thinking mode is active. OpenCode/Codenomad and most generic
   openai-compat clients don't track that field, so any multi-turn request
   would 400 with "The reasoning_content in the thinking mode must be
   passed back to the API." The send-path now auto-disables thinking by
   sending the V4-correct `thinking: {type: "disabled"}` ThinkingOptions
   struct (the boolean form is silently ignored upstream).
"""

# ruff: noqa: E402

from __future__ import annotations

# Use the genuine httpx: provider clients are constructed but never make a
# request in these tests, so no network client is needed. A global stub here
# would leak into every module collected afterwards.
import httpx  # noqa: F401  (genuine package; see tests/conftest.py)
import pytest

import faigate.providers as providers_module  # noqa: E402
from faigate.providers import ProviderBackend  # noqa: E402


def _make_deepseek_backend(family: str = "deepseek") -> ProviderBackend:
    cfg = {
        "backend": "openai-compat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "fake-key",
        "model": "deepseek-v4-flash",
        "max_tokens": 256,
        "lane": {
            "family": family,
            "name": "workhorse",
            "canonical_model": "deepseek/v4-flash",
            "route_type": "direct",
        },
    }
    return ProviderBackend("deepseek-test", cfg)


def _install_capture_post(backend: ProviderBackend) -> dict:
    """Replace _client.post with an async stub that captures the JSON body."""
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        headers: dict = {}
        text = ""

        def json(self):
            return {
                "id": "stub",
                "model": backend.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    async def _fake_post(url, json=None, **kw):
        captured.update(json or {})
        return _FakeResp()

    backend._client.post = _fake_post  # type: ignore[attr-defined]
    return captured


# ── DeepSeek V4 thinking-mode safeguard ──────────────────────────────────────


class TestDeepSeekThinkingSafeguard:
    @pytest.mark.asyncio
    async def test_assistant_without_reasoning_content_disables_thinking(self):
        """Multi-turn with at least one assistant turn missing reasoning_content
        must auto-disable thinking via the ThinkingOptions struct that V4
        actually accepts. Without this, DeepSeek 400s every follow-up turn."""
        backend = _make_deepseek_backend()
        captured = _install_capture_post(backend)

        await backend.complete(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hi back"},  # no reasoning_content
                {"role": "user", "content": "reply pong"},
            ]
        )

        assert captured.get("thinking") == {"type": "disabled"}
        # And the legacy boolean form must NOT leak in — DeepSeek silently
        # ignores it, which would re-introduce the bug we just fixed.
        assert "enable_thinking" not in captured

    @pytest.mark.asyncio
    async def test_single_turn_keeps_thinking_active(self):
        """No prior assistant turn = nothing to round-trip, so we leave
        thinking on its default (active) and let DeepSeek do its job."""
        backend = _make_deepseek_backend()
        captured = _install_capture_post(backend)

        await backend.complete([{"role": "user", "content": "hi"}])

        assert "thinking" not in captured

    @pytest.mark.asyncio
    async def test_assistant_with_reasoning_content_keeps_thinking_active(self):
        """If the client *does* track reasoning_content (proper V4 client),
        we trust it and let thinking stay active for full reasoning fidelity."""
        backend = _make_deepseek_backend()
        captured = _install_capture_post(backend)

        await backend.complete(
            [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": "hi back",
                    "reasoning_content": "thought process here",
                },
                {"role": "user", "content": "reply pong"},
            ]
        )

        assert "thinking" not in captured

    @pytest.mark.asyncio
    async def test_safeguard_does_not_apply_to_non_deepseek_lanes(self):
        """The safeguard is DeepSeek-V4-specific. Other openai-compat lanes
        (kilocode, blackbox, openrouter) must not accidentally inherit it."""
        backend = _make_deepseek_backend(family="kilocode")
        captured = _install_capture_post(backend)

        await backend.complete(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hi back"},
                {"role": "user", "content": "reply pong"},
            ]
        )

        assert "thinking" not in captured

    @pytest.mark.asyncio
    async def test_extra_body_overrides_safeguard(self):
        """Operator can opt out of the auto-safeguard via request extra_body
        for advanced workflows that *do* want thinking on with reasoning_content
        threading. The merge order in providers.py guarantees explicit wins."""
        backend = _make_deepseek_backend()
        captured = _install_capture_post(backend)

        await backend.complete(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hi back"},
                {"role": "user", "content": "reply pong"},
            ],
            extra_body={"thinking": {"type": "enabled"}},
        )

        assert captured.get("thinking") == {"type": "enabled"}


# ── ChatGPT plan-tier-aware Codex model alias mapping ────────────────────────


class TestCodexEffectiveModel:
    """`_codex_effective_model` must adapt to the user's ChatGPT plan tier.

    The mapping was previously `gpt-5.4` → `gpt-5-codex` unconditionally,
    which works for Pro subscribers but 400s Plus accounts (the chatgpt.com
    backend rejects gpt-5-codex with `"not supported when using Codex with
    a ChatGPT account"`).
    """

    @pytest.fixture(autouse=True)
    def reset_plan_cache(self):
        """The plan tier is cached at module level for the process lifetime;
        clear it between tests so each test sees its own fixture."""
        providers_module._CODEX_PLAN_TIER_CACHE = None
        yield
        providers_module._CODEX_PLAN_TIER_CACHE = None

    def _make_backend(self) -> ProviderBackend:
        cfg = {
            "backend": "openai-compat",
            "base_url": "https://chatgpt.com/backend-api/codex/responses",
            "api_key": "fake",
            "model": "gpt-5.4",
            "transport": {"profile": "oauth-codex"},
        }
        return ProviderBackend("openai-codex-test", cfg)

    def test_pro_plan_maps_to_gpt5_codex(self, monkeypatch):
        monkeypatch.setattr(providers_module, "_CODEX_PLAN_TIER_CACHE", "pro", raising=False)
        backend = self._make_backend()
        assert backend._codex_effective_model("gpt-5.4") == "gpt-5-codex"

    def test_plus_plan_maps_to_gpt5_codex_mini(self, monkeypatch):
        monkeypatch.setattr(providers_module, "_CODEX_PLAN_TIER_CACHE", "plus", raising=False)
        backend = self._make_backend()
        assert backend._codex_effective_model("gpt-5.4") == "gpt-5-codex-mini"

    def test_unknown_plan_passes_raw_model_through(self, monkeypatch):
        """Unknown plan tier (free, expired, missing auth.json) → pass the
        original model name and let the upstream reject explicitly."""
        monkeypatch.setattr(providers_module, "_CODEX_PLAN_TIER_CACHE", "unknown", raising=False)
        backend = self._make_backend()
        assert backend._codex_effective_model("gpt-5.4") == "gpt-5.4"

    def test_other_aliases_unaffected_by_plan_tier(self, monkeypatch):
        """The 5.3-codex variants follow a different rule (always collapse to
        the canonical `gpt-5.3-codex`) and must not regress with the plan-aware
        change applied to `gpt-5.4`."""
        monkeypatch.setattr(providers_module, "_CODEX_PLAN_TIER_CACHE", "plus", raising=False)
        backend = self._make_backend()
        assert backend._codex_effective_model("gpt-5.3-codex-high") == "gpt-5.3-codex"
        assert backend._codex_effective_model("gpt-5.3-codex-xhigh") == "gpt-5.3-codex"
        assert backend._codex_effective_model("gpt-5.3-codex-low") == "gpt-5.3-codex"
        # Models not in either rule pass through unchanged.
        assert backend._codex_effective_model("gpt-5.1-codex-mini") == "gpt-5.1-codex-mini"


class TestCodexPlanTierDetection:
    """`_detect_codex_chatgpt_plan_tier` parses ~/.codex/auth.json once."""

    @pytest.fixture(autouse=True)
    def reset_plan_cache(self):
        providers_module._CODEX_PLAN_TIER_CACHE = None
        yield
        providers_module._CODEX_PLAN_TIER_CACHE = None

    def _write_auth(self, tmp_path, plan_type: str | None) -> None:
        """Write a minimal auth.json with a synthetic id_token JWT carrying
        the ChatGPT plan claim. The signature is meaningless — the helper
        only base64-decodes the payload, never verifies."""
        import base64
        import json as _json

        if plan_type is None:
            payload = {"https://api.openai.com/auth": {}}
        else:
            payload = {"https://api.openai.com/auth": {"chatgpt_plan_type": plan_type}}
        encoded = base64.urlsafe_b64encode(_json.dumps(payload).encode()).rstrip(b"=").decode()
        token = f"header.{encoded}.signature"
        auth_dir = tmp_path / ".codex"
        auth_dir.mkdir(exist_ok=True)
        (auth_dir / "auth.json").write_text(_json.dumps({"tokens": {"id_token": token}}))

    def test_detects_pro_plan_from_jwt(self, tmp_path, monkeypatch):
        self._write_auth(tmp_path, "pro")
        monkeypatch.setenv("HOME", str(tmp_path))
        # pathlib.Path.home() reads $HOME on POSIX
        assert providers_module._detect_codex_chatgpt_plan_tier() == "pro"

    def test_detects_plus_plan_from_jwt(self, tmp_path, monkeypatch):
        self._write_auth(tmp_path, "plus")
        monkeypatch.setenv("HOME", str(tmp_path))
        assert providers_module._detect_codex_chatgpt_plan_tier() == "plus"

    def test_missing_auth_file_returns_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert providers_module._detect_codex_chatgpt_plan_tier() == "unknown"

    def test_malformed_token_returns_unknown(self, tmp_path, monkeypatch):
        import json as _json

        auth_dir = tmp_path / ".codex"
        auth_dir.mkdir()
        (auth_dir / "auth.json").write_text(_json.dumps({"tokens": {"id_token": "not-a-jwt"}}))
        monkeypatch.setenv("HOME", str(tmp_path))
        assert providers_module._detect_codex_chatgpt_plan_tier() == "unknown"

    def test_result_is_cached_across_calls(self, tmp_path, monkeypatch):
        """Cache is the whole point of the helper — the JWT decode happens
        on every Codex request otherwise."""
        self._write_auth(tmp_path, "plus")
        monkeypatch.setenv("HOME", str(tmp_path))
        first = providers_module._detect_codex_chatgpt_plan_tier()
        # Now write a different plan and assert we still see the cached one.
        self._write_auth(tmp_path, "pro")
        # tmp_path was overwritten — the cache should still serve "plus".
        # (Note: _write_auth mkdirs which would fail on second call; rewrite the file.)
        # Skip the cache-vs-disk delta check; the API contract is "same result
        # without re-reading", which is what we verify here.
        second = providers_module._detect_codex_chatgpt_plan_tier()
        assert first == second == "plus"
