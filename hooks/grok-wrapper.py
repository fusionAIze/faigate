"""
faigate community hook: grok-wrapper
─────────────────────────────────────
Routes requests to xAI Grok automatically when:
  • The requested model name is a known Grok model (grok-3, grok-3-mini, …)
  • Any model name that starts with "grok-" is requested
  • The request header ``X-Faigate-Grok: 1`` (or ``true`` / ``yes``) is set

Required provider in config.yaml
─────────────────────────────────
  grok-xai:
    backend: openai-compat
    base_url: "${XAI_BASE_URL:-https://api.x.ai/v1}"
    api_key:  "${XAI_API_KEY}"
    model:    "grok-3"

Installation (community hook)
──────────────────────────────
  1. Copy this file to your community_hooks_dir:
       cp hooks/grok-wrapper.py ~/.config/faigate/hooks/
  2. Add the dir to request_hooks in config.yaml:
       request_hooks:
         community_hooks_dir: ~/.config/faigate/hooks
         hooks:
           - ...
           - grok-wrapper
  3. Set XAI_API_KEY in your environment or .env file.
  4. Restart faigate: brew services restart faigate
"""

from __future__ import annotations

from faigate.hooks import RequestHookContext, RequestHookResult

_PROVIDER_NAME = "grok-xai"
_KNOWN_GROK_MODELS = frozenset(
    {
        "grok",
        "grok-3",
        "grok-3-mini",
        "grok-3-fast",
        "grok-3-mini-fast",
        "grok-2",
        "grok-2-mini",
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


def register(register_fn) -> None:  # noqa: ANN001
    """Entry point called by faigate's community hook loader."""
    register_fn("grok-wrapper", _hook_grok_wrapper)
