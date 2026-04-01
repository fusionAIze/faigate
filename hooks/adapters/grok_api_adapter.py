#!/usr/bin/env python3
"""
Grok OpenAI-compat Adapter
───────────────────────────
Bridges faigate's virtual grok-xai provider to the web-based Grok client
(realasfngl/Grok-Api).  No official XAI API key required — uses Grok's web
interface via curl_cffi.

Exposes:
  GET  /v1/models               → list available Grok models
  POST /v1/chat/completions     → OpenAI-compat chat (streaming + non-streaming)

Usage
─────
  # 1. Install Grok-Api (once):
  git clone https://github.com/fusionAIze/grok-api-hook ~/.config/faigate/grok-api
  pip install curl_cffi coincurve beautifulsoup4

  # 2. Start the adapter (keep running alongside faigate):
  python hooks/adapters/grok_api_adapter.py

  # 3. Optionally set a proxy (recommended to avoid anti-bot detection):
  GROK_PROXY=http://user:pass@host:port python hooks/adapters/grok_api_adapter.py

Environment variables
─────────────────────
  GROK_API_DIR       Path to cloned Grok-Api repo  (default: ~/.config/faigate/grok-api)
  GROK_PROXY         HTTP proxy, e.g. http://user:pass@host:port  (optional but recommended)
  GROK_ADAPTER_HOST  Bind host  (default: 127.0.0.1)
  GROK_ADAPTER_PORT  Bind port  (default: 8091)

Model name mapping (OpenAI-style → Grok-Api internal)
──────────────────────────────────────────────────────
  grok-3 / grok-3-auto           → grok-3-auto
  grok-3-fast                    → grok-3-fast
  grok-4                         → grok-4
  grok-4-mini / grok-4-mini-*    → grok-4-mini-thinking-tahoe
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import sys
import time
import uuid

# ── Grok-Api path resolution ────────────────────────────────────────────────

_GROK_API_DIR = pathlib.Path(os.environ.get("GROK_API_DIR", "~/.config/faigate/grok-api")).expanduser().resolve()

if str(_GROK_API_DIR) not in sys.path:
    sys.path.insert(0, str(_GROK_API_DIR))

try:
    from core import Grok  # type: ignore[import]

    _GROK_AVAILABLE = True
except ImportError:
    _GROK_AVAILABLE = False

# ── FastAPI ──────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
_logger = logging.getLogger("grok-adapter")

_PROXY: str | None = os.environ.get("GROK_PROXY", "").strip() or None
_HOST: str = os.environ.get("GROK_ADAPTER_HOST", "127.0.0.1")
_PORT: int = int(os.environ.get("GROK_ADAPTER_PORT", "8091"))

# ── Model mapping ────────────────────────────────────────────────────────────

_MODEL_MAP: dict[str, str] = {
    "grok-3": "grok-3-auto",
    "grok-3-auto": "grok-3-auto",
    "grok-3-fast": "grok-3-fast",
    "grok-4": "grok-4",
    "grok-4-mini": "grok-4-mini-thinking-tahoe",
    "grok-4-mini-thinking": "grok-4-mini-thinking-tahoe",
    "grok-4-mini-thinking-tahoe": "grok-4-mini-thinking-tahoe",
    # Fallback: anything else → auto
}

_AVAILABLE_MODELS = list(_MODEL_MAP.keys())

# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Grok OpenAI Adapter",
    version="1.0.0",
    description="OpenAI-compatible adapter for Grok web (no XAI API key required)",
)

# ── Pydantic models ──────────────────────────────────────────────────────────


class _ChatMessage(BaseModel):
    role: str
    content: str | None = None


class _ChatCompletionRequest(BaseModel):
    model: str = "grok-3-auto"
    messages: list[_ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _messages_to_prompt(messages: list[_ChatMessage]) -> str:
    """Flatten an OpenAI messages array into a single Grok prompt string.

    System prompts are prepended in brackets; assistant turns are included as
    context so multi-turn conversations are preserved in a single call.
    """
    parts: list[str] = []
    for msg in messages:
        content = (msg.content or "").strip()
        if not content:
            continue
        if msg.role == "system":
            parts.append(f"[System instructions: {content}]")
        elif msg.role == "user":
            parts.append(content)
        elif msg.role == "assistant":
            parts.append(f"[Previous assistant response: {content}]")
    return "\n\n".join(parts)


def _make_completion_response(request_model: str, content: str) -> dict:
    """Build a non-streaming OpenAI chat completion response."""
    return {
        "id": f"chatcmpl-grok-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            # Grok-Api does not expose token counts
            "prompt_tokens": -1,
            "completion_tokens": -1,
            "total_tokens": -1,
        },
    }


async def _stream_tokens(request_model: str, tokens: list[str], fallback_content: str) -> object:
    """Yield OpenAI SSE chunks from Grok-Api's token list."""
    completion_id = f"chatcmpl-grok-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    # Use token stream when available; fall back to single content chunk
    emit_tokens = tokens if tokens else [fallback_content]

    for token in emit_tokens:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request_model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": token},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    # Final chunk signals end of stream
    final = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": request_model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


def _call_grok(grok_model: str, prompt: str) -> dict:
    """Blocking call to Grok-Api — run in executor to avoid blocking the event loop."""
    return Grok(model=grok_model, proxy=_PROXY).start_convo(prompt, extra_data=None)


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "xai-web",
                "description": f"Grok web model (via adapter) → {_MODEL_MAP[model_id]}",
            }
            for model_id in _AVAILABLE_MODELS
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: _ChatCompletionRequest):
    if not _GROK_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Grok-Api not found at {_GROK_API_DIR}. "
                "Install with: "
                f"git clone https://github.com/fusionAIze/grok-api-hook {_GROK_API_DIR} "
                "&& pip install curl_cffi coincurve beautifulsoup4"
            ),
        )

    grok_model = _MODEL_MAP.get(req.model.lower(), "grok-3-auto")
    prompt = _messages_to_prompt(req.messages)

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="No non-empty user message found")

    _logger.info("→ Grok [%s] prompt=%d chars proxy=%s", grok_model, len(prompt), bool(_PROXY))

    try:
        loop = asyncio.get_event_loop()
        result: dict = await loop.run_in_executor(None, _call_grok, grok_model, prompt)
    except Exception as exc:
        _logger.error("Grok-Api call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Grok-Api error: {exc}") from exc

    if "error" in result:
        _logger.error("Grok-Api returned error: %s", result["error"])
        raise HTTPException(status_code=502, detail=str(result["error"]))

    content: str = result.get("response") or ""
    tokens: list[str] = result.get("stream_response") or []

    _logger.info("← Grok [%s] response=%d chars tokens=%d", grok_model, len(content), len(tokens))

    if req.stream:
        return StreamingResponse(
            _stream_tokens(req.model, tokens, content),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return JSONResponse(_make_completion_response(req.model, content))


@app.get("/health")
async def health():
    return {
        "status": "ok" if _GROK_AVAILABLE else "degraded",
        "grok_api_available": _GROK_AVAILABLE,
        "grok_api_dir": str(_GROK_API_DIR),
        "proxy_configured": bool(_PROXY),
        "adapter_port": _PORT,
        "models": _AVAILABLE_MODELS,
    }


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("─" * 60)
    print("  Grok OpenAI Adapter  (faigate community hook)")
    print("─" * 60)
    if _GROK_AVAILABLE:
        print(f"  ✓ Grok-Api found at {_GROK_API_DIR}")
    else:
        print(f"  ✗ Grok-Api NOT found at {_GROK_API_DIR}")
        print()
        print("  Install with:")
        print(f"    git clone https://github.com/fusionAIze/grok-api-hook {_GROK_API_DIR}")
        print("    pip install curl_cffi coincurve beautifulsoup4")

    if _PROXY:
        print(f"  Proxy: {_PROXY}")
    else:
        print("  ⚠  No GROK_PROXY set — may be blocked by Grok anti-bot detection")

    print(f"  Listening on http://{_HOST}:{_PORT}/v1")
    print("─" * 60)

    uvicorn.run(app, host=_HOST, port=_PORT, log_level="info")
