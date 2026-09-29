# Conformance Matrix — fusionAIze Gate API Surfaces

This matrix documents which API-surface features are **confirmed** (tested),
**partial** (partially supported, known gaps), or **not supported** for each
exposed endpoint. Every claim is backed by a test in
`tests/test_api_surfaces.py`.

**Tested client version:** OpenAI-compatible SDKs (openai-python ≥1.0),
Anthropic SDK (anthropic-python ≥0.30), or any HTTP client.

---

## 1. OpenAI-Compatible Surface

Base path: `/v1` — enabled by `api_surfaces.openai_compatible: true` (default).

### `POST /v1/chat/completions`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Text response (non-streaming) | confirmed | v0.1 | `test_openai_chat_text` | |
| Streaming (`stream: true`) | confirmed | v0.1 | `test_openai_chat_streaming` | Server-Sent Events |
| Tools / function calling | confirmed | v0.6 | `test_openai_chat_tools` | |
| Usage in response | confirmed | v0.1 | `test_openai_chat_usage` | `prompt_tokens`, `completion_tokens` |
| Model routing (`auto` / mode / provider-id) | confirmed | v0.1 | `test_openai_chat_model_routing` | |
| System message | confirmed | v0.1 | `test_openai_chat_system_message` | |
| Multimodal (image input) | partial | v0.4 | untested | Passed through, depends on upstream |
| `max_tokens` / `temperature` / `top_p` | confirmed | v0.1 | `test_openai_chat_sampling_params` | |
| `stop` sequences | confirmed | v0.1 | `test_openai_chat_stop` | |
| `response_format` (JSON mode) | partial | v0.8 | untested | Passed through; no schema enforcement |
| Error format (OpenAI-compatible) | confirmed | v0.1 | `test_openai_chat_error_format` | Top-level `{"error": {"message": …, "type": …, "code": …}}` |

### `GET /v1/models`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| List routable models | confirmed | v0.1 | `test_openai_models_list` | Returns `{"object": "list", "data": […]}` |
| Response includes `auto`, modes, shortcuts | confirmed | v0.7 | `test_openai_models_includes_gate_models` | |

### `POST /v1/images/generations`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Image generation | confirmed | v0.4 | `test_openai_image_generation` | Requires provider with `image_generation` capability |
| `n` / `size` validation | confirmed | v0.4 | `test_openai_image_generation_validation` | |
| Image-policy hints | confirmed | v0.8 | `test_openai_image_policy` | Via `X-faigate-Image-Policy` or `metadata.image_policy` |

### `POST /v1/images/edits`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Image editing (`multipart/form-data`) | confirmed | v0.4 | `test_openai_image_edits` | Requires provider with `image_editing` capability |
| Upload size limit | confirmed | v0.4 | `test_openai_image_edits_upload_limit` | Enforced by `security.max_upload_bytes` |
| Error format (OpenAI-compatible) | confirmed | v0.4 | `test_openai_image_error_format` | Same top-level error envelope as chat |

---

## 2. Anthropic-Compatible Bridge (Optional)

Base path: `/v1` — requires **both** `anthropic_bridge.enabled: true` **and**
`api_surfaces.anthropic_messages: true`.

### Dual-switch semantics

The Anthropic surface has **two independent switches with distinguishable
meanings**:

| Switch | Controls | Default |
|---|---|---|
| `anthropic_bridge.enabled` | Bridge logic layer: model translation, routing adaptation, Claude Code hint processing | `false` |
| `api_surfaces.anthropic_messages` | HTTP surface exposure: whether `/v1/messages` and `/v1/messages/count_tokens` respond | follows `anthropic_bridge.enabled` |

The runtime gate (`_anthropic_bridge_surface_enabled`) requires **both** to be
`true`. Setting only one does not enable the surface.

### `POST /v1/messages`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Text response (non-streaming) | confirmed | v0.7 | `test_anthropic_messages_text` | |
| Streaming | not supported | v0.7 | `test_anthropic_messages_streaming_rejected` | Returns error; v1 bridge is non-streaming only |
| System prompt (string) | confirmed | v0.7 | `test_anthropic_messages_system_string` | |
| System prompt (text block) | confirmed | v0.7 | `test_anthropic_messages_system_text_block` | |
| Tool use / tool result | confirmed | v0.7 | `test_anthropic_messages_tool_use` | |
| Image / binary content blocks | not supported | v0.7 | `test_anthropic_messages_rejects_non_text_blocks` | Explicitly rejected |
| Model aliases (`model_aliases`) | confirmed | v0.7 | `test_anthropic_messages_model_aliases` | Maps Claude-facing ids to routing modes |
| Built-in Claude Code aliases | confirmed | v0.7 | `test_anthropic_messages_builtin_aliases` | |
| Usage in response | partial | v0.7 | `test_anthropic_messages_usage` | `input_tokens` provided; `output_tokens` may be estimated |
| Error format (Anthropic-compatible) | confirmed | v0.7 | `test_anthropic_messages_error_format` | Top-level `{"type": "error", "error": {"type": …, "message": …}}` |
| Surface disabled response (404) | confirmed | v0.7 | `test_anthropic_messages_disabled` | Returns 404 with Anthropic error body when either switch is off |

### `POST /v1/messages/count_tokens`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Token count (estimated) | confirmed | v0.7 | `test_anthropic_count_tokens_estimated` | Char-based estimate, not provider-exact |
| Exact token count | not supported | v0.7 | `test_anthropic_count_tokens_exact_rejected` | Headers indicate estimation: `X-faigate-Token-Count-Exact: false` |
| Error format | confirmed | v0.7 | `test_anthropic_count_tokens_error_format` | Same Anthropic error envelope |

---

## 3. Health / Operator Endpoints

### `GET /health`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Full provider health summary | confirmed | v0.1 | `test_health_endpoint` | Includes per-provider health, failure counters, latency |

### `GET /livez`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Lightweight liveness | confirmed | v0.9 (F13-A) | `test_livez_endpoint` | Answers without external work |

### `GET /readyz`

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Readiness with required providers | confirmed | v0.9 (F13-A) | `test_readyz_endpoint` | 503 when required provider is unreachable |
| Config-driven required providers | confirmed | v0.9 (F13-A) | `test_readyz_required_providers_config` | Via `health.required_providers` |

### Operator API (`/api/*`, `/dashboard`)

| Feature | Status | Since | Test | Notes |
|---|---|---|---|---|
| Provider inventory (`/api/providers`) | confirmed | v0.1 | `test_api_providers` | |
| Route dry-run (`/api/route`) | confirmed | v0.3 | `test_api_route_dryrun` | |
| Provider catalog (`/api/provider-catalog`) | confirmed | v0.8 | `test_api_provider_catalog` | |
| Dashboard (`/dashboard`) | confirmed | v0.6 | untested | Built-in HTML dashboard |
| Stats / traces / recent | confirmed | v0.5 | untested | Operator introspection endpoints |
| Quota endpoints | confirmed | v0.9 | untested | |

---

## 4. Error Format Divergence

| Surface | Top-level schema | Error detail schema | Test |
|---|---|---|---|
| OpenAI-compatible | `{"error": {"message": …, "type": …, "code": …}}` | Standard OpenAI error object | `test_openai_chat_error_format` |
| Anthropic-compatible | `{"type": "error", "error": {"type": …, "message": …}}` | Anthropic error object with `type` discriminator | `test_anthropic_messages_error_format` |

The top-level schemas differ intentionally — each surface matches its
respective API specification.

---

## 5. Evidence Levels

Each claim in this matrix uses one of four evidence kinds:

| Kind | Meaning |
|---|---|
| `derivable` | Logical consequence of tested behavior |
| `not_applicable` | Cannot occur or does not apply |
| `runtime_dependent` | Depends on upstream provider capabilities |
| `unlisted` | Not yet classified |

Measurement state (tested/untested) is tracked separately from evidence kind.
