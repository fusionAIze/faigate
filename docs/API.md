# fusionAIze Gate API Reference

fusionAIze Gate keeps the client-facing surface intentionally small: OpenAI-compatible paths for chat and image workloads, plus a compact operator API for health, routing introspection, and updates.

## Core OpenAI-Compatible Endpoints

### `GET /v1/models`

Returns the virtual `auto` model, any configured routing modes and model shortcuts, plus one entry for every provider that actually loaded at startup.

This is also the source of truth for OpenClaw-side model ids under a `faigate` provider entry.

```bash
curl -fsS http://127.0.0.1:8090/v1/models
```

### `POST /v1/chat/completions`

Routes OpenAI-style chat requests.

- `model: "auto"` runs the normal routing flow
- `model: "eco"` / `model: "premium"` / other configured routing modes apply virtual mode preferences first
- `model: "<provider-id>"` routes directly to a loaded provider
- `model: "<shortcut-id>"` routes directly through one configured model shortcut
- request size is bounded by `security.max_json_body_bytes`

```bash
curl -fsS http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Summarize the benefits of a local AI gateway."}
    ],
    "max_tokens": 128
  }'
```

## Optional Anthropic-Compatible Bridge

The Anthropic bridge stays optional and v1 is intentionally narrow. It exists to let Claude-oriented clients keep one stable local endpoint while Gate still owns routing, health checks, fallback, and provider selection.

Enable it with:

```yaml
api_surfaces:
  anthropic_messages: true

anthropic_bridge:
  enabled: true
```

### `POST /v1/messages`

Routes Anthropic-/Claude-style message requests through the same internal Gate routing path used by the OpenAI-compatible surface.

- validates a small v1 subset of Anthropic `messages`
- supports a simple `system` prompt
- supports text content blocks
- non-streaming only in v1
- optional `anthropic_bridge.model_aliases` can map Claude-facing model ids onto Gate routing modes or provider ids

```bash
curl -fsS http://127.0.0.1:8090/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'anthropic-client: claude-code' \
  -d '{
    "model": "claude-code",
    "system": "Prefer concise technical explanations.",
    "messages": [
      {"role": "user", "content": "Summarize the current fallback path."}
    ]
  }'
```

Response shape is Anthropic-compatible and still carries the normal Gate response headers such as:

- `X-faigate-Provider`
- `X-faigate-Profile`
- `X-faigate-Layer`
- `X-faigate-Rule`

### `POST /v1/messages/count_tokens`

Returns a minimal Anthropic-compatible token-count response for the same request structure as `/v1/messages`.

v1 uses a deterministic local estimate instead of provider-exact token accounting.

```bash
curl -fsS http://127.0.0.1:8090/v1/messages/count_tokens \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-code",
    "messages": [
      {"role": "user", "content": "Count these tokens."}
    ]
  }'
```

Response body:

```json
{"input_tokens": 11}
```

Response headers make the approximation explicit:

- `X-faigate-Token-Count-Exact: false`
- `X-faigate-Token-Count-Method: estimated-char-v1`

Known v1 bridge limits:

- non-streaming only
- text content blocks only
- image or binary content blocks are rejected
- `count_tokens` is an estimate, not provider-exact accounting

### `POST /v1/images/generations`

Routes image-generation requests to providers with `capabilities.image_generation: true`.

- validates `prompt`, `n`, and `size` before any provider call
- supports image-policy hints via `metadata.image_policy` or `X-faigate-Image-Policy`
- works well with OpenClaw when `imageModel.primary` is `faigate/auto` or one explicit `faigate/<provider-id>`

```bash
curl -fsS http://127.0.0.1:8090/v1/images/generations \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "prompt": "An architectural diagram of a local AI gateway, blueprint style",
    "size": "1024x1024"
  }'
```

### `POST /v1/images/edits`

Routes image-editing requests to providers with `capabilities.image_editing: true`.

- expects `multipart/form-data`
- currently supports one required `image` and one optional `mask`
- rejects uploads above `security.max_upload_bytes`
- accepts image-policy hints via `image_policy`, `metadata.image_policy`, or `X-faigate-Image-Policy`
- requires at least one loaded provider with `capabilities.image_editing: true`

```bash
curl -fsS http://127.0.0.1:8090/v1/images/edits \
  -F 'model=auto' \
  -F 'prompt=Remove the background and keep the subject centered' \
  -F 'image=@input.png' \
  -F 'mask=@mask.png'
```

## Operator Endpoints

### `GET /health`

Returns overall service status, provider summary, and capability coverage.

Each provider entry includes health, failure counters, average latency, last error, contract, backend, tier, capabilities, and image metadata.

```bash
curl -fsS http://127.0.0.1:8090/health
```

### `GET /api/providers`

Returns the loaded provider inventory plus the same capability-coverage summary used by the dashboard.

- optional `capability=<name>`
- optional `healthy=true|false`

```bash
curl -fsS 'http://127.0.0.1:8090/api/providers?capability=image_generation'
```

### `GET /api/provider-catalog`

Returns the curated provider-catalog view with drift, freshness, volatility, auth-mode, source-confidence metadata, an explicit link-neutral recommendation policy block, and optional disclosed provider-discovery links for configured providers.

```bash
curl -fsS http://127.0.0.1:8090/api/provider-catalog
```

For local operator use, the same discovery block is also available via:

```bash
./scripts/faigate-provider-discovery
./scripts/faigate-provider-discovery --json
```

### `GET /api/provider-discovery`

Returns the compact discovery-link view with the same link-neutral recommendation policy block, plus optional filters for `link_source`, `offer_track`, and `disclosed_only`.

```bash
curl -fsS 'http://127.0.0.1:8090/api/provider-discovery?offer_track=free'
curl -fsS 'http://127.0.0.1:8090/api/provider-discovery?link_source=operator_override&disclosed_only=true'
./scripts/faigate-provider-discovery --json --offer-track free
./scripts/faigate-provider-discovery --link-source operator_override --disclosed-only
```

### `GET /api/stats`

Returns aggregate request counters, token usage, per-client breakdowns, aggregate client totals, client highlight summaries, cost data, and operator-action summaries.

```bash
curl -fsS http://127.0.0.1:8090/api/stats
```

### `GET /api/recent`

Returns recent request records with optional filters for provider, client tag, layer, and success state.

```bash
curl -fsS 'http://127.0.0.1:8090/api/recent?limit=20'
```

### `GET /api/traces`

Returns detailed route traces including requested model, decision reason, attempt order, client profile, and selected provider.

```bash
curl -fsS 'http://127.0.0.1:8090/api/traces?limit=20'
```

### `GET /api/update`

Returns current release information plus update guardrails such as alert level, rollout ring, release age eligibility, maintenance-window state, and verification hints.

```bash
curl -fsS http://127.0.0.1:8090/api/update
```

### `GET /api/operator-events`

Returns helper-driven operator actions such as update checks and auto-update attempts.

```bash
curl -fsS 'http://127.0.0.1:8090/api/operator-events?limit=20'
```

### `POST /api/route`

Dry-runs chat routing and returns the selected provider, routing layer, decision reason, resolved mode, resolved shortcut, profile resolution, and attempt order.

```bash
curl -fsS http://127.0.0.1:8090/api/route \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Plan a low-latency response path for a CLI agent."}
    ]
  }'
```

### `POST /api/route/image`

Dry-runs image-generation or image-editing routing without calling an upstream provider.

```bash
curl -fsS http://127.0.0.1:8090/api/route/image \
  -H 'Content-Type: application/json' \
  -d '{
    "operation": "generation",
    "model": "auto",
    "prompt": "A clean dashboard screenshot mockup",
    "size": "1024x1024"
  }'
```

### `GET /dashboard`

Serves the built-in no-build operator dashboard.

```bash
open http://127.0.0.1:8090/dashboard
```

## Response Headers

Non-streaming chat completions include:

- `X-faigate-Provider`
- `X-faigate-Mode` when a virtual routing mode was active
- `X-faigate-Shortcut` when a model shortcut was used
- `X-faigate-Layer`
- `X-faigate-Rule`

These are intentionally bounded and sanitized before they leave the gateway.
