"""FastAPI route builders for the optional Anthropic bridge surface."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...bridges.anthropic import dispatch_anthropic_count_tokens, dispatch_anthropic_messages
from ...canonical import CanonicalChatExecutor


def build_anthropic_router(*, executor: CanonicalChatExecutor) -> APIRouter:
    """Return a detached Anthropic-compatible router.

    The router is intentionally not mounted by default. This keeps the current
    OpenAI-compatible runtime unchanged while making the future bridge ingress
    explicit and testable.
    """

    router = APIRouter(tags=["anthropic-bridge"])

    @router.post("/v1/messages")
    async def anthropic_messages(request: Request) -> JSONResponse:
        payload = await request.json()
        response = await dispatch_anthropic_messages(
            payload=payload,
            headers={key.lower(): value for key, value in request.headers.items()},
            executor=executor,
        )
        return JSONResponse(asdict(response))

    @router.post("/v1/messages/count_tokens")
    async def anthropic_count_tokens(request: Request) -> JSONResponse:
        payload = await request.json()
        response, extra_headers = dispatch_anthropic_count_tokens(
            payload=payload,
            headers={key.lower(): value for key, value in request.headers.items()},
        )
        return JSONResponse(asdict(response), headers=extra_headers)

    return router
