"""Anthropic <-> canonical model adapters.

This module intentionally contains only normalization logic. Routing, policy
application, hook execution, and provider selection stay in the existing gate
core and are addressed through the ``CanonicalChatExecutor`` contract.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ...api.anthropic.models import (
    AnthropicBridgeError,
    AnthropicContentBlock,
    AnthropicMessage,
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
    AnthropicTokenCountRequest,
    AnthropicTokenCountResponse,
    parse_anthropic_messages_request,
    parse_anthropic_token_count_request,
)
from ...canonical import (
    CanonicalChatExecutor,
    CanonicalChatRequest,
    CanonicalChatResponse,
    CanonicalMessage,
    CanonicalResponseMessage,
    CanonicalTool,
)


@dataclass
class _AnthropicStreamToolState:
    """Tracks one streamed tool block while OpenAI-style deltas arrive."""

    index: int
    tool_use_id: str | None = None
    name: str | None = None
    started: bool = False
    closed: bool = False


def anthropic_request_to_canonical(
    request: AnthropicMessagesRequest,
    *,
    headers: dict[str, str] | None = None,
) -> CanonicalChatRequest:
    """Map an Anthropic messages request to the internal gateway model."""

    normalized_headers = {
        str(key): str(value) for key, value in (headers or {}).items()
    }
    source = (
        normalized_headers.get("x-faigate-client")
        or normalized_headers.get("anthropic-client")
        or "claude-code"
    )
    client = source
    metadata = dict(request.metadata)
    metadata.setdefault("source", source)
    metadata.setdefault("bridge_surface", "anthropic-messages")
    if normalized_headers:
        metadata["bridge_headers"] = normalized_headers

    return CanonicalChatRequest(
        client=client,
        surface="anthropic-messages",
        requested_model=request.model,
        system=request.system,
        messages=_messages_to_canonical(request.messages),
        tools=[
            CanonicalTool(
                name=tool.name,
                description=tool.description,
                input_schema=dict(tool.input_schema),
            )
            for tool in request.tools
        ],
        stream=request.stream,
        metadata=metadata,
    )


def canonical_to_openai_body(request: CanonicalChatRequest) -> dict[str, Any]:
    """Build the current internal handoff shape for the gateway core."""

    return request.to_openai_body()


def anthropic_count_tokens_request_to_canonical(
    request: AnthropicTokenCountRequest,
    *,
    headers: dict[str, str] | None = None,
) -> CanonicalChatRequest:
    """Map a count_tokens request to the same canonical request model."""

    return anthropic_request_to_canonical(
        AnthropicMessagesRequest(
            model=request.model,
            system=request.system,
            messages=request.messages,
            tools=request.tools,
            stream=False,
            metadata=dict(request.metadata),
        ),
        headers=headers,
    )


def canonical_response_to_anthropic(
    response: CanonicalChatResponse,
    *,
    requested_model: str,
) -> AnthropicMessagesResponse:
    """Map the canonical response model back to Anthropic wire format."""

    return AnthropicMessagesResponse(
        id=response.response_id or f"msg_{uuid4().hex}",
        model=response.model or requested_model,
        content=_canonical_content_to_anthropic_blocks(response.message),
        stop_reason=map_stop_reason_to_anthropic(
            response.stop_reason or response.message.stop_reason,
            has_tool_calls=bool(response.message.tool_calls),
        ),
        usage=dict(response.usage),
        metadata={
            **dict(response.metadata),
            **({"provider": response.provider} if response.provider else {}),
        },
    )


async def dispatch_anthropic_messages(
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    executor: CanonicalChatExecutor,
) -> AnthropicMessagesResponse:
    """Run the full bridge flow for one Anthropic messages request."""

    wire_request = parse_anthropic_messages_request(payload)
    canonical_request = anthropic_request_to_canonical(wire_request, headers=headers)
    canonical_response = await executor.execute_canonical_chat(canonical_request)
    return canonical_response_to_anthropic(
        canonical_response,
        requested_model=wire_request.model,
    )


def dispatch_anthropic_count_tokens(
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> tuple[AnthropicTokenCountResponse, dict[str, str]]:
    """Run the bridge flow for a local v1 token-count estimate.

    v1 deliberately favors a stable local estimate over provider-specific token
    accounting. The response remains Anthropic-compatible while the headers make
    the approximation explicit for operators and advanced clients.
    """

    wire_request = parse_anthropic_token_count_request(payload)
    canonical_request = anthropic_count_tokens_request_to_canonical(
        wire_request,
        headers=headers,
    )
    input_tokens, method = approximate_anthropic_input_tokens(canonical_request)
    return (
        AnthropicTokenCountResponse(input_tokens=input_tokens),
        {
            "X-faigate-Token-Count-Exact": "false",
            "X-faigate-Token-Count-Method": method,
        },
    )


def approximate_anthropic_input_tokens(
    request: CanonicalChatRequest,
) -> tuple[int, str]:
    """Return a lightweight token estimate for Anthropic bridge requests.

    The gateway does not yet maintain provider-specific tokenizers or a stable
    upstream counting path for every routed provider. For v1 we therefore use a
    deterministic character-byte heuristic with small structural overheads.
    """

    total = 3
    if isinstance(request.system, str):
        total += 4 + _estimate_text_tokens(request.system)
    elif isinstance(request.system, list):
        for item in request.system:
            if isinstance(item, str):
                total += 4 + _estimate_text_tokens(item)

    for message in request.messages:
        total += 4
        total += _estimate_text_tokens(message.role)
        total += _estimate_message_content_tokens(message.content)

    for tool in request.tools:
        total += 12
        total += _estimate_text_tokens(tool.name)
        total += _estimate_text_tokens(tool.description)
        total += _estimate_text_tokens(
            json.dumps(tool.input_schema, sort_keys=True, separators=(",", ":"))
        )

    return max(total, 1), "estimated-char-v1"


def _messages_to_canonical(messages: list[AnthropicMessage]) -> list[CanonicalMessage]:
    """Flatten Anthropic turns into the OpenAI-style sequence the core expects."""

    canonical_messages: list[CanonicalMessage] = []
    for message in messages:
        canonical_messages.extend(_message_to_canonical(message))
    return canonical_messages


def _message_to_canonical(message: AnthropicMessage) -> list[CanonicalMessage]:
    if message.role == "assistant":
        return [_assistant_message_to_canonical(message)]
    if message.role == "user":
        return _user_message_to_canonical(message)
    if any(block.type != "text" for block in message.content):
        raise AnthropicBridgeError(
            "Anthropic bridge v1 does not support "
            f"'{message.role}' messages with non-text blocks"
        )
    return [
        CanonicalMessage(
            role=message.role,
            content=_text_blocks_to_string(message.content),
        )
    ]


def _assistant_message_to_canonical(message: AnthropicMessage) -> CanonicalMessage:
    text_blocks: list[AnthropicContentBlock] = []
    tool_calls: list[dict[str, Any]] = []
    for block in message.content:
        if block.type == "text":
            text_blocks.append(block)
            continue
        if block.type != "tool_use":
            raise AnthropicBridgeError(
                "Anthropic bridge v1 supports only text and tool_use blocks in assistant messages"
            )
        tool_calls.append(_anthropic_tool_use_to_openai_call(block))
    return CanonicalMessage(
        role="assistant",
        content=_text_blocks_to_string(text_blocks),
        tool_calls=tool_calls,
    )


def _user_message_to_canonical(message: AnthropicMessage) -> list[CanonicalMessage]:
    tool_messages: list[CanonicalMessage] = []
    pending_text: list[AnthropicContentBlock] = []
    for block in message.content:
        if block.type == "text":
            pending_text.append(block)
            continue
        if block.type != "tool_result":
            raise AnthropicBridgeError(
                "Anthropic bridge v1 supports only text and tool_result blocks in user messages"
            )
        if not block.tool_use_id:
            # Claude-native clients can emit tool_result-like user blocks without a
            # stable tool_use_id. Falling back to user text keeps the session
            # usable instead of hard-failing the whole turn.
            pending_text.append(
                AnthropicContentBlock(
                    type="text",
                    text=_anthropic_tool_result_to_string(block),
                    metadata={**dict(block.metadata), "tool_result_without_id": True},
                )
            )
            continue
        tool_messages.append(_anthropic_tool_result_to_canonical_message(block))

    if not tool_messages:
        return [CanonicalMessage(role="user", content=_text_blocks_to_string(pending_text))]

    canonical_messages = list(tool_messages)
    if pending_text:
        # OpenAI-style tool continuity requires tool messages to follow the
        # assistant tool_calls immediately. Preserve any surrounding user text
        # as a trailing user turn once all tool_result blocks are emitted.
        canonical_messages.append(
            CanonicalMessage(role="user", content=_text_blocks_to_string(pending_text))
        )
    return canonical_messages


def _text_blocks_to_string(blocks: list[AnthropicContentBlock]) -> str:
    parts = [str(block.text or "") for block in blocks if block.type == "text"]
    return "\n\n".join(part for part in parts if part)


def _anthropic_tool_use_to_openai_call(block: AnthropicContentBlock) -> dict[str, Any]:
    if not block.name:
        raise AnthropicBridgeError("Anthropic tool_use blocks require a name")
    call_id = block.tool_use_id or f"toolu_{uuid4().hex[:24]}"
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": block.name,
            "arguments": json.dumps(
                block.input or {},
                separators=(",", ":"),
                sort_keys=True,
            ),
        },
    }


def _anthropic_tool_result_to_canonical_message(
    block: AnthropicContentBlock,
) -> CanonicalMessage:
    tool_use_id = block.tool_use_id
    if not tool_use_id:
        raise AnthropicBridgeError("Anthropic tool_result blocks require a tool_use_id")
    metadata = {}
    if "is_error" in block.metadata:
        metadata["tool_result_is_error"] = bool(block.metadata.get("is_error"))
    return CanonicalMessage(
        role="tool",
        content=_anthropic_tool_result_to_string(block),
        tool_call_id=tool_use_id,
        metadata=metadata,
    )


def _anthropic_tool_result_to_string(block: AnthropicContentBlock) -> str:
    raw_content = block.metadata.get("content")
    if raw_content is None and block.text is not None:
        return block.text
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        text_parts: list[str] = []
        for item in raw_content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if isinstance(item, dict) and str(item.get("type") or "") == "text":
                text_parts.append(str(item.get("text") or ""))
                continue
            return json.dumps(raw_content, sort_keys=True)
        return "\n\n".join(part for part in text_parts if part)
    if raw_content is None:
        return ""
    return json.dumps(raw_content, sort_keys=True)


def _anthropic_block_to_payload(block: AnthropicContentBlock) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": block.type}
    if block.text is not None:
        payload["text"] = block.text
    if block.tool_use_id:
        payload["tool_use_id"] = block.tool_use_id
    if block.name:
        payload["name"] = block.name
    if block.input:
        payload["input"] = dict(block.input)
    if block.metadata:
        payload["metadata"] = dict(block.metadata)
    return payload


def _estimate_message_content_tokens(content: Any) -> int:
    if isinstance(content, str):
        return _estimate_text_tokens(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, str):
                total += _estimate_text_tokens(item)
            elif isinstance(item, dict):
                total += _estimate_text_tokens(json.dumps(item, sort_keys=True))
            else:
                total += _estimate_text_tokens(str(item))
        return total
    return _estimate_text_tokens(str(content or ""))


def _estimate_text_tokens(text: str) -> int:
    cleaned = str(text or "")
    if not cleaned:
        return 0
    byte_count = len(cleaned.encode("utf-8"))
    return max(1, (byte_count + 3) // 4)


def _canonical_content_to_anthropic_blocks(
    message: CanonicalResponseMessage,
) -> list[AnthropicContentBlock]:
    content = message.content
    blocks: list[AnthropicContentBlock]
    if isinstance(content, str):
        blocks = (
            []
            if (not content and message.tool_calls)
            else [AnthropicContentBlock(type="text", text=content)]
        )
    elif isinstance(content, list):
        blocks = []
        for item in content:
            if isinstance(item, str):
                if item:
                    blocks.append(AnthropicContentBlock(type="text", text=item))
                continue
            if not isinstance(item, dict):
                blocks.append(AnthropicContentBlock(type="text", text=str(item)))
                continue
            blocks.append(
                AnthropicContentBlock(
                    type=str(item.get("type", "text") or "text"),
                    text=item.get("text"),
                    tool_use_id=str(item.get("tool_use_id", "") or "").strip() or None,
                    name=str(item.get("name", "") or "").strip() or None,
                    input=dict(item.get("input", {}) or {}),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
            )
    elif content:
        blocks = [AnthropicContentBlock(type="text", text=str(content))]
    else:
        blocks = []

    for tool_call in message.tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function", {}) or {}
        raw_arguments = str(function.get("arguments", "") or "").strip()
        parsed_arguments: dict[str, Any]
        if raw_arguments:
            try:
                loaded = json.loads(raw_arguments)
                parsed_arguments = loaded if isinstance(loaded, dict) else {"arguments": loaded}
            except json.JSONDecodeError:
                parsed_arguments = {"raw_arguments": raw_arguments}
        else:
            parsed_arguments = {}
        blocks.append(
            AnthropicContentBlock(
                type="tool_use",
                tool_use_id=str(tool_call.get("id", "") or "").strip() or None,
                name=str(function.get("name", "") or "").strip() or None,
                input=parsed_arguments,
            )
        )
    return blocks


def map_stop_reason_to_anthropic(
    stop_reason: str | None, *, has_tool_calls: bool = False
) -> str | None:
    """Translate OpenAI-style finish reasons into Anthropic stop reasons."""

    normalized = str(stop_reason or "").strip().lower()
    if not normalized:
        return "tool_use" if has_tool_calls else None
    if normalized in {"stop", "end_turn"}:
        return "end_turn"
    if normalized in {"tool_calls", "tool_use"}:
        return "tool_use"
    if normalized in {"length", "max_tokens"}:
        return "max_tokens"
    return normalized


def anthropic_sse_event(event_type: str, payload: dict[str, Any]) -> bytes:
    """Encode one Anthropic-style SSE event."""

    body = json.dumps(payload, separators=(",", ":"))
    return f"event: {event_type}\ndata: {body}\n\n".encode()


async def openai_sse_to_anthropic(
    stream: AsyncIterator[bytes],
    *,
    requested_model: str,
    resolved_model: str | None = None,
) -> AsyncIterator[bytes]:
    """Translate OpenAI-compatible SSE chunks into Anthropic-style message events.

    This intentionally supports the common bridge path first:

    - text deltas
    - streamed tool calls represented as function-call deltas
    - stop reasons and optional usage payloads

    Unknown or malformed upstream chunks are ignored conservatively instead of
    terminating the client-visible stream abruptly.
    """

    message_id = f"msg_{uuid4().hex}"
    output_tokens = 0
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    text_block_started = False
    text_block_closed = False
    tool_states: dict[int, _AnthropicStreamToolState] = {}
    tool_blocks_closed = False
    stop_reason: str | None = None

    yield anthropic_sse_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": resolved_model or requested_model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": dict(usage),
            },
        },
    )

    try:
        async for raw_line in stream:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if not payload_text:
                continue
            if payload_text == "[DONE]":
                break

            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict) and "error" in payload:
                if text_block_started and not text_block_closed:
                    yield anthropic_sse_event(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": 0},
                    )
                    text_block_closed = True
                for tool_index in sorted(tool_states):
                    state = tool_states[tool_index]
                    if state.started and not state.closed:
                        yield anthropic_sse_event(
                            "content_block_stop",
                            {
                                "type": "content_block_stop",
                                "index": _anthropic_tool_index(
                                    tool_index,
                                    text_block_started,
                                ),
                            },
                        )
                        state.closed = True
                tool_blocks_closed = True
                yield anthropic_sse_event(
                    "error",
                    {
                        "type": "error",
                        "error": payload.get("error")
                        or {"type": "api_error", "message": "Upstream error"},
                    },
                )
                return

            usage_payload = payload.get("usage") or {}
            prompt_tokens = int(usage_payload.get("prompt_tokens") or 0)
            completion_tokens = int(usage_payload.get("completion_tokens") or 0)
            if prompt_tokens:
                usage["input_tokens"] = prompt_tokens
            if completion_tokens:
                usage["output_tokens"] = completion_tokens

            choices = payload.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            delta = choice.get("delta") or {}
            finish_reason = str(choice.get("finish_reason") or "").strip() or None

            text_delta = delta.get("content")
            if isinstance(text_delta, str) and text_delta:
                if tool_states and not tool_blocks_closed:
                    for tool_index in sorted(tool_states):
                        state = tool_states[tool_index]
                        if state.started and not state.closed:
                            yield anthropic_sse_event(
                                "content_block_stop",
                                {
                                    "type": "content_block_stop",
                                    "index": _anthropic_tool_index(
                                        tool_index,
                                        text_block_started=True,
                                    ),
                                },
                            )
                            state.closed = True
                    tool_blocks_closed = True
                if not text_block_started:
                    yield anthropic_sse_event(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        },
                    )
                    text_block_started = True
                output_tokens += _estimate_text_tokens(text_delta)
                usage["output_tokens"] = max(usage["output_tokens"], output_tokens)
                yield anthropic_sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": text_delta},
                    },
                )

            delta_tool_calls = delta.get("tool_calls") or []
            if isinstance(delta_tool_calls, list) and delta_tool_calls:
                if text_block_started and not text_block_closed:
                    yield anthropic_sse_event(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": 0},
                    )
                    text_block_closed = True
                for tool_delta in delta_tool_calls:
                    if not isinstance(tool_delta, dict):
                        continue
                    raw_index = int(tool_delta.get("index") or 0)
                    state = tool_states.setdefault(
                        raw_index, _AnthropicStreamToolState(index=raw_index)
                    )
                    function = tool_delta.get("function") or {}
                    if tool_delta.get("id"):
                        state.tool_use_id = str(tool_delta["id"])
                    if function.get("name"):
                        state.name = str(function["name"])
                    if not state.started and state.name:
                        state.started = True
                        state.tool_use_id = state.tool_use_id or f"toolu_{uuid4().hex[:24]}"
                        yield anthropic_sse_event(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": _anthropic_tool_index(
                                    raw_index,
                                    text_block_started,
                                ),
                                "content_block": {
                                    "type": "tool_use",
                                    "id": state.tool_use_id,
                                    "name": state.name,
                                    "input": {},
                                },
                            },
                        )
                    raw_arguments = function.get("arguments")
                    if state.started and isinstance(raw_arguments, str) and raw_arguments:
                        yield anthropic_sse_event(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": _anthropic_tool_index(
                                    raw_index,
                                    text_block_started,
                                ),
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": raw_arguments,
                                },
                            },
                        )

            if finish_reason:
                stop_reason = map_stop_reason_to_anthropic(
                    finish_reason,
                    has_tool_calls=bool(tool_states),
                )
    except Exception as exc:
        if text_block_started and not text_block_closed:
            yield anthropic_sse_event(
                "content_block_stop",
                {"type": "content_block_stop", "index": 0},
            )
            text_block_closed = True
        for tool_index in sorted(tool_states):
            state = tool_states[tool_index]
            if state.started and not state.closed:
                yield anthropic_sse_event(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": _anthropic_tool_index(
                            tool_index,
                            text_block_started,
                        ),
                    },
                )
                state.closed = True
        yield anthropic_sse_event(
            "error",
            {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"Streaming request failed unexpectedly: {exc}",
                },
            },
        )
        return

    if text_block_started and not text_block_closed:
        yield anthropic_sse_event(
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
        )
    for tool_index in sorted(tool_states):
        state = tool_states[tool_index]
        if state.started and not state.closed:
            yield anthropic_sse_event(
                "content_block_stop",
                {
                    "type": "content_block_stop",
                    "index": _anthropic_tool_index(tool_index, text_block_started),
                },
            )

    yield anthropic_sse_event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": (
                    stop_reason or ("tool_use" if tool_states else "end_turn")
                ),
                "stop_sequence": None,
            },
            "usage": dict(usage),
        },
    )
    yield anthropic_sse_event("message_stop", {"type": "message_stop"})


def _anthropic_tool_index(raw_index: int, text_block_started: bool) -> int:
    """Return the Anthropic content index for one streamed tool block."""

    return raw_index + (1 if text_block_started else 0)
