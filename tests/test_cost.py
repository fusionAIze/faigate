"""Acceptance tests for image-token handling in the cost model.

Covers the three TASK-C3 criteria:

1. a request with one image reports at most 384 image tokens
2. a request with three images scales image tokens linearly
3. models without ``image_tokens_max`` behave unchanged
"""

from __future__ import annotations

import faigate.cost as cost


def _patch_pricing(monkeypatch, pricing):
    monkeypatch.setattr(cost, "_get_pricing_for_provider_and_model", lambda provider, model: dict(pricing))
    monkeypatch.setattr(cost, "_get_packages_for_provider", lambda provider: [])


def test_one_image_reports_at_most_384_image_tokens(monkeypatch):
    _patch_pricing(
        monkeypatch,
        {
            "input": 0.44,
            "output": 1.32,
            "source_type": "provider-docs",
            "image_tokens_max": 384,
        },
    )

    estimate = cost.estimate_provider_cost("deepseek-flash-vision-exp", "deepseek/flash-vision-exp", image_count=1)

    assert estimate["image_tokens"] <= 384
    assert estimate["image_tokens"] == 384


def test_three_images_scale_image_tokens_linearly(monkeypatch):
    _patch_pricing(
        monkeypatch,
        {
            "input": 0.44,
            "output": 1.32,
            "source_type": "provider-docs",
            "image_tokens_max": 384,
        },
    )

    one = cost.estimate_provider_cost("deepseek-flash-vision-exp", "deepseek/flash-vision-exp", image_count=1)
    three = cost.estimate_provider_cost("deepseek-flash-vision-exp", "deepseek/flash-vision-exp", image_count=3)

    assert three["image_tokens"] == 3 * one["image_tokens"] == 1152


def test_images_bill_at_the_input_token_rate(monkeypatch):
    _patch_pricing(
        monkeypatch,
        {
            "input": 0.44,
            "output": 1.32,
            "source_type": "provider-docs",
            "image_tokens_max": 384,
        },
    )

    no_image = cost.estimate_provider_cost("deepseek-flash-vision-exp", "deepseek/flash-vision-exp")
    one_image = cost.estimate_provider_cost("deepseek-flash-vision-exp", "deepseek/flash-vision-exp", image_count=1)

    # 384 image tokens * 0.44 / 1_000_000
    expected_image_cost = 384 * 0.44 / 1_000_000
    assert abs((one_image["input_cost"] - no_image["input_cost"]) - expected_image_cost) < 1e-12


def test_model_without_image_tokens_max_is_unchanged(monkeypatch):
    _patch_pricing(
        monkeypatch,
        {
            "input": 0.44,
            "output": 1.32,
            "source_type": "provider-docs",
        },
    )

    estimate = cost.estimate_provider_cost(
        "deepseek-chat", "deepseek/chat", input_tokens=1000, output_tokens=100, image_count=3
    )

    # No image_tokens_max means images contribute nothing and cost is identity.
    assert estimate["image_tokens"] == 0
    assert estimate["input_tokens"] == 1000
    assert estimate["output_tokens"] == 100
    assert estimate["input_cost"] == 1000 * 0.44 / 1_000_000
    assert estimate["output_cost"] == 100 * 1.32 / 1_000_000
