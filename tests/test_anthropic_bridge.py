"""Tests for the Anthropic bridge scaffolding."""

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from faigate.api.anthropic import build_anthropic_router
from faigate.api.anthropic.models import (
    AnthropicMessagesRequest,
    parse_anthropic_messages_request,
)
from faigate.bridges.anthropic import (
    anthropic_request_to_canonical,
    canonical_response_to_anthropic,
)
from faigate.canonical import CanonicalChatResponse, CanonicalResponseMessage


class _FakeExecutor:
    def __init__(self):
        self.last_request = None

    async def execute_canonical_chat(self, request):
        self.last_request = request
        return CanonicalChatResponse(
            response_id="msg_test",
            model="anthropic/claude-sonnet-4.6",
            provider="anthropic-direct",
            message=CanonicalResponseMessage(content="bridge ok"),
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 4},
        )


def test_parse_anthropic_messages_request_accepts_string_content():
    request = parse_anthropic_messages_request(
        {
            "model": "claude-sonnet",
            "system": "Stay concise",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        }
    )

    assert isinstance(request, AnthropicMessagesRequest)
    assert request.messages[0].content[0].type == "text"
    assert request.messages[0].content[0].text == "hello"


def test_anthropic_request_maps_to_canonical_and_openai_body():
    wire_request = parse_anthropic_messages_request(
        {
            "model": "claude-sonnet",
            "system": "Use markdown",
            "messages": [{"role": "user", "content": "Explain the diff"}],
            "tools": [
                {
                    "name": "lookup_doc",
                    "description": "Load one doc",
                    "input_schema": {"type": "object"},
                }
            ],
            "metadata": {"source": "claude-code"},
        }
    )

    canonical = anthropic_request_to_canonical(
        wire_request,
        headers={"x-faigate-client": "claude-code"},
    )
    openai_body = canonical.to_openai_body()

    assert canonical.client == "claude-code"
    assert canonical.surface == "anthropic-messages"
    assert canonical.requested_model == "claude-sonnet"
    assert canonical.tools[0].name == "lookup_doc"
    assert openai_body["messages"][0] == {"role": "system", "content": "Use markdown"}
    assert openai_body["messages"][1]["content"] == "Explain the diff"


def test_detached_router_runs_bridge_dispatch():
    executor = _FakeExecutor()
    response = TestClient(_build_test_app(executor)).post(
        "/v1/messages",
        json={
            "model": "claude-opus",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"x-faigate-client": "claude-code"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "message"
    assert payload["content"][0]["text"] == "bridge ok"
    assert executor.last_request is not None
    assert executor.last_request.client == "claude-code"
    assert executor.last_request.surface == "anthropic-messages"


def test_canonical_response_maps_back_to_anthropic_blocks():
    response = canonical_response_to_anthropic(
        CanonicalChatResponse(
            response_id="msg_back",
            model="anthropic/claude-opus-4.6",
            provider="kilo-opus",
            message=CanonicalResponseMessage(
                content=[{"type": "text", "text": "done"}],
            ),
            stop_reason="end_turn",
        ),
        requested_model="claude-opus",
    )

    payload = asdict(response)
    assert payload["id"] == "msg_back"
    assert payload["content"][0]["text"] == "done"
    assert payload["metadata"]["provider"] == "kilo-opus"


def _build_test_app(executor: _FakeExecutor) -> FastAPI:
    app = FastAPI()
    app.include_router(build_anthropic_router(executor=executor))
    return app
