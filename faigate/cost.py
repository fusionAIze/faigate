"""Cost projection utilities for fusionAIze Gate."""

from __future__ import annotations

from typing import Any

from .provider_catalog import (
    _get_packages_for_provider,
    _get_pricing_for_provider_and_model,
    get_offerings_catalog,
)


def estimate_provider_cost(
    provider_id: str,
    model_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, Any]:
    """Estimate cost for a specific provider and model.

    Args:
        provider_id: Provider identifier (e.g., 'deepseek-chat')
        model_id: Canonical model ID (e.g., 'deepseek/chat')
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Dictionary with cost breakdown:
        {
            'provider': provider_id,
            'model': model_id,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'input_cost_per_1m': float,
            'output_cost_per_1m': float,
            'input_cost': float,
            'output_cost': float,
            'total_cost': float,
            'source_type': str,
            'packages': list,  # applicable packages
            'credits_remaining': float,
            'cost_after_credits': float,
        }
    """
    # Get pricing
    pricing = _get_pricing_for_provider_and_model(provider_id, model_id)
    if not pricing:
        # No pricing available
        return {
            "provider": provider_id,
            "model": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost_per_1m": 0.0,
            "output_cost_per_1m": 0.0,
            "input_cost": 0.0,
            "output_cost": 0.0,
            "total_cost": 0.0,
            "source_type": "unknown",
            "packages": [],
            "credits_remaining": 0.0,
            "cost_after_credits": 0.0,
        }

    input_cost_per_1m = pricing.get("input", 0.0)
    output_cost_per_1m = pricing.get("output", 0.0)

    # Calculate costs
    input_cost = (input_tokens * input_cost_per_1m) / 1_000_000
    output_cost = (output_tokens * output_cost_per_1m) / 1_000_000
    total_cost = input_cost + output_cost

    # Get packages for provider
    packages = _get_packages_for_provider(provider_id)
    credits_remaining = 0.0
    for pkg in packages:
        total_credits = pkg.get("total_credits", 0)
        used_credits = pkg.get("used_credits", 0)
        credits_remaining += max(0, total_credits - used_credits)

    cost_after_credits = max(0.0, total_cost - credits_remaining)

    return {
        "provider": provider_id,
        "model": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_per_1m": input_cost_per_1m,
        "output_cost_per_1m": output_cost_per_1m,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "source_type": pricing.get("source_type", "unknown"),
        "packages": packages,
        "credits_remaining": credits_remaining,
        "cost_after_credits": cost_after_credits,
    }


def estimate_costs_across_providers(
    model_mix: dict[str, dict[str, int]],
    include_packages: bool = True,
) -> list[dict[str, Any]]:
    """Estimate costs across all providers for a given model mix.

    Args:
        model_mix: Dictionary mapping canonical model IDs to token counts.
            Example: {
                'deepseek/chat': {'input': 1000000, 'output': 500000},
                'openai/gpt-4o': {'input': 500000, 'output': 200000},
            }
        include_packages: Whether to factor in package credits.

    Returns:
        List of provider cost estimates, sorted by total cost (ascending).
    """
    # Get all offerings to know which providers offer which models
    offerings = get_offerings_catalog()

    # Build mapping from (provider, model) to offering
    provider_model_offerings = {}
    for offering_id, offering in offerings.items():
        provider_id = offering.get("provider_id")
        model_id = offering.get("model_id")
        if provider_id and model_id:
            provider_model_offerings.setdefault(provider_id, set()).add(model_id)

    results = []

    # For each provider that offers at least one model in the mix
    for provider_id, offered_models in provider_model_offerings.items():
        provider_total_input = 0
        provider_total_output = 0
        provider_total_cost = 0.0

        # Check which models in mix are offered by this provider
        for model_id, tokens in model_mix.items():
            if model_id in offered_models:
                input_tokens = tokens.get("input", 0)
                output_tokens = tokens.get("output", 0)
                estimate = estimate_provider_cost(provider_id, model_id, input_tokens, output_tokens)
                provider_total_input += input_tokens
                provider_total_output += output_tokens
                provider_total_cost += estimate["total_cost"]

        if provider_total_input == 0 and provider_total_output == 0:
            # Provider doesn't offer any models in the mix
            continue

        # Aggregate packages across all models (same provider)
        packages = _get_packages_for_provider(provider_id) if include_packages else []
        credits_remaining = 0.0
        for pkg in packages:
            total_credits = pkg.get("total_credits", 0)
            used_credits = pkg.get("used_credits", 0)
            credits_remaining += max(0, total_credits - used_credits)

        cost_after_credits = max(0.0, provider_total_cost - credits_remaining)

        results.append(
            {
                "provider": provider_id,
                "input_tokens": provider_total_input,
                "output_tokens": provider_total_output,
                "total_tokens": provider_total_input + provider_total_output,
                "total_cost": provider_total_cost,
                "credits_remaining": credits_remaining,
                "cost_after_credits": cost_after_credits,
                "packages": packages,
            }
        )

    # Sort by cost_after_credits ascending
    results.sort(key=lambda x: x["cost_after_credits"])
    return results


def format_cost_estimate(estimate: dict[str, Any]) -> str:
    """Format a cost estimate for human-readable output."""
    lines = []
    lines.append(f"Provider: {estimate['provider']}")
    lines.append(f"  Tokens: {estimate['input_tokens']:,} in, {estimate['output_tokens']:,} out")
    lines.append(f"  Cost: ${estimate['total_cost']:.4f}")
    if estimate["credits_remaining"] > 0:
        lines.append(f"  Credits remaining: ${estimate['credits_remaining']:.2f}")
        lines.append(f"  Cost after credits: ${estimate['cost_after_credits']:.4f}")
    if estimate.get("packages"):
        lines.append(f"  Packages: {len(estimate['packages'])}")
        for pkg in estimate["packages"][:2]:
            name = pkg.get("name", "unknown")
            remaining = pkg.get("remaining", 0)
            total = pkg.get("total_credits", 0)
            expiry = pkg.get("expiry_date", "none")
            lines.append(f"    - {name}: {remaining}/{total} credits (expires {expiry})")
    return "\n".join(lines)
