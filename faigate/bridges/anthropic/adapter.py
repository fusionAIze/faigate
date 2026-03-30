"""Anthropic <-> canonical model adapters.

This module intentionally contains only normalization logic. Routing, policy
application, hook execution, and provider selection stay in the existing gate
core and are addressed through the ``CanonicalChatExecutor`` contract.
"""

from __future__ import annotations

import json
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


def anthropic_request_to_canonical(
    request: AnthropicMessagesRequest,
    *,
    headers: dict[str, str] | None = None,
) -> CanonicalChatRequest:
    """Map an Anthropic messages request to the internal gateway model."""

    normalized_headers = {str(key): str(value) for key, value in (headers or {}).items()}
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
        messages=[_message_to_canonical(message) for message in request.messages],
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
        stop_reason=response.stop_reason or response.message.stop_reason,
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


def approximate_anthropic_input_tokens(request: CanonicalChatRequest) -> tuple[int, str]:
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


def _message_to_canonical(message: AnthropicMessage) -> CanonicalMessage:
    if any(block.type != "text" for block in message.content):
        raise AnthropicBridgeError(
            "Anthropic bridge v1 currently supports only text content blocks in messages"
        )
    if len(message.content) == 1 and message.content[0].type == "text":
        content: Any = message.content[0].text or ""
    else:
        content = [_anthropic_block_to_payload(block) for block in message.content]
    return CanonicalMessage(role=message.role, content=content)


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
        blocks = [AnthropicContentBlock(type="text", text=content)]
    elif isinstance(content, list):
        blocks = []
        for item in content:
            if isinstance(item, str):
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
    else:
        blocks = [AnthropicContentBlock(type="text", text=str(content or ""))]

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
