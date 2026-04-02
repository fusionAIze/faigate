# Anthropic Bridge Plan

## Goal

Add an internal, optional Anthropic-/Claude-compatible bridge layer to
`faigate` without creating a separate repo or a sidecar gateway.

The bridge should:

- add an Anthropic-compatible ingress surface
- normalize Anthropic Messages requests into one internal canonical request shape
- reuse the existing routing, policies, hooks, fallbacks, and provider execution
- translate selected responses back into Anthropic-compatible output

The bridge should **not**:

- create a second routing engine
- move provider selection logic out of the current core
- turn `faigate` into a generic protocol-conversion platform

## Current Repo Shape

Today the runtime is still intentionally flat:

- `faigate/main.py`
  - owns FastAPI route registration
  - validates request bodies
  - applies request hooks
  - calls the router
  - executes providers and fallback order
- `faigate/router.py`
  - owns layered route selection via `Router.route(...)`
  - uses policy, static, heuristic, hook, profile, optional LLM classify, fallback
- `faigate/providers.py`
  - owns backend execution through `ProviderBackend.complete(...)`
  - currently assumes OpenAI-style chat payloads plus the Google-specific path
- `faigate/hooks.py`
  - owns request hook contracts and hook application
- `faigate/config.py`
  - owns config normalization and defaulting

That means the current OpenAI ingress path is effectively:

1. HTTP request enters `POST /v1/chat/completions` in `faigate/main.py`
2. JSON body is validated and normalized enough for the OpenAI path
3. `_apply_request_hooks(...)` runs through `faigate/hooks.py`
4. `_resolve_route_preview(...)` prepares routing inputs
5. `Router.route(...)` in `faigate/router.py` selects a provider
6. `ProviderBackend.complete(...)` in `faigate/providers.py` sends the upstream request
7. `faigate/main.py` wraps the response and emits metrics/headers

This is the seam the Anthropic bridge should reuse, not replace.

## Existing Integration Points

These are the main places where API routes, routing, providers, and hooks meet
today.

### API ingress and request handling

- `faigate/main.py`
  - `_read_json_body(...)`
  - `_apply_request_hooks(...)`
  - `_resolve_route_preview(...)`
  - `chat_completions(...)`

### Routing engine

- `faigate/router.py`
  - `Router.route(...)`
  - `Router.route_capability_request(...)`

### Provider execution

- `faigate/providers.py`
  - `ProviderBackend.complete(...)`
  - `ProviderBackend._stream_response(...)`

### Hook seam

- `faigate/hooks.py`
  - `RequestHookContext`
  - `RequestHookResult`
  - `apply_request_hooks(...)`

## Recommended Minimal Internal Module Structure

Keep the new structure deliberately small and close to the current repo style.

Recommended first cut:

```text
faigate/
  bridges/
    __init__.py
    anthropic.py
  api/
    __init__.py
    anthropic.py
```

### Why this is the minimal good cut

- `faigate/api/anthropic.py`
  - contains the FastAPI-facing route handlers and payload validation helpers
  - keeps Anthropic-specific HTTP semantics out of `main.py`
- `faigate/bridges/anthropic.py`
  - contains the protocol mapping logic
  - translates Anthropic request/response shapes to and from the canonical shape

This is enough for v1.

Do **not** start with a large tree such as:

- `faigate/api/anthropic/routes.py`
- `faigate/api/anthropic/validation.py`
- `faigate/bridges/anthropic/mapper_in.py`
- `faigate/bridges/anthropic/mapper_out.py`
- `faigate/bridges/anthropic/errors.py`

That decomposition may become useful later, but it is not necessary for the
first bridge slice and would add abstraction before we know where the real
complexity lands.

## Recommended Internal Canonical Request Shape

The bridge should not hand Anthropic payloads directly to the router or to
providers. Introduce one small canonical request/response mapping boundary.

For v1, the canonical request can remain a plain Python dict instead of a new
Pydantic model layer.

Suggested v1 shape:

```python
{
    "surface": "anthropic",
    "client": "claude-code",
    "model_requested": "claude-sonnet-4-5",
    "messages": [...],          # OpenAI-like normalized messages
    "system": "...",            # folded into messages if needed before provider call
    "tools": [...],
    "tool_choice": ...,
    "max_tokens": 4096,
    "temperature": 0.2,
    "stream": False,
    "metadata": {
        "bridge": "anthropic",
        "source_client": "claude-code",
        "anthropic_model": "claude-sonnet-4-5",
    },
}
```

Important point:

- this canonical shape should be **close enough to the existing OpenAI path**
  that we can reuse the current router and provider execution with minimal glue

## Bridge Behavior by Layer

### Bridge responsibilities

- validate incoming Anthropic request body
- normalize `system`, `messages`, `tools`, `tool_choice`, `max_tokens`, `stream`
- map model aliases into `model_requested`
- preserve enough client metadata for hooks and observability
- translate selected response fields back into Anthropic-compatible output

### Core responsibilities that stay where they are

- hooks
- client profile resolution
- route scoring and selection
- fallback order
- provider health and runtime penalties
- metrics and traces
- adaptive routing state

### Hook role

Hooks stay optional routing refinement, not protocol translation.

A Claude-/Anthropic-specific hook may later:

- detect Claude Code traffic
- prefer coding-capable routes
- prefer tool-capable routes
- set `routing_mode`
- add provider preferences

But the hook should operate on already normalized request metadata, not parse
Anthropic wire protocol directly.

## Suggested v1 API Scope

### In scope

- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- non-streaming text responses
- simple tool definitions
- model alias handling
- error mapping for the common client-visible cases

### Explicitly out of scope for v1

- full Anthropic SSE streaming parity
- multimodal attachments
- advanced tool-use round-tripping
- every Anthropic-specific content block type
- every Claude Desktop / Claude Code nuance

That narrower scope keeps the bridge realistic and testable.

## Concrete Implementation Plan

### Phase 1: extract a reusable chat execution seam

Before the Anthropic route is added, create one small internal helper in
`faigate/main.py` for the already-existing OpenAI path.

Goal:

- avoid duplicating routing + provider execution logic between
  `POST /v1/chat/completions` and `POST /v1/messages`

Suggested helper shape:

```python
async def _execute_chat_request(
    *,
    body: dict[str, Any],
    headers: dict[str, str],
    surface: str,
) -> Response:
    ...
```

This helper should:

- call hooks
- resolve the route
- execute fallback/provider completion
- emit metrics and headers

Then:

- existing OpenAI route becomes a thin wrapper around it
- Anthropic route can reuse it

This is the most important enabling refactor.

### Phase 2: add the bridge module

Create:

- `faigate/bridges/anthropic.py`

Recommended contents:

- `normalize_anthropic_messages_request(...)`
- `anthropic_to_openai_messages(...)`
- `anthropic_tools_to_openai(...)`
- `openai_response_to_anthropic(...)`
- `count_tokens_estimate_for_anthropic(...)`

Keep these as plain functions first.

### Phase 3: add Anthropic route module

Create:

- `faigate/api/anthropic.py`

Recommended contents:

- route registration helper, for example `register_anthropic_routes(app, ...)`
- request validation helpers for `/v1/messages`
- request validation helpers for `/v1/messages/count_tokens`

This keeps Anthropic HTTP behavior out of the already-large `main.py` while
still remaining lightweight.

### Phase 4: wire config and startup

Add config gating in `faigate/config.py`.

Suggested keys:

```yaml
api_surfaces:
  openai_compatible: true
  anthropic_messages: false

anthropic_bridge:
  enabled: false
  allow_clients: []
  model_aliases: {}
```

Guidance:

- default `anthropic_messages` to `false`
- do not enable this bridge accidentally for existing users
- keep startup behavior unchanged when disabled

### Phase 5: register the Anthropic routes

In `faigate/main.py` startup or module initialization:

- keep existing OpenAI routes untouched
- conditionally register Anthropic routes when enabled

Do not duplicate app startup or provider loading.

### Phase 6: add a Claude-specific routing hint hook

Only after the bridge path works end to end, add an optional community or core
hook for Claude-Code-specific routing hints.

This hook may look at:

- `surface=anthropic`
- `metadata.source_client`
- tool presence
- message shape indicating coding work

And then set:

- `routing_mode`
- `prefer_providers`
- `require_capabilities`

## Testing Plan

### Unit tests

- Anthropic request normalization
- Anthropic response mapping
- tool mapping
- error mapping
- token-count mapping

### API tests

- `/v1/messages` enabled and disabled
- `/v1/messages/count_tokens`
- route preview through the same router path as OpenAI requests
- fallback still works

### Regression tests

- existing `/v1/chat/completions` remains unchanged
- existing hooks still apply
- existing provider execution path still behaves the same

## Risks

### 1. `main.py` is already large

Risk:

- adding Anthropic routes directly into `main.py` would make an existing hotspot
  harder to maintain

Mitigation:

- extract only the minimal shared chat execution helper
- move Anthropic-specific HTTP handling into `faigate/api/anthropic.py`

### 2. Internal canonical format can sprawl

Risk:

- trying to support every Anthropic content block and tool nuance in v1 will
  create a second internal protocol model too early

Mitigation:

- keep canonical shape small and chat-focused
- treat advanced content blocks as later follow-up work

### 3. Hook misuse

Risk:

- pushing bridge behavior into hooks would blur protocol translation and routing

Mitigation:

- keep protocol translation entirely in the bridge module
- use hooks only for post-normalization routing hints

### 4. Streaming complexity

Risk:

- Anthropic-style streaming parity will widen the surface quickly

Mitigation:

- keep v1 non-streaming first
- add streaming only after request/response translation is stable

## Open Questions

- How much Anthropic tool-use parity is actually required for the first intended
  Claude Code / Claude Desktop workflows?
- Should `/v1/messages/count_tokens` remain an estimate in v1, or should it be
  backed by the same token heuristics already used elsewhere in Gate?
- Should the bridge expose Anthropic-specific response headers, or is body-level
  compatibility enough for v1?
- Which Anthropic model aliases should be supported from day one, and should
  those aliases resolve into lane shortcuts or literal upstream model names?

## Assumptions

- The first consumer is primarily Claude Code / Claude-compatible tooling, not
  a broad external Anthropic ecosystem migration.
- Reusing the existing OpenAI-shaped provider execution path is acceptable for
  v1 if the bridge normalizes requests carefully enough.
- We want an internal extension of `faigate`, not a separately marketed generic
  Anthropic adapter.

## Recommended Next Step

Do one small implementation slice first:

1. extract the shared chat execution helper from `faigate/main.py`
2. add `faigate/bridges/anthropic.py` with request/response mapping functions
3. add disabled-by-default `POST /v1/messages`

That is the smallest meaningful end-to-end bridge slice.
