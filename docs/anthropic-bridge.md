# Anthropic Bridge

`fusionAIze Gate` can optionally expose an Anthropic-/Claude-compatible bridge surface on top of the existing gateway core.

This is not a second gateway and not a sidecar. It is one extra ingress surface inside Gate.

## Purpose

Use the bridge when a client wants Anthropic-style `messages` requests, but you still want Gate to keep control over:

- provider selection
- policy and hook handling
- health-aware fallback
- route scoring
- operator visibility

That is especially useful for Claude-oriented workflows where a direct Anthropic account or subscription can hit daily or weekly limits. In that case, Gate can continue the session through:

- another Anthropic-capable route with available balance
- a coding-capable non-Anthropic route with similar context or tool fit
- a local worker when you want to stay operational without depending on one cloud account

## Architecture Overview

The bridge stays intentionally thin:

1. the Anthropic surface accepts a Claude-compatible request
2. the bridge validates and normalizes the request
3. the request is mapped into Gate's internal canonical model
4. the existing Gate core applies hooks, routing, health checks, and fallback
5. the result is mapped back into an Anthropic-compatible response

The important split is:

- bridge: protocol normalization only
- core gateway: routing and execution
- optional hook: Claude-Code-specific routing hints

## Activation

Minimal config:

```yaml
api_surfaces:
  anthropic_messages: true

anthropic_bridge:
  enabled: true
  allow_claude_code_hints: true
  model_aliases:
    claude-code: auto
    claude-code-fast: eco
    claude-code-premium: premium

request_hooks:
  enabled: true
  community_hooks_dir: "./hooks/community"
  hooks:
    - claude-code-router
```

What the keys do:

- `api_surfaces.anthropic_messages`
  - exposes the Anthropic-compatible HTTP surface
- `anthropic_bridge.enabled`
  - enables bridge parsing and response mapping
- `anthropic_bridge.model_aliases`
  - maps Claude-facing model ids to Gate routing modes or explicit provider ids
- `anthropic_bridge.allow_claude_code_hints`
  - keeps Claude-Code-specific bridge metadata available for optional hooks

## Model Alias Strategy

Keep aliases stable and operational, not provider-specific by default.

Good first aliases:

- `claude-code -> auto`
- `claude-code-fast -> eco`
- `claude-code-premium -> premium`

Built-in bridge defaults also recognize common Claude Code model ids such as:

- `claude-sonnet-4-6[1m]`
- `claude-sonnet-4-6-20251001`
- `claude-opus-4-6[1m]`
- `claude-haiku-4-5-20251001`

By default those map to routing intents, not direct frontier providers:

- `claude-sonnet-* -> auto`
- `claude-opus-* -> premium`
- `claude-haiku-* -> eco`

That keeps Claude-oriented clients on stable logical targets while Gate can still adapt the real route underneath and avoid burning Sonnet or Opus for trivial turns.

## Limits And Fallback Design

If your main Claude usage comes from one Anthropic subscription or account, be careful with aggregator routes that still depend on a BYOK Anthropic key from the same quota domain.

Recommended pattern:

- keep direct Anthropic routes probeable and clearly named
- keep Anthropic-capable aggregators as explicit mirrors or secondary routes
- do not assume a premium Anthropic mirror is independent if it uses the same exhausted account
- mark routes that can burn the same upstream quota with a shared `transport.quota_group`
- use `transport.billing_mode: byok` on aggregator routes when the wallet path may still collapse to your own upstream account
- use `faigate-doctor`, `faigate-provider-probe`, `/health`, and `/api/providers` to validate which routes are actually request-ready

## Claude Code / Claude Desktop

Client support for custom Anthropic endpoints varies by version and integration style. The safe pattern is:

1. point the client at the local Gate base URL when it supports overriding the Anthropic API endpoint
2. use one stable bridge-facing model alias such as `claude-code`
3. keep route changes inside Gate, not inside the client config

If a client cannot override the Anthropic base URL directly, use the OpenAI-compatible Gate surface instead or place a thin local wrapper in front of the client.

Practical operator guidance:

- start with one alias such as `claude-code -> auto`
- add `claude-code-fast -> eco` and `claude-code-premium -> premium` only when the client can switch models cleanly
- keep Anthropic-capable aggregator routes out of the top priority slot if they may still consume the same Anthropic account quota through BYOK
- keep at least one non-Anthropic coding-capable route or local worker available for continuity

Illustrative endpoint pattern for Claude-oriented clients that allow endpoint overrides:

```text
Base URL: http://127.0.0.1:8090
Messages path: /v1/messages
Model: claude-code
```

### Local Claude Code test path

Anthropic's current Claude Code gateway docs describe the main local-gateway path as:

- `ANTHROPIC_BASE_URL` pointing at the gateway base URL
- the gateway exposing `/v1/messages` and `/v1/messages/count_tokens`
- the gateway preserving `anthropic-version` and `anthropic-beta`

For local Gate testing, the practical flow is:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8090
export ANTHROPIC_AUTH_TOKEN=dummy-local-token
```

Notes:

- if your local Gate does not enforce client auth, the token can be a harmless placeholder; Claude Code still wants to send one
- if you place auth in front of Gate, use the real token expected by that layer instead
- keep the client pointed at one stable alias such as `claude-code`; move real route changes inside Gate
- if a given Claude Code build does not honor the endpoint override you expect, fall back to the validation scripts first and treat the client as version-sensitive

For local operator validation after the service is running:

```bash
./docs/examples/anthropic-bridge-smoke.sh
./docs/examples/anthropic-bridge-validation.sh
```

## Local Smoke Test

Use the bundled example:

```bash
./docs/examples/anthropic-bridge-smoke.sh
```

This covers:

- `POST /v1/messages`
- `POST /v1/messages/count_tokens`

For a client-near validation pass before release, run:

```bash
./docs/examples/anthropic-bridge-validation.sh
```

That broader check adds:

- bridge headers and Anthropic version/beta tolerance
- basic `tool_use` / `tool_result` flow shape
- doctor and provider-probe output after the same config is live

For the explicit release gate, see [Anthropic Bridge Release Readiness](./bridge/anthropic-bridge-release-readiness.md).

## Known v1 Limits

- non-streaming only
- text blocks plus basic `tool_use` / `tool_result`
- `count_tokens` returns a deterministic local estimate
- image or binary content blocks are not bridged yet
- the optional `claude-code-router` hook only adds routing hints
