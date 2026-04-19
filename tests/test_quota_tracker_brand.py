"""Coverage for the v1.3 brand pivot in ``faigate.quota_tracker``.

Pins the contract the quota widget + Gate Bar read from: every ``QuotaStatus``
carries ``brand`` / ``brand_slug`` / ``identity``, and rolling-window / daily
packages also expose a ``pace_delta`` so the UI can render the pace marker.

See ``docs/GATE-BAR-DESIGN.md`` §1 (naming pivot) and §4 (pace computation).
"""

from __future__ import annotations

from datetime import UTC, datetime

from faigate.quota_tracker import (
    _derive_brand,
    _derive_identity,
    _slugify_brand,
    compute_quota_status,
)


class TestBrandFallback:
    def test_known_provider_groups_map_to_branded_names(self):
        assert _derive_brand("anthropic") == "Claude"
        assert _derive_brand("openai") == "Codex"
        assert _derive_brand("gemini") == "Gemini"
        assert _derive_brand("deepseek") == "DeepSeek"
        assert _derive_brand("kilocode") == "Kilo Code"

    def test_unknown_group_titlecases_gracefully(self):
        # Not in the table → title-case fallback so we don't show lowercase
        # noise in the widget.
        assert _derive_brand("foobar") == "Foobar"

    def test_slug_is_url_safe_kebab_case(self):
        assert _slugify_brand("Kilo Code") == "kilo-code"
        assert _slugify_brand("Claude") == "claude"
        assert _slugify_brand("OpenRouter") == "openrouter"
        # Repeated spaces / punctuation collapse to single hyphens.
        assert _slugify_brand("  Some  Brand! ") == "some-brand"


class TestIdentity:
    def test_env_var_credential_is_flagged_as_api_key(self):
        assert _derive_identity("ANTHROPIC_API_KEY") == {
            "login_method": "API key",
            "credential": "ANTHROPIC_API_KEY",
        }

    def test_oauth_subject_is_flagged_as_oauth(self):
        assert _derive_identity("claude-code") == {
            "login_method": "OAuth",
            "credential": "claude-code",
        }

    def test_missing_credential_returns_none(self):
        # Packages without `_requires_credential` (e.g. always-on local
        # providers) get no identity line instead of a placeholder.
        assert _derive_identity(None) is None
        assert _derive_identity("") is None


class TestComputeQuotaStatusBrand:
    """End-to-end: catalog dicts resolve to QuotaStatus with brand+pace."""

    def test_credits_package_carries_brand_and_null_pace(self):
        pkg = {
            "package_id": "deepseek-pay-as-you-go",
            "provider_id": "deepseek-chat",
            "provider_group": "deepseek",
            "brand": "DeepSeek",
            "brand_slug": "deepseek",
            "package_type": "credits",
            "total_credits": 28.42,
            "used_credits": 0.0,
            "_requires_credential": "DEEPSEEK_API_KEY",
        }
        status = compute_quota_status(pkg)
        assert status.brand == "DeepSeek"
        assert status.brand_slug == "deepseek"
        # Credits packages lean on projected_days_left, not pace.
        assert status.pace_delta is None
        assert status.elapsed_ratio is None
        assert status.identity == {
            "login_method": "API key",
            "credential": "DEEPSEEK_API_KEY",
        }

    def test_rolling_window_fresh_session_has_zero_pace(self):
        # No request log → window just started, nothing used → pace = 0.0.
        pkg = {
            "package_id": "anthropic-pro-5h-session",
            "provider_id": "anthropic-claude",
            "provider_group": "anthropic",
            "brand": "Claude",
            "brand_slug": "claude",
            "package_type": "rolling_window",
            "window_hours": 5,
            "limit_per_window": 100,
            "_requires_credential": "claude-code",
        }
        status = compute_quota_status(pkg)
        assert status.brand == "Claude"
        assert status.brand_slug == "claude"
        assert status.pace_delta == 0.0
        assert status.elapsed_ratio == 0.0
        assert status.identity == {"login_method": "OAuth", "credential": "claude-code"}

    def test_daily_package_pace_is_negative_late_in_the_day(self):
        # Force ``now`` to 22:00 UTC. With 0 requests used on a 1500/day
        # budget, elapsed_ratio ≈ 0.92 and used_ratio = 0, so pace is
        # strongly negative (very under pace).
        pkg = {
            "package_id": "gemini-free-daily",
            "provider_id": "gemini-flash",
            "provider_group": "gemini",
            "brand": "Gemini",
            "brand_slug": "gemini",
            "package_type": "daily",
            "limit_per_day": 1500,
            "_requires_credential": "GEMINI_API_KEY",
        }
        fixed_now = datetime(2026, 4, 19, 22, 0, tzinfo=UTC)
        status = compute_quota_status(pkg, now=fixed_now)
        assert status.brand == "Gemini"
        assert status.pace_delta is not None
        # elapsed ~22/24 = 0.9167, used_ratio = 0.0 → pace_delta ~ -0.9167.
        assert status.pace_delta < -0.9
        assert status.elapsed_ratio is not None
        assert 0.9 < status.elapsed_ratio < 0.95

    def test_brand_falls_back_when_catalog_omits_field(self):
        # Simulates a pre-v1.3 catalog entry — no brand/brand_slug. The
        # fallback table + slug derivation must keep the UI contract alive.
        pkg = {
            "package_id": "legacy-anthropic",
            "provider_id": "anthropic-claude",
            "provider_group": "anthropic",
            "package_type": "rolling_window",
            "window_hours": 5,
            "limit_per_window": 100,
        }
        fixed_now = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        status = compute_quota_status(pkg, now=fixed_now)
        assert status.brand == "Claude"
        assert status.brand_slug == "claude"

    def test_status_dict_exposes_new_fields_for_api(self):
        # The /api/quotas handler just calls ``.to_dict()`` — make sure the
        # fields the widget depends on actually round-trip through asdict().
        pkg = {
            "package_id": "qwen-free-daily",
            "provider_id": "qwen-portal",
            "provider_group": "qwen",
            "brand": "Qwen",
            "brand_slug": "qwen",
            "package_type": "daily",
            "limit_per_day": 2000,
            "_requires_credential": "qwen-portal",
        }
        fixed_now = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        data = compute_quota_status(pkg, now=fixed_now).to_dict()
        assert data["brand"] == "Qwen"
        assert data["brand_slug"] == "qwen"
        assert data["pace_delta"] is not None
        assert data["elapsed_ratio"] is not None
        assert data["identity"]["login_method"] == "OAuth"
