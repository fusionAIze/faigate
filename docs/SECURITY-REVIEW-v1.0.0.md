# FoundryGate v1.0.0 Security Review

## Scope

This review covers the release-gate areas called out in the roadmap for `v1.0.0`:

- dashboard XSS and HTML/CSS injection
- request, header, and parameter injection
- dependency and unsafe-default review
- local-worker and upstream trust boundaries
- auth, secret-handling, and writable-path assumptions

## Findings And Outcomes

### 1. Dashboard XSS / HTML / CSS injection

Status: mitigated in the current runtime baseline.

- the built-in dashboard remains a static no-build page
- dynamic values are escaped before insertion into the DOM
- the dashboard now ships with a restrictive CSP using content hashes instead of `unsafe-inline`
- `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer` are enabled by default

Residual risk:

- the dashboard is still intentionally simple and unauthenticated, so it should stay bound to trusted local or operator-only network surfaces

### 2. Request / header / parameter injection

Status: mitigated for the current request surface.

- routing and operator headers are normalized and length-bounded before reaching traces, metrics, or rollout logic
- request hooks stay on a sanitized input/output surface
- oversized JSON bodies are rejected before route resolution
- oversized multipart uploads are rejected before provider calls
- provider failure details are logged internally but no longer echoed back to clients verbatim

Residual risk:

- upstream providers still define their own model- and payload-level validation semantics, so operators should keep provider-specific constraints tight in config

### 3. Dependency vulnerabilities and unsafe defaults

Status: reviewed against the current shipped surface.

- the release CI covers Ruff, CodeQL, Python tests, packaging, and artifact checks
- the runtime keeps conservative defaults for cache control and response headers
- database output stays out of the repo checkout through `FOUNDRYGATE_DB_PATH`

Residual risk:

- dependency freshness remains an ongoing maintenance task, not a one-time release action

### 4. Trust boundaries for local workers and upstream providers

Status: tightened in config validation.

- public/non-local provider URLs must now use `https`
- local or private-network workers may still use `http`
- `contract: local-worker` continues to require local/private network placement

Residual risk:

- FoundryGate is still a gateway, not an auth or service-mesh product; upstream TLS trust and network placement remain operator responsibilities

### 5. Auth, secrets, and writable paths

Status: documented and partially enforced.

- provider secrets remain environment-driven
- writable state stays outside the repo by default
- repo safety checks continue to block common artifact and secret-adjacent file types

Residual risk:

- the runtime does not currently implement end-user auth; deployments should assume a trusted local or internal edge

## Release Decision

Result: acceptable for `v1.0.0`.

The current review did not uncover a blocker that requires delaying the stable release, provided deployments keep the local-first trust model and conservative defaults intact.
