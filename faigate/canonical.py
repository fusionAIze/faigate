"""Canonical request/response models shared by protocol bridge layers.

The gateway currently exposes an OpenAI-compatible ingress surface. Additional
surfaces such as Anthropic messages should normalize into one internal shape so
that routing, hooks, and provider execution remain centralized.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class CanonicalTool:
    """One tool definition in the gateway-internal request model."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalMessage:
    """One normalized conversational turn.

    ``content`` intentionally stays flexible for the first bridge slice. The
    existing routing path mainly reasons about message lists and roles, while
    bridge adapters may still need to preserve provider-specific content blocks.
    """

    role: str
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalChatRequest:
    """Ingress-independent chat request passed into the gateway core."""

    client: str
    surface: str
    requested_model: str
    system: str | list[str] | None = None
    messages: list[CanonicalMessage] = field(default_factory=list)
    tools: list[CanonicalTool] = field(default_factory=list)
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_openai_body(self) -> dict[str, Any]:
        """Build the existing OpenAI-compatible request shape.

        This helper is the narrow handoff point for the first bridge iteration.
        The rest of the runtime can keep using the established
        ``/v1/chat/completions`` payload contract until a shared execution
        helper is extracted.
        """

        messages: list[dict[str, Any]] = []
        if isinstance(self.system, str) and self.system.strip():
            messages.append({"role": "system", "content": self.system})
        elif isinstance(self.system, list):
            for item in self.system:
                if isinstance(item, str) and item.strip():
                    messages.append({"role": "system", "content": item})

        for message in self.messages:
            payload: dict[str, Any] = {
                "role": message.role,
                "content": message.content,
            }
            if message.name:
                payload["name"] = message.name
            if message.tool_call_id:
                payload["tool_call_id"] = message.tool_call_id
            if message.metadata:
                payload["metadata"] = dict(message.metadata)
            messages.append(payload)

        body: dict[str, Any] = {
            "model": self.requested_model,
            "messages": messages,
            "stream": self.stream,
        }
        if self.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": dict(tool.input_schema),
                    },
                    "metadata": dict(tool.metadata),
                }
                for tool in self.tools
            ]
        if self.metadata:
            body["metadata"] = dict(self.metadata)
        return body


@dataclass(frozen=True)
class CanonicalResponseMessage:
    """Normalized assistant response returned from the gateway core."""

    role: str = "assistant"
    content: Any = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalChatResponse:
    """Ingress-independent chat response."""

    response_id: str | None = None
    model: str | None = None
    provider: str | None = None
    message: CanonicalResponseMessage = field(default_factory=CanonicalResponseMessage)
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class CanonicalChatExecutor(Protocol):
    """Small execution contract for future bridge surfaces."""

    async def execute_canonical_chat(self, request: CanonicalChatRequest) -> CanonicalChatResponse:
        """Run one canonical chat request through the gateway core."""

