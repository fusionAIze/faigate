# Anthropic Bridge Release Readiness

This checklist is the release gate for shipping the Anthropic bridge as a production-facing feature inside `fusionAIze Gate`.

The intended release position is:

- optional and explicitly enabled
- safe for production early adopters
- not full Anthropic parity yet

The bridge should only ship when the core protocol path, fallback behavior, and operator surfaces all agree.

## Intended Release Scope

Acceptable to release:

- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- non-streaming text flows
- basic `tool_use` / `tool_result`
- Anthropic header/version tolerance
- shared-quota-aware fallback behavior

Still explicitly out of scope:

- streaming SSE parity
- image or binary content blocks
- provider-exact token counting
- claiming full Claude Desktop or Claude Code parity across all versions

## Preflight Configuration

Before release, verify that the target config has:

- `api_surfaces.anthropic_messages: true`
- `anthropic_bridge.enabled: true`
- at least one stable Claude-facing alias such as `claude-code -> auto`
- at least one non-Anthropic fallback route or local worker for continuity
- shared Anthropic quota domains marked with `transport.quota_group`
- aggregator or wallet-style routes marked with `transport.billing_mode` when BYOK collapse is possible

Recommended example:

```yaml
anthropic_bridge:
  enabled: true
  model_aliases:
    claude-code: auto
    claude-code-fast: eco
    claude-code-premium: premium

providers:
  anthropic-sonnet:
    transport:
      quota_group: anthropic-main
  kilo-sonnet:
    transport:
      billing_mode: byok
      quota_group: anthropic-main
  local-worker:
    transport:
      quota_isolated: true
```

## Validation Sequence

Run these in order on a product-like config:

1. `./docs/examples/anthropic-bridge-smoke.sh`
2. `./docs/examples/anthropic-bridge-validation.sh`
3. `./scripts/faigate-doctor`
4. `./scripts/faigate-provider-probe --json`

The second script is the more complete client-near validation path. It checks:

- Anthropic messages with version/beta headers
- basic tool-use / tool-result bridge handling
- `count_tokens`
- doctor and provider-probe output after the same config is live

## Required Test Baseline

Before release, keep these green:

```bash
env PYTHONPATH=. ./.venv-check-313/bin/pytest -q \
  tests/test_config.py \
  tests/test_providers.py \
  tests/test_anthropic_api.py \
  tests/test_anthropic_bridge.py \
  tests/test_request_hooks.py
```

and:

```bash
rtk ruff check faigate/config.py faigate/providers.py faigate/main.py \
  faigate/canonical.py faigate/bridges/anthropic/adapter.py \
  tests/test_config.py tests/test_providers.py tests/test_anthropic_api.py \
  tests/test_anthropic_bridge.py tests/test_request_hooks.py
```

## Release Criteria

Ship only if all of these are true:

- Anthropic bridge requests succeed through the normal routing core
- tool-use / tool-result flows stay on the same execution path
- Anthropic error mapping stays coherent under direct provider failures
- version/beta headers survive roundtrip handling
- shared-quota routes are skipped when one route in the same quota group fails with quota, rate-limit, or auth pressure
- doctor and provider-probe still explain route readiness clearly
- docs match the real v1 limits

## No-Go Signals

Do not release if any of these are still observed:

- a quota-exhausted Anthropic route still retries an aggregator route that shares the same upstream quota domain
- the bridge silently drops tool-use or tool-result semantics
- the bridge claims streaming support without a tested SSE implementation
- `count_tokens` is described as exact anywhere in the docs
- doctor or provider-probe make Anthropic-shaped routes look independent when they are actually BYOK-coupled

## Release Call

If the checks above pass, the bridge is reasonable to release as:

- production-usable
- opt-in
- early-adopter safe

It should not yet be marketed as:

- full Anthropic API parity
- full Claude Code parity
- full Claude Desktop parity
