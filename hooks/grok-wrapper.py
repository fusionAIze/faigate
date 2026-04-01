"""
faigate community hook: grok-wrapper
─────────────────────────────────────
Routes requests to a virtual grok-xai provider backed by a local OpenAI-compat
adapter (hooks/adapters/grok_api_adapter.py) that talks to Grok's web interface.
No official XAI API key required.

What this hook does
───────────────────
1. Registers a virtual ``grok-xai`` provider pointing to the local adapter
   at http://127.0.0.1:8091/v1  (no config.yaml entry required)
2. Intercepts requests for grok-* model names (or X-Faigate-Grok header)
   and injects prefer_providers: [grok-xai] so the router picks the virtual provider

Requirements
────────────
• Run the adapter before starting faigate:
    python hooks/adapters/grok_api_adapter.py

• Install Grok-Api (once):
    git clone https://github.com/fusionAIze/grok-api-hook ~/.config/faigate/grok-api
    pip install curl_cffi coincurve beautifulsoup4

• Optionally set a proxy (recommended to avoid anti-bot blocking):
    export GROK_PROXY=http://user:pass@host:port

Installation (community hook)
──────────────────────────────
1. Copy this file and the adapter to your config dir:
     cp hooks/grok-wrapper.py ~/.config/faigate/hooks/
     cp -r hooks/adapters       ~/.config/faigate/hooks/

2. Enable in config.yaml:
     request_hooks:
       enabled: true
       community_hooks_dir: ~/.config/faigate/hooks
       hooks:
         - prefer-provider-header
         - mode-override-header
         - grok-wrapper          # ← add this

3. Start the adapter, then restart faigate:
     python ~/.config/faigate/hooks/adapters/grok_api_adapter.py &
     brew services restart faigate

Environment variables
─────────────────────
  GROK_ADAPTER_HOST   default: 127.0.0.1
  GROK_ADAPTER_PORT   default: 8091
  GROK_PROXY          optional, e.g. http://user:pass@host:port
"""

from __future__ import annotations

import os

from faigate.hooks import RequestHookContext, RequestHookResult

_PROVIDER_NAME = "grok-xai"
_KNOWN_GROK_MODELS = frozenset(
    {
        "grok",
        "grok-3",
        "grok-3-auto",
        "grok-3-fast",
        "grok-4",
        "grok-4-mini",
        "grok-4-mini-thinking",
        "grok-4-mini-thinking-tahoe",
        "grok-2",
        "grok-vision-beta",
        "grok-beta",
    }
)


def _hook_grok_wrapper(context: RequestHookContext) -> RequestHookResult | None:
    """Inject grok-xai into prefer_providers when a Grok model or header is detected."""
    model = (context.model_requested or "").lower().strip()
    header = context.headers.get("x-faigate-grok", "").strip().lower()

    wants_grok_by_model = model in _KNOWN_GROK_MODELS or model.startswith("grok-")
    wants_grok_by_header = header in {"1", "true", "yes"}

    if not (wants_grok_by_model or wants_grok_by_header):
        return None

    reason = f"model={model}" if wants_grok_by_model else "x-faigate-grok header"
    return RequestHookResult(
        routing_hints={"prefer_providers": [_PROVIDER_NAME]},
        notes=[f"grok-wrapper: routing to {_PROVIDER_NAME} ({reason})"],
    )


def register(register_fn, register_provider_fn=None) -> None:  # noqa: ANN001
    """Entry point called by faigate's community hook loader."""
    register_fn("grok-wrapper", _hook_grok_wrapper)

    if register_provider_fn is None:
        return

    adapter_host = os.environ.get("GROK_ADAPTER_HOST", "127.0.0.1").strip()
    adapter_port = int(os.environ.get("GROK_ADAPTER_PORT", "8091"))
    adapter_url = f"http://{adapter_host}:{adapter_port}/v1"

    register_provider_fn(
        _PROVIDER_NAME,
        {
            "backend": "openai-compat",
            "base_url": adapter_url,
            # Dummy key — adapter does not validate authentication
            "api_key": "grok-web-no-key",
            "model": "grok-3-auto",
            "tier": "mid",
            "max_tokens": 8192,
            "timeout": {
                "connect_s": 15,
                "read_s": 120,  # Grok web is slower than direct API
            },
            "pricing": {
                "input": 0.0,
                "output": 0.0,
            },
            "cache": {
                "mode": "none",
            },
            "capabilities": {
                "cost_tier": "free",
                "latency_tier": "slow",
                "reasoning": True,
                "cloud": True,
                "local": False,
                "streaming": True,
            },
            "lane": {
                "name": "reasoning",
                "family": "xai",
                "canonical_model": "xai/grok-3",
                "cluster": "quality-coding",
                "benchmark_cluster": "quality-coding",
                "quality_tier": "high",
                "reasoning_strength": "high",
                "context_strength": "high",
                "tool_strength": "mid",
                "route_type": "virtual",
                "same_model_group": "xai/grok-3",
                "degrade_to": ["openai/gpt-4o", "anthropic/claude-sonnet"],
                "last_reviewed": "2026-03-25",
                "freshness_status": "fresh",
                "review_age_days": 0,
                "freshness_hint": (
                    f"Virtual provider via grok_api_adapter — no XAI API key required. Adapter at {adapter_url}"
                ),
            },
        },
    )
