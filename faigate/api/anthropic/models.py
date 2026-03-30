"""Anthropic-compatible wire models for the internal bridge layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class AnthropicBridgeError(ValueError):
    """Raised when an Anthropic wire payload cannot be normalized."""


@dataclass(frozen=True)
class AnthropicContentBlock:
    """One Anthropic content block."""

    type: str
    text: str | None = None
    tool_use_id: str | None = None
    name: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnthropicMessage:
    """One Anthropic message turn."""

    role: str
    content: list[AnthropicContentBlock] = field(default_factory=list)


@dataclass(frozen=True)
class AnthropicToolDefinition:
    """One Anthropic tool declaration."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnthropicMessagesRequest:
    """Minimal request model for ``POST /v1/messages``."""

    model: str
    system: str | list[str] | None = None
    messages: list[AnthropicMessage] = field(default_factory=list)
    tools: list[AnthropicToolDefinition] = field(default_factory=list)
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnthropicTokenCountRequest:
    """Minimal request model for ``POST /v1/messages/count_tokens``."""

    model: str
    system: str | list[str] | None = None
    messages: list[AnthropicMessage] = field(default_factory=list)
    tools: list[AnthropicToolDefinition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnthropicTokenCountResponse:
    """Minimal Anthropic-compatible token-count response."""

    input_tokens: int


@dataclass(frozen=True)
class AnthropicMessagesResponse:
    """Minimal response model for the Anthropic bridge."""

    id: str
    type: str = "message"
    role: str = "assistant"
    model: str | None = None
    content: list[AnthropicContentBlock] = field(default_factory=list)
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_anthropic_messages_request(payload: Mapping[str, Any]) -> AnthropicMessagesRequest:
    """Parse the smallest Anthropic messages payload we need for bridge setup."""

    if not isinstance(payload, Mapping):
        raise AnthropicBridgeError("Anthropic messages payload must be a mapping")

    model = str(payload.get("model", "") or "").strip()
    if not model:
        raise AnthropicBridgeError("Anthropic messages payload requires a model")

    raw_system = payload.get("system")
    system: str | list[str] | None
    if raw_system is None:
        system = None
    elif isinstance(raw_system, str):
        system = raw_system
    elif isinstance(raw_system, list) and all(isinstance(item, str) for item in raw_system):
        system = list(raw_system)
    else:
        raise AnthropicBridgeError("'system' must be a string, a list of strings, or null")

    raw_messages = payload.get("messages", [])
    if not isinstance(raw_messages, list):
        raise AnthropicBridgeError("'messages' must be a list")
    messages = [_parse_message(item) for item in raw_messages]

    raw_tools = payload.get("tools", [])
    if not isinstance(raw_tools, list):
        raise AnthropicBridgeError("'tools' must be a list")
    tools = [_parse_tool(item) for item in raw_tools]

    stream = payload.get("stream", False)
    if not isinstance(stream, bool):
        raise AnthropicBridgeError("'stream' must be a boolean")

    metadata = payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        raise AnthropicBridgeError("'metadata' must be a mapping")

    return AnthropicMessagesRequest(
        model=model,
        system=system,
        messages=messages,
        tools=tools,
        stream=stream,
        metadata=dict(metadata),
    )


def parse_anthropic_token_count_request(payload: Mapping[str, Any]) -> AnthropicTokenCountRequest:
    """Parse the v1 count_tokens payload using the same basic request shape."""

    request = parse_anthropic_messages_request(payload)
    return AnthropicTokenCountRequest(
        model=request.model,
        system=request.system,
        messages=request.messages,
        tools=request.tools,
        metadata=dict(request.metadata),
    )


def _parse_message(raw: Any) -> AnthropicMessage:
    if not isinstance(raw, Mapping):
        raise AnthropicBridgeError("Anthropic message entries must be mappings")

    role = str(raw.get("role", "") or "").strip()
    if not role:
        raise AnthropicBridgeError("Anthropic message entries require a role")

    return AnthropicMessage(role=role, content=_parse_content_blocks(raw.get("content", [])))


def _parse_content_blocks(raw: Any) -> list[AnthropicContentBlock]:
    if isinstance(raw, str):
        return [AnthropicContentBlock(type="text", text=raw)]
    if not isinstance(raw, list):
        raise AnthropicBridgeError("'content' must be a string or a list of blocks")

    blocks: list[AnthropicContentBlock] = []
    for item in raw:
        if isinstance(item, str):
            blocks.append(AnthropicContentBlock(type="text", text=item))
            continue
        if not isinstance(item, Mapping):
            raise AnthropicBridgeError("Anthropic content blocks must be strings or mappings")

        block_type = str(item.get("type", "") or "").strip()
        if not block_type:
            raise AnthropicBridgeError("Anthropic content blocks require a type")

        raw_input = item.get("input", {})
        if raw_input is None:
            raw_input = {}
        if not isinstance(raw_input, Mapping):
            raise AnthropicBridgeError("Anthropic tool content block 'input' must be a mapping")

        block_metadata = {
            key: value
            for key, value in item.items()
            if key not in {"type", "text", "id", "tool_use_id", "name", "input"}
        }
        blocks.append(
            AnthropicContentBlock(
                type=block_type,
                text=item.get("text"),
                tool_use_id=str(item.get("tool_use_id") or item.get("id") or "").strip() or None,
                name=str(item.get("name", "") or "").strip() or None,
                input=dict(raw_input),
                metadata=block_metadata,
            )
        )
    return blocks


def _parse_tool(raw: Any) -> AnthropicToolDefinition:
    if not isinstance(raw, Mapping):
        raise AnthropicBridgeError("Anthropic tool definitions must be mappings")

    name = str(raw.get("name", "") or "").strip()
    if not name:
        raise AnthropicBridgeError("Anthropic tool definitions require a name")

    input_schema = raw.get("input_schema", {})
    if input_schema is None:
        input_schema = {}
    if not isinstance(input_schema, Mapping):
        raise AnthropicBridgeError("'input_schema' must be a mapping")

    return AnthropicToolDefinition(
        name=name,
        description=str(raw.get("description", "") or "").strip(),
        input_schema=dict(input_schema),
    )
