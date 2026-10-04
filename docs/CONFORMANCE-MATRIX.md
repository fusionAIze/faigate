# Conformance Matrix — fusionAIze Gate API Surfaces

This matrix records, per endpoint and feature, which behaviors of the exposed
API surfaces are **confirmed by a test**, which are **partial** (measured, with
a known gap), which are **not supported**, and which are **untested**.

**Tested against:**

- fusionAIze Gate **v2.9.3** (2026-09-24)
- OpenAI-compatible clients: **openai-python >= 1.0** and any HTTP client
- Anthropic-compatible clients: **anthropic-python >= 0.30** and any HTTP client

Every row that names a test cites a function that exists in `tests/`.
`test_matrix_citations_resolve` (in `tests/test_api_surfaces.py`) fails if a
cited test name does not resolve, so a claim cannot outlive its backing test.
Rows with no backing test cite no test and are marked **untested**; they are
neither "supported" nor "not supported".

---

## 1. OpenAI-Compatible Surface

Base path: `/v1` — enabled by `api_surfaces.openai_compatible: true` (default).

### `POST /v1/chat/completions`

| Feature | Status | Test | Notes |
|---|---|---|---|
| Text response (non-streaming) | confirmed | `test_openai_chat_text` | |
| Streaming (`stream: true`) | confirmed | `test_openai_chat_streaming` | Server-Sent Events; asserts emitted chunks and `data: [DONE]` |
| Usage in response | confirmed | `test_openai_chat_usage` | `prompt_tokens`, `completion_tokens` |
| Model routing (`auto` / provider-id) | confirmed | `test_openai_chat_model_routing` | |
| System message | confirmed | `test_openai_chat_system_message` | |
| Tools / function calling | partial | `test_openai_chat_tools_forwarded` | Forwarded to the provider; no server-side execution |
| `max_tokens` / `temperature` | confirmed | `test_openai_chat_sampling_forwarded` | |
| `stop` sequences | confirmed | `test_openai_chat_sampling_forwarded` | Placed in the provider `extra_body` |
| `response_format` (JSON mode) | partial | `test_openai_chat_sampling_forwarded` | Forwarded; no schema enforcement |
| Multimodal (image input) | partial | `test_openai_chat_multimodal_accepted` | Accepted and passed through; upstream-dependent |
| Error format (OpenAI-compatible) | confirmed | `test_openai_chat_error_format` | `{"error": {"message", "type", "attempts"}}` |

### `GET /v1/models`

| Feature | Status | Test | Notes |
|---|---|---|---|
| List routable models | confirmed | `test_openai_models_list` | `{"object": "list", "data": [...]}` |
| Includes `auto` | confirmed | `test_openai_models_includes_gate_models` | |

### `POST /v1/images/generations`

| Feature | Status | Test | Notes |
|---|---|---|---|
| Image generation | confirmed | `test_openai_image_generation` | Requires provider `image_generation` capability |
| `size` / `n` validation | confirmed | `test_openai_image_generation_validation` | 400 before the provider call |
| Capability enforcement | confirmed | `test_openai_image_generation_without_capability` | Provider without the capability is refused |
| Image-policy hints | untested | — | Not measured; no test |

### `POST /v1/images/edits`

| Feature | Status | Test | Notes |
|---|---|---|---|
| Image editing (`multipart/form-data`) | confirmed | `test_openai_image_edits` | Requires provider `image_editing` capability |
| Upload size limit | confirmed | `test_openai_image_edits_upload_limit` | 413 via `security.max_upload_bytes` |

---

## 2. Anthropic-Compatible Bridge (Optional)

Base path: `/v1` — requires **both** switches (see below).

### Dual-switch semantics

Two switches exist with distinguishable meanings:

| Switch | Meaning | Default |
|---|---|---|
| `anthropic_bridge.enabled` | Bridge logic layer (model translation, routing adaptation) | `false` |
| `api_surfaces.anthropic_messages` | HTTP surface exposure of `/v1/messages` and `/v1/messages/count_tokens` | follows `anthropic_bridge.enabled` |

The runtime gate requires **both** to be `true`. Measured 2026-09-24 (v2.9.3),
with the surface explicitly set and the bridge toggled:

| `anthropic_bridge.enabled` | `api_surfaces.anthropic_messages` | `/v1/messages` |
|---|---|---|
| `true` | `true` | 200 |
| `true` | `false` | 404 |
| `false` | `true` | 404 |
| `true` | absent | 200 (surface defaults to the bridge) |
| `false` | absent | 404 |

The 404 body is `{"type": "error", "error": {"type": "not_found_error",
"message": "Anthropic bridge is disabled"}}`.

**Note:** `anthropic_bridge.route_prefix` and
`anthropic_bridge.allow_claude_code_hints` are parsed and validated in
`faigate/config.py` but are not consulted anywhere at runtime (measured by
grep). They are configuration no-ops in v2.9.3.

### `POST /v1/messages`

| Feature | Status | Test | Notes |
|---|---|---|---|
| Text response (non-streaming) | confirmed | `test_anthropic_messages_text` | |
| Streaming | confirmed | `test_anthropic_messages_streaming` | Emits Anthropic SSE (`message_start` … `message_stop`) |
| System prompt (string) | confirmed | `test_anthropic_messages_system_string` | |
| System prompt (text block) | confirmed | `test_anthropic_messages_system_text_block` | |
| Tool use / tool result | confirmed | `test_anthropic_messages_forward_tool_use_and_tool_result_blocks` | Backed in `tests/test_anthropic_api.py` |
| Non-text blocks (image/binary) | not supported | `test_anthropic_messages_rejects_non_text_blocks` | 400; only text and tool_result blocks accepted |
| Model aliases (`model_aliases`) | confirmed | `test_anthropic_messages_applies_model_aliases` | Backed in `tests/test_anthropic_api.py` |
| Built-in Claude Code aliases | confirmed | `test_anthropic_messages_applies_builtin_claude_code_model_aliases` | Backed in `tests/test_anthropic_api.py` |
| Surface disabled response (404) | confirmed | `test_anthropic_messages_disabled_response` | Anthropic error envelope |
| Error format (Anthropic-compatible) | confirmed | `test_anthropic_messages_error_format` | `{"type": "error", "error": {"type", "message"}}` |

### `POST /v1/messages/count_tokens`

| Feature | Status | Test | Notes |
|---|---|---|---|
| Token count (estimated) | confirmed | `test_anthropic_count_tokens_estimated` | Char-based estimate; not provider-exact |
| Exact token count | not supported | `test_anthropic_count_tokens_estimated` | Header `X-faigate-Token-Count-Exact: false` |
| Error format | confirmed | `test_anthropic_count_tokens_error_format` | Same Anthropic envelope |

---

## 3. Health / Operator Endpoints

| Endpoint | Status | Test | Notes |
|---|---|---|---|
| `GET /health` | confirmed | `test_health_endpoint` | Provider summary, failure counters, latency |
| `GET /livez` | confirmed | `test_livez_endpoint` | Answers without external work |
| `GET /readyz` | confirmed | `test_readyz_endpoint` | |
| `GET /readyz` (required providers) | confirmed | `test_readyz_required_providers_config` | Via `health.required_providers` |
| `GET /api/providers` | confirmed | `test_api_providers` | |
| `POST /api/route` (dry-run) | confirmed | `test_api_route_dryrun` | |
| `GET /dashboard` | confirmed | `test_operator_endpoints_respond` | |
| `GET /api/stats` | confirmed | `test_operator_endpoints_respond` | |
| `GET /api/recent` | confirmed | `test_operator_endpoints_respond` | |
| `GET /api/traces` | confirmed | `test_operator_endpoints_respond` | |
| `GET /api/quotas` | confirmed | `test_operator_endpoints_respond` | |
| `GET /api/provider-catalog` | confirmed | `test_operator_endpoints_respond` | |

---

## 4. Error Format Divergence

Top-level schemas differ by surface. Measured 2026-09-24 (v2.9.3):

| Surface / condition | Top-level schema | Test |
|---|---|---|
| Chat, all providers failed | `{"error": {"message": <str>, "type": "upstream_server_error", "attempts": [{"provider", "status", "category"}]}}` | `test_openai_chat_error_format` |
| Image generation/edit, invalid request | `{"error": <str>, "type": "invalid_request_error"}` | `test_openai_image_generation_validation` |
| Image edit upload too large | `{"error": <str>, "type": "payload_too_large"}` | `test_openai_image_edits_upload_limit` |
| Anthropic surface error | `{"type": "error", "error": {"type": <str>, "message": <str>}}` | `test_anthropic_messages_error_format` |

The OpenAI-compatible image endpoints put a **string** under `error`; the chat
endpoint puts an **object**. The Anthropic surface uses a top-level `type:
"error"` discriminator. These differences are intentional — each surface
follows its own specification.

---

## 5. Evidence Levels

Each claim carries one of four evidence kinds:

| Kind | Meaning |
|---|---|
| `derivable` | Logical consequence of a tested behavior |
| `not_applicable` | Cannot occur, or does not apply |
| `runtime_dependent` | Depends on upstream provider behavior |
| `unlisted` | Not yet classified |

Measurement state (confirmed / partial / not supported / untested) is tracked
separately from the evidence kind. A row is only marked **confirmed** when the
cited test asserts the behavior; otherwise it is **untested**.
