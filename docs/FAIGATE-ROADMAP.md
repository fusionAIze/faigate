# fusionAIze Gate Roadmap

## Status

fusionAIze Gate is now the public product, runtime, and repository name.

The foundation that used to be the near-term buildout is largely in place:

- provider capability schema
- policy-based provider selection
- local worker provider contract
- client profiles and presets
- optional request hook interfaces
- multi-dimensional candidate scoring for context windows, token limits, locality, cache alignment, health, latency, and recent failures
- route introspection
- routing traces and client/profile metrics
- local worker probing
- a hardened simple dashboard with filtered traces, client/provider views, URL-persisted filters, operator summary cards, and modality/capability coverage

This roadmap now shifts from "rename and foundation" to "deepen the gateway plane without bloating it".

The next major product track is now explicit: adaptive model orchestration.

That means the next meaningful line is not just "more providers" or "more UI". It is:

- canonical model lanes
- route-aware aggregator handling
- benchmark and cost clusters
- live adaptation under quota, latency, and failure pressure
- operator explainability for every major routing decision

The detailed design lives in [Adaptive model orchestration](./ADAPTIVE-ORCHESTRATION.md).

`v1.2.0` is now shipped. The workstation baseline is in place: Linux, macOS, and Windows runtime guidance is documented, macOS helpers now auto-detect `launchd`, and a project-owned Homebrew path exists for packaged macOS installs.

`v1.2.x` also closed the immediate Homebrew/macOS packaging loop. The next active release line should therefore shift to `v1.3.0`: guided setup, catalog-assisted updates, and safer operator ergonomics for many fast-moving providers.

The next block should stay disciplined: build on the workstation baseline, keep packaging practical, and avoid turning fusionAIze Gate into a sprawling platform.

## Current release target: `v1.13.0`

The next release should land as a clean bridge release, not as a grab bag of protocol experiments.

`v1.13.0` should close around one coherent theme:

- an optional Anthropic-compatible bridge that stays inside the existing Gate core instead of spawning a second gateway or a protocol-specific routing stack

That release should feel disciplined from an operator point of view:

- Claude-native clients can enter through `/v1/messages` while Gate still owns routing, policy, fallback, and health decisions
- basic `tool_use` / `tool_result`, Anthropic header tolerance, and bridge-shaped error mapping are stable enough for everyday opt-in usage
- quota-group-aware fallback behavior avoids the most obvious "same exhausted Anthropic account via another path" mistakes
- doctor, provider probe, README, API docs, and release-readiness docs all describe the same v1 bridge limits

What is intentionally not in scope for `v1.13.0`:

- full Anthropic parity
- full Claude Code parity
- full Claude Desktop parity
- SSE streaming parity
- exact provider-side token counting

Those remain follow-on work once the opt-in bridge line has shipped and seen real operator usage.

## Next target after `v1.13.0`: make the provider catalog truly live

Once the bridge line is out, the next meaningful track should return to provider intelligence:

- move the provider-source catalog from "visible" to "continuously trustworthy"
- mirror local model visibility per key and per route more directly against the global catalog
- escalate drift, quota coupling, and stale assumptions earlier in the operator surfaces

That next line should stay operational:

- no second platform
- no sprawling memory layer
- no heavy UI dependency just to understand route health

## Shipped: `v1.8.0` – `v1.9.1`

The adaptive model orchestration foundation is fully in place:

- **v1.8.0** ✅ lane registry, provider lane metadata, route-aware catalog surfaces
- **v1.9.0** ✅ lane-aware router scoring, "why this lane?" traces, short-complex escalation
- **v1.9.1** ✅ routing bug fixes, signal group expansion (10 groups), mode-override hook, load_dotenv fix

What shipped in v1.9.1 specifically:

- `load_dotenv()` now correctly resolves `faigate.env` from the config directory (fixed 0/10 providers unresolved-key state under Homebrew launchd)
- `short_complex` prompts (< 80 tokens, ≥ 2 signal groups) bypass `short-message` and `general-default` heuristic rules and reach profile scoring correctly
- `prefer-provider-header` hook correctly bypasses `general-default` fallthrough
- New `mode-override-header` hook: `X-faigate-Mode` header sets routing posture per-request
- `_routing_posture()` checks `hook_hints.routing_mode` before `profile_hints`
- 5 new `opencode` signal groups: `devops`, `testing`, `security`, `database`, extended `architecture`
- Plural keyword matching fixed: `unit tests`, `integration tests` now detected correctly

Non-negotiable guardrails that remain in effect across all future releases:

- never hide a downgrade from operators
- prefer same-lane route substitution before weaker-model degradation
- keep old configs compatible while new metadata is introduced
- treat benchmarks and cost heuristics as curated operational inputs, not as magic constants

---

## `v1.9.2`: quick-win observability and pre-failure rate limiting

Primary goals:

- surface routing context to clients without requiring them to read `/api/route`
- reduce 429 cascades proactively instead of reacting after errors occur

### `x-faigate-trace-id` response header

Every response adds `x-faigate-trace-id: <sqlite-row-id-or-uuid>` so clients (opencode, openclaw, n8n) can correlate their own logs with Gate traces at `/api/traces`. One-line addition to the response pipeline in `main.py`. Costs nothing operationally.

### Live RPM/TPM headroom scoring

Currently Gate reacts to rate-limit errors after they happen (via the typed cooldown windows). This adds a pre-failure layer:

- new `rpm_limit` and `tpm_limit` optional fields in provider config
- rolling request counter per provider per minute in `adaptation.py` state (in-memory, no persistence required)
- when a provider exceeds 80% of its configured limit, apply a soft scoring penalty in the provider scoring layer
- penalty scales linearly from 80% to 100% headroom; at 100% the provider is temporarily excluded (same as a live rate-limit error but proactive)
- no change to the cooldown model — this is a pre-failure complement, not a replacement

This is a direct answer to LiteLLM's `usage-based-routing` strategy and eliminates the majority of observable 429 cascades in high-throughput operator deployments.

---

## `v1.10.x`: provider intelligence layer

The canonical lane registry is already the strongest differentiator vs LiteLLM and OpenRouter. This release line deepens it into a managed data product — richer, fresher, and directly queryable by the scoring engine.

### Granular capability tag matrix

Current state: `reasoning_strength: high`, `context_strength: mid`, `tool_strength: medium` as string labels.

Target: a full capability matrix per lane that the scoring engine can use directly:

| Tag | Values | Scoring use |
|-----|--------|-------------|
| `reasoning_strength` | `high / mid / low` | reasoning lane selection |
| `context_strength` | `high / mid / low` | long-context routing |
| `tool_strength` | `strong / medium / weak` | tool-use heuristic |
| `latency_tier` | `fast / standard / slow` | TTFT-sensitive routing |
| `coding_strength` | `high / mid / low` | code signal group weighting |
| `instruction_following` | `high / mid / low` | structured output routing |
| `vision` | `true / false` | multimodal routing guard |
| `multilingual` | `true / false` | locale-aware routing (future) |

Each tag feeds directly into scoring formulas rather than being a post-hoc label. A `latency_tier: fast` lane gets a scoring bonus when `stream: true` and expected output is short. A `coding_strength: high` lane gets a bonus when `devops` or `testing` signal groups fire.

### Richer benchmark cluster metadata

Current state: `benchmark_cluster: balanced-coding` — a single string label.

Target: structured object per lane:

```yaml
benchmark:
  cluster: balanced-coding
  coding_rank: 3          # ordinal rank within cluster (1 = best)
  reasoning_rank: 2
  cost_efficiency_rank: 1
  last_reviewed: 2026-03-24
  freshness_days: 1
  sources:
    - LiveCodeBench-2025-Q1
    - Aider-Polyglot-2025-03
    - MATH-500
```

Rank `1` beats rank `3` in the same cluster when other factors are equal. Today operators have to hold this in their heads; with structured ranks the scoring engine can quantify it. The `sources` array makes the basis for quality assumptions explicit and auditable.

### Context window cache intelligence

Current state: `cache.mode: implicit/explicit/none` and `cache_read_discount: 0.1` as flat fields. No TTL, no minimum prefix threshold per provider.

Target: full cache spec per provider:

```yaml
cache:
  mode: implicit              # implicit / explicit / none
  min_prefix_tokens: 1024     # minimum stable prefix for cache to activate
  ttl_seconds: 300            # provider cache lifetime (Anthropic: 5 min, OpenAI: ~1 h)
  max_cached_tokens: 32000    # max tokens in prefix that stay cached at this provider
  cache_read_discount: 0.1    # cost of cached input tokens vs fresh input tokens
  cache_write_surcharge: 1.25 # explicit mode only: write cost multiplier (Anthropic: +25%)
```

Routing decisions this enables:

- if `stable_prefix_tokens >= cache.min_prefix_tokens` → prefer providers where `ttl_seconds` exceeds the expected session duration
- if `total_tokens > cache.max_cached_tokens` → warn operator: cache will not activate at this provider for this request size
- `cache_write_surcharge` makes explicit cache-insert cost calculable in the scoring layer (today it is invisible)
- session-aware routing: routes with recent cache hits on the same stable prefix get a cost-adjusted scoring bonus

This is where faigate genuinely beats both LiteLLM and OpenRouter. LiteLLM models gateway-level response caching (full response deduplication). OpenRouter exposes prompt caching implicitly but does not surface TTL or minimum prefix thresholds. faigate models provider-side prompt caching semantics explicitly — which is more accurate for how Anthropic and OpenAI actually implement it.

### Fresher provider pricing and auto-update cadence

Current state: `last_reviewed` and `freshness_status` are manually maintained. No automated pricing drift detection.

Target:

- `faigate-auto-update` fetches a `provider-catalog.json` from a configured endpoint (fusionAIze-hosted or self-hosted)
- diffs incoming pricing against local `lane_registry.py` values
- emits an operator event when pricing drift exceeds 20% on any lane
- new `pricing.stale_since_days` field in provider config; scoring engine applies an uncertainty penalty when pricing is stale
- pricing update can be applied via `faigate-update` or operator approval flow, not silently

### TTFT and throughput as routing signals

Current state: `latency_ms` is recorded per request in metrics. No per-provider TTFT profile exists; no latency-sensitive routing path.

Target:

- rolling TTFT (time-to-first-token) measured per provider in the response pipeline
- `p50_ttft_ms` and `p95_ttft_ms` per provider stored in `adaptation.py` state
- new request insight: `latency_sensitive: true` when `stream: true` and expected output token count is short (< 500 tokens)
- `latency_sensitive` prompts prefer providers where `p50_ttft_ms` is low and `latency_tier: fast`
- TTFT profiles decay over time (30-minute rolling window) so a provider that was fast this morning but slow now loses its advantage

### Named routing strategy aliases (operator legibility)

LiteLLM lets operators set `routing_strategy: latency-based-routing` and understand what they're getting. faigate's scoring is richer but less legible to operators who are evaluating it or comparing it against alternatives.

Add an optional `routing_strategy` config field that maps to scoring weight presets:

| Strategy alias | Effect on scoring weights |
|----------------|--------------------------|
| `latency-first` | `p50_ttft_ms` weight ×3, cost weight ×0.5 |
| `cost-first` | cost weight ×3, quality tier weight ×0.5 |
| `quality-first` | benchmark rank weight ×3, cost weight ×0.5 |
| `balanced` | default weights (current behavior) |

The multi-dimensional engine does not change — only the weight distribution shifts. Operators can audit what they're getting; the engine stays the same under the hood.

---

## `v1.11.x`: virtual key layer and gateway-level response caching

### Virtual key layer (Tier B)

This is the single largest remaining gap between faigate and LiteLLM for any deployment with more than one operator or client that needs cost accountability. It is also the natural anchor feature for Tier B commercial positioning.

Per-key fields:
- `max_budget` and `budget_duration` (daily / weekly / monthly)
- `rpm_limit` and `tpm_limit`
- `allowed_models` (restrict a key to specific canonical lanes or routing modes)
- `hard_limit: true/false` — hard blocks the request vs soft logs-only
- key lifecycle: create, rotate, expire, disable

Implementation:
- SQLite-backed key registry (no Postgres required)
- budget enforcement at the routing decision point, before any provider call
- `x-faigate-api-key` request header (or standard `Authorization: Bearer` with a virtual key prefix)
- spend ledger per key per day in the existing `metrics.py` schema
- `/api/keys` endpoint for key management (operator-only, behind operator secret)

This feature is Tier B from day one. It will not be backslid to Tier A. This boundary should be announced in the roadmap before the feature ships.

### Gateway-level response caching (exact match)

Distinct from provider-side prompt caching. This eliminates provider calls entirely for repeated identical prompts.

- canonical request hash: `sha256(model + messages + temperature + tool_choice + response_format)` — normalised before hashing so field order does not matter
- in-memory LRU cache with configurable `max_entries` and `ttl_seconds`
- cache hit returns the stored response directly, sets `x-faigate-cache: hit` response header
- cache miss records the response and stores it if eligible (streaming responses are not cached at this stage)
- cost savings from cache hits are recorded in metrics and visible in the dashboard
- Redis backend as an optional future extension for shared-state multi-process deployments

### Webhook / callback observability output

Add configurable `success_callbacks` and `failure_callbacks` in config (list of URLs). On each completed request, POST a structured JSON event (same fields as the metrics schema) to each configured URL. This unlocks Langfuse, Helicone, Datadog, and custom sinks with zero deep-integration work. The data model already captures everything needed.

### Reference guardrail hook implementations

The hook seam in `hooks.py` supports fail-closed behavior via `HookExecutionError`. Ship two reference guardrail implementations to make the seam credible for enterprise evaluation:

1. `keyword-blocklist` hook: configurable list of blocked terms; fails closed with 400 if matched
2. `max-prompt-tokens` hook: rejects requests exceeding a configurable token count before any provider call

Full Presidio (PII detection) and Lakera (prompt injection) integrations are natural Tier B additions that follow the same hook seam.

---

## `v2.x`: multi-instance, team budgets, semantic caching

### Team and org budget hierarchy

Extends virtual keys to a `user → team → org` hierarchy with cascading spend limits. Cascading means: a user's spend counts against their own budget and their team's budget simultaneously. A team that hits its limit blocks all member keys regardless of individual balances.

Requires a small relational model in SQLite (three tables: `orgs`, `teams`, `keys`). An optional Postgres backend becomes worth offering at this stage for deployments that need shared state across multiple gateway instances or that have audit requirements.

### Multi-instance shared state via Grid

faigate's local-first, SQLite-only design means each gateway instance has independent state. For teams running faigate on multiple machines or in a cluster there is no shared spend state, no distributed rate-limit tracking, and no cross-instance cache coherence.

The answer is not to add Redis and Postgres to Gate. The answer is **Grid** — the multi-instance coordination layer in the fusionAIze stack. Gate should stay single-instance-friendly and expose a stable API contract that Grid consumes. Grid manages the coordination; Gate manages the routing.

This is a cleaner product boundary than LiteLLM's approach of coupling the proxy runtime with shared infrastructure dependencies.

### Semantic caching

Embedding-based similarity lookup: incoming prompt is embedded, compared to cached prompts by cosine similarity above a configurable threshold. Higher cache hit rate for semantically equivalent prompts than exact hash matching.

Requires a vector store backend (in-memory for development, Qdrant or Redis Vector for production). High operational cost; only worth building after exact caching is solid and usage patterns demonstrate that the operator's workload has sufficient prompt homogeneity for semantic caching to materially improve hit rates.

### OTEL-compatible trace context

Full `traceparent` header forwarding and span emission for OpenTelemetry-compatible backends. Native Langfuse SDK integration beyond the webhook/callback layer. This is the observability completion milestone — the data model is already complete from v1.9.x; this release adds the integration glue.

---

## Competitive positioning: where faigate leads

This section documents the specific capabilities where faigate is ahead of LiteLLM, OpenRouter, and ClawRouter — and where the product should double down rather than copy competitors' approaches.

### vs LiteLLM

| Capability | faigate | LiteLLM |
|---|---|---|
| Routing model | Multi-dimensional score (quality × cost × benchmark × pressure × locality) | Single-axis `routing_strategy` |
| Failure model | Typed cooldowns: `auth-invalid`, `quota-exhausted`, `rate-limited` with different TTLs | Generic time-based cooldown |
| Client-profile routing | Separate routing behavior per client (`opencode`, `openclaw`, `n8n`, `cli`) | No equivalent |
| Pre-routing hook pipeline | Full hook pipeline with fail-closed `HookExecutionError` | Post-call callbacks only |
| Canonical lane abstraction | Routes to a capability lane (e.g. `anthropic/sonnet`), then selects transport | Routes to a deployment pool by string name |
| Provider-side cache semantics | TTL, min-prefix, max-cached-tokens, write surcharge modelled per provider | Gateway-level response cache only |
| Provider catalog freshness | `last_reviewed`, `freshness_status`, per-lane review age | Not tracked |
| Local-first, zero external deps | SQLite only, no Redis or Postgres required | Redis + Postgres for full feature set |
| Licensing | Apache 2.0 gateway core permanently | BSL 1.1 for the proxy; Apache 2.0 for SDK only |

The canonical lane abstraction is the primary structural advantage. LiteLLM cannot replicate it without a near-full rewrite of its routing layer.

### vs OpenRouter

OpenRouter is a hosted aggregator, not a local gateway. The comparison is about philosophy and capability, not deployment model.

| Capability | faigate | OpenRouter |
|---|---|---|
| Data residency | Local-first; requests go directly to providers from operator's machine | All requests transit OpenRouter infrastructure |
| Custom client profiles | Full per-client routing behavior | Not available |
| Operator-owned config | Full YAML config; operator controls every routing decision | Model selection only; routing is OpenRouter's black box |
| Cache semantics | Explicit per-provider cache spec (TTL, min-prefix, discount) | Implicit; not surfaced to operators |
| Provider fallback control | Explicit degrade-to chains, same-lane substitution first | Available but not configurable per-scenario |
| Cost calculation | Cache-aware, per-provider, calculable before the call | Post-call only |
| Hybrid local+cloud | Local workers as first-class providers | Cloud-only |
| No vendor lock-in | Operators own their credentials and route directly | All traffic through OpenRouter; single vendor dependency |

faigate's answer to OpenRouter is: **you keep your keys, your traffic goes direct, and you get the same model-selection intelligence with explicit control over every routing decision**.

### vs ClawRouter

ClawRouter is architecturally closer to faigate than LiteLLM — it focuses on agent-native routing and transport bindings rather than fleet management. Key comparisons:

| Capability | faigate | ClawRouter |
|---|---|---|
| Agent-native clients | `openclaw` client profile, `x-openclaw-source` multi-agent header | Core focus |
| Transport bindings | `direct`, `aggregator`, `wallet-router` route types in lane registry | Primary differentiator |
| Local worker contract | Full health-probe and local worker provider type | Limited |
| Signal-group complexity scoring | 10 signal groups, short_complex escalation, per-client profiles | Not present |
| Provider catalog | Lane registry with benchmark clusters, freshness, degrade-to chains | Minimal |
| Request hooks | Full pipeline with routing hint injection | Not present |
| Routing transparency | Full trace with why-not-selected, lane reasoning, selection path | Limited |

ClawRouter's transport binding model (`direct`, `wallet-router`, `aggregator`) is well-designed and faigate should adopt its vocabulary in `lane_registry.py` — this is already partly done (`route_type: direct / aggregator / wallet-router`). The area where faigate leads is the full provider-intelligence layer: ClawRouter does not model benchmark clusters, cache semantics, or per-client signal scoring.

What faigate can learn from ClawRouter: deeper agent-native transport contracts, richer `x-openclaw-*` header semantics for multi-agent delegation flows.

---

## `v1.8.0` to `v1.11.x`: adaptive model orchestration (original sequence for reference)

Primary goals:

- treat providers, aggregators, and direct routes as execution paths to canonical model lanes rather than as one flat list of alternatives
- let scenarios such as `quality`, `balanced`, `eco`, and `free` choose the right lane threshold and degradation path instead of only choosing a provider tier
- preserve same-lane quality when direct quota is exhausted by trying equivalent aggregator routes before dropping to a weaker model cluster
- keep benchmark and cost assumptions visible, curated, and refreshable so "magical" routing still stays explainable

Release sequence:

1. `v1.8.0` ✅ lane registry, provider lane metadata, and route-aware catalog surfaces
2. `v1.9.0` ✅ lane-aware router scoring and "why this lane?" traces
3. `v1.9.1` ✅ routing bug fixes, signal group expansion, mode-override hook
4. `v1.9.2`: pre-failure RPM/TPM headroom, trace-id header
5. `v1.10.x`: provider intelligence layer (capability tags, benchmark ranks, cache TTL, TTFT, pricing freshness)
6. `v1.11.x`: virtual key layer, gateway-level response caching, webhook observability, guardrail hooks
7. `v2.x`: team/org budget hierarchy, multi-instance Grid coordination, semantic caching, OTEL

Non-negotiable guardrails:

- never hide a downgrade from operators
- prefer same-lane route substitution before weaker-model degradation
- keep old configs compatible while lane metadata is introduced
- treat benchmarks and cost heuristics as curated operational inputs, not as magic constants

## `v1.5.0`: guided control-center UX

Primary goals:

- make the standalone Gate shell feel like the first serious product surface instead of a loose set of helper scripts
- introduce one obvious happy path for first setup, validation, restart, and client connection
- replace raw JSON-first operator views with compact human summaries plus drill-downs where needed
- keep the Gate UX aligned with the later Grid orchestration direction so the products feel like one family

Recommended minimal slices:

1. `Quick Setup` happy path inside `faigate-menu`
2. compact summary cards for gateway, config, providers, and clients in the main operational menus
3. shorter, recommendation-first client quickstarts with per-client drilldown instead of long first-contact dumps
4. explicit next-step receipts after wizard, validation, restart, and client-setup actions

Guardrails:

- keep the shell UX scriptable and helper-driven; do not turn `faigate-menu` into a full-screen TUI yet
- prefer compact default output plus optional detail/raw views over large payload dumps
- keep wording calm and operational, especially when health, service-manager state, and bound port state disagree

Post-`1.5.0` UX items already worth bookmarking:

- readiness score and richer setup progress scoring
- port/runtime conflict auto-detection with one-step recovery suggestions
- client route previews that show where a given client would land right now
- richer action receipts and broader `what to do next` guidance
- more compact client cards before the long quickstart text

## Licensing strategy

The fusionAIze stack uses a three-tier open-core model. The tier boundaries are defined here before the features exist so there are no retroactive surprises for the community.

**Non-negotiable rule**: a feature that ships as Tier A will never be moved to Tier B or Tier C. Only newly-built features can be Tier B or Tier C from day one.

This is the lesson from LiteLLM's BSL transition: moving the proxy from Apache 2.0 to BSL 1.1 after the community had adopted it created lasting distrust and reputational damage. faigate will not repeat that mistake.

### Tier A — Apache 2.0 (permanent)

The full local gateway runtime, as it exists and as it will continue to evolve through routine improvements:

- baseline gateway core: routing engine, heuristic rules, hook pipeline, fallback chains
- all provider adapters: direct, aggregator, wallet-router
- all built-in request hooks: locality, prefer-provider, profile-override, mode-override
- client profile system and opencode / openclaw / n8n / cli profiles
- config schema and YAML format
- SQLite metrics store and trace recording
- operator dashboard (read-only)
- `/api/route`, `/api/stats`, `/api/traces`, `/api/providers` endpoints
- all helper scripts: `faigate-menu`, `faigate-doctor`, `faigate-status`, `faigate-update`, etc.
- Homebrew formula and packaging
- everything shipped through v1.9.x and all future routine routing improvements

### Tier B — Source-available (open-core)

Features built for operators who run faigate at team or production scale. Defined as Tier B before they are built:

- virtual key layer (`max_budget`, `budget_duration`, `rpm_limit`, `allowed_models`, key lifecycle)
- per-key budget enforcement and spend ledger
- webhook / callback observability output to external sinks (Langfuse, Helicone, Datadog)
- advanced guardrail hook implementations (PII detection via Presidio, prompt injection via Lakera)
- named routing strategy weight presets as a commercial operator convenience
- gateway-level response caching with Redis backend
- team and org budget hierarchy

### Tier C — Proprietary / commercial (fusionAIze OS)

Control-plane features that belong with the broader fusionAIze stack, not with the local gateway runtime:

- managed control plane (fusionAIze Grid / OS)
- SSO / SAML / OIDC authentication for the operator UI
- RBAC and audit logs for team and org management
- multi-instance shared state and distributed rate-limit coordination (Grid)
- enterprise SLAs and priority support

### Product stack and tier mapping

| Product | Role | Tier |
|---|---|---|
| **Gate** | Local-first routing runtime | A core + selective B |
| **Lens** | Observability and spend analytics consuming Gate `/api/stats`, `/api/traces`, webhook events | B–C |
| **Grid** | Multi-instance coordination: distributed rate limits, shared virtual key registry, cross-instance cache | C |
| **OS** | SSO, RBAC, audit logs, team management — LiteLLM Enterprise's territory | C |
| **Fabric** | Content policy and guardrail enforcement via Gate's hook seam | B–C |

## `v1.3.0`: guided setup and catalog-assisted updates

Primary goals:

- make first setup and later provider updates realistic without turning `config.yaml` into hand-edited drift bait
- keep routing modes, client defaults, and provider selection understandable across many clients
- improve provider-catalog freshness and update suggestions without silently rewriting operator intent
- start the provider-discovery and recommendation-link line only in a transparency-first, metadata-first shape

Recommended minimal slices:

1. wizard candidate selection, update suggestions, dry-run summaries, and backup-aware writes
2. provider-catalog source metadata, offer-track volatility flags, and freshness alerts
3. wizard and CLI usage polish so the guided flow is self-explanatory from `--help`
4. optional provider recommendation-link metadata with explicit disclosure, but still no ranking changes based on provider-link metadata

Guardrails for any recommendation-link work in this line:

- recommendation ranking must never use provider-link metadata as an input and must stay performance-led, preferring fit, quality, health, capability, and cost behavior
- provider-link metadata should stay operator-owned and secret-backed, not embedded in user-editable client configs
- docs and CLI output should disclose clearly when a shown signup link is informational only
- the first slice should be metadata and display only; managed short links, browser control-center surfaces, and richer landing-page flows can come later

## `v1.2.0`: workstation operations baseline

Primary goals:

- add a dedicated workstation operations guide
- document macOS `launchd` as a first-class local-runtime path
- document Windows Task Scheduler / PowerShell as the baseline Windows path
- keep development checkouts and runtime installs clearly separated
- add a project-owned Homebrew packaging path for macOS workstations

Recommended minimal slices:

1. workstation baseline docs and path layout
2. macOS `launchd` example and instructions
3. Windows startup examples and documentation
4. optional lightweight install helpers only if the docs prove insufficient
5. Homebrew formula and `brew services` guidance for the packaged macOS path

## Post-1.0 direction

The first post-`1.0` block should stay narrow enough to ship as `v1.1.0`.

Primary goals:

- double-check and extend AI-native client support beyond the current OpenClaw, n8n, and CLI baseline
- ship the next wave of integration starters for requested and high-signal agent frameworks
- expose more useful per-client token and usage metrics in the operator surface
- audit the routing-stage stack so the responsibility of each layer stays clear
- keep a structured watch on ClawRouter-style product evolution without copying features blindly

The current framework prioritization lives in [AI-NATIVE-MATRIX.md](./AI-NATIVE-MATRIX.md).

## Big Picture

The opportunity is not to build another thin router.

The opportunity is to build a reusable AI gateway plane that works across:

- local model workers
- direct provider APIs
- proxy providers
- OpenClaw
- workflow systems such as n8n
- CLI-native development environments
- agent tools
- future AI-native SaaS products

If the core stays disciplined, fusionAIze Gate can become the common routing and policy layer shared by several products without collapsing into a bloated platform.

That is the target shape:

- one gateway core
- many providers
- many clients
- optional context and optimization layers
- clear operational boundaries

## Design principles

### 1. Gateway first

fusionAIze Gate should stay a gateway and control plane, not a monolithic platform.

### 2. Standard protocols first

If a client can use the OpenAI-compatible API cleanly, keep it on that path before building a custom adapter.

### 3. Multi-dimensional routing

The design target is to exceed simpler router behavior by making routing explicitly multi-dimensional.

That means fusionAIze Gate should increasingly consider:

- capability support
- health and latency
- cost tier
- local vs cloud locality
- context window size
- cache behavior and cache pricing
- tool usage
- client identity
- modality requirements
- compliance or tenancy constraints

The intent is not to claim that this is fully implemented today. The intent is to make this the guiding routing architecture.

### 4. Optional extension layers

Context, memory, optimization, and sidecar adapters should plug into the gateway cleanly, not become mandatory core behavior.

## Current runtime baseline

Today the runtime already supports:

- one OpenAI-compatible endpoint
- multiple providers behind a single local base URL
- policy, static, heuristic, client-profile, and optional LLM-assisted routing stages
- direct model pinning and fallback chains
- local worker contracts and health probes
- route introspection and traces
- client-aware routing defaults for OpenClaw, n8n, and CLI callers

The next runtime gap to close is not “more core abstraction”. It is “more real clients with less glue”.

## `v1.1.0`: AI-native client expansion and operator visibility

Primary goals:

- add the first post-`1.0` starter wave for requested and high-signal AI-native clients
- add a curated framework matrix so external users can quickly see where fusionAIze Gate fits
- deepen client and token reporting in API and dashboard surfaces
- review policy, static, heuristic, hook, client-profile, and classifier boundaries with clearer ownership and tests

Recommended minimal slices:

1. AI-native client matrix plus roadmap update
2. first-wave starter templates for `SWE-AF`, `paperclip`, `ship-faster`, and the highest-fit external frameworks
3. per-client token and usage reporting in stats and dashboard views
4. routing-layer review plus targeted rule/test cleanup

The plugin question should stay explicitly out of scope for `v1.1.0` and be revisited only after this release line lands.

## OpenClaw direction

OpenClaw remains a first-class integration surface.

Current coverage:

- one-agent traffic through the normal OpenAI-compatible path
- many-agent or delegated traffic through the same path with `x-openclaw-source`
- OpenClaw-side model aliases and profile defaults

Near-term direction:

- document one-agent and many-agent behavior explicitly
- keep the integration header-based and OpenAI-compatible
- avoid forking the core gateway logic just for OpenClaw

## Modality expansion

Inspired by the value of image-router patterns in other gateways, fusionAIze Gate should eventually support modality-aware routing beyond chat.

Planned direction:

- add a provider contract for image-generation-capable backends
- add modality-aware request classification
- route image tasks to the right backend without polluting the chat path

This is a roadmap item, not a current runtime claim.

## Architecture direction

### Gateway core

Responsibilities:

- request normalization
- route selection
- fallback handling
- timeout boundaries
- usage and trace recording
- operational endpoints

### Provider layer

Responsibilities:

- cloud providers
- OpenAI-compatible proxies
- local workers
- future modality-specific providers

### Client layer

Responsibilities:

- OpenClaw
- n8n and workflow clients
- CLI wrappers and proxy clients
- future AI-native app integrations

### Optional extension layer

Responsibilities:

- request hooks
- context or memory enrichment
- optimization hooks
- policy overlays

## Release path to v1.0.0

`v0.3.0` is the first public fusionAIze Gate release. The path to `v1.0.0` should stay incremental and reviewable.

### `v0.4.x`: deeper routing and extension hardening

Primary goals:

- deepen multi-dimensional scoring beyond simple fit checks for cache behavior, context windows, provider limits, locality, latency, and recent failures
- keep refining the simple dashboard around traces, provider/client breakdowns, route visibility, and safe operator ergonomics
- keep OpenClaw one-agent and many-agent flows on the same OpenAI-compatible path with clearer defaults
- harden the request hook seam for context, memory, and optimization layers, including fail-closed behavior and input sanitization

This release line should deepen the gateway core without turning it into a monolith.

### `v0.5.0`: operator distribution baseline

Primary goals:

- add the first modality-aware provider contract, starting with image generation
- publish an official Docker release path
- publish fusionAIze Gate to PyPI
- add provider and client onboarding helpers for many-provider and many-client deployments
- add a publish dry-run path for Python package and GHCR validation before real release tags
- add validation workflows so operators can catch config mistakes before rollout
- complete the public community-health baseline and security-overview baseline for the repo

This is the first release line where installation and upgrade paths should feel productized for external users.

### `v0.6.x`: modality expansion

Primary goals:

- add modality-aware provider contracts, starting with image generation
- extend that contract toward image editing where the provider surface supports it
- keep chat and image paths explicit instead of mixing modality-specific behavior into one opaque route
- expose modality-aware health, provider inventory, and routing visibility in the dashboard and operational endpoints

This should borrow the useful parts of image-router patterns without copying another gateway's product shape.

### `v0.7.x`: operations polish

Primary goals:

- expand the release-check baseline into stronger update alerts so operators can see when a newer release is available
- add an optional automatic update enabler for controlled deployments
- improve route traces, metrics, and dashboard filters for providers, clients, and profiles
- keep the dashboard simple, read-heavy, and operationally safe

This release line is about day-2 operations rather than new routing concepts.

The first small slice in this line is to turn `GET /api/update` from a plain boolean check into an operator-facing alert surface with update type, alert level, and recommended action.

The next small slice is to keep auto-update conservative:

- disabled by default
- no checkout mutation over HTTP
- helper-driven and operator-triggered only
- major upgrades still manual unless explicitly allowed

### `v0.8.x`: many-provider and many-client onboarding

Primary goals:

- make onboarding repeatable for many providers and many clients on one gateway
- ship clearer presets and validation for OpenClaw, n8n, CLI wrappers, and future AI-native applications
- reduce manual config editing for common deployment shapes
- tighten integration coverage for delegated or many-agent traffic where headers identify sub-clients

The target is faster adoption without custom glue for every client.

Current `v0.8.x` baseline already includes:

- onboarding report plus validation helpers
- staged provider rollout reporting
- client matrix reporting
- starter templates for OpenClaw, n8n, CLI, cloud providers, local workers, and image providers
- matching provider `.env` starter files
- delegated OpenClaw request examples
- starter custom-profile examples for future AI-native applications
- doctor checks for missing provider env placeholders
- JSON and Markdown onboarding exports

### `v0.9.x`: pre-1.0 hardening

Primary goals:

- stabilize request hook boundaries and extension contracts
- expand integration and functional test coverage across real client flows
- complete documentation review across README, onboarding, integrations, troubleshooting, and release docs
- close obvious operational gaps discovered during earlier releases

This release line should leave `v1.0.0` focused on stability and security gates, not backlog cleanup.

Current `v0.9.x` baseline is aimed at:

- conservative response headers and dashboard CSP defaults
- explicit JSON and multipart size guardrails
- bounded routing and operator header handling
- broader functional API tests around dashboard, routing, and upload surfaces
- documentation updates that make the hardened defaults visible to operators

### `v1.0.0`: stable gateway baseline

Primary goals:

- declare a stable fusionAIze Gate gateway baseline for local-first, multi-provider routing
- publish the first separate npm CLI package for fusionAIze Gate-adjacent CLI usage
- complete a comprehensive security review before release

The `v1.0.0` security review should explicitly cover:

- cross-site scripting and HTML or CSS injection risks in the dashboard
- request, header, and parameter injection risks in proxy and routing paths
- dependency vulnerabilities and unsafe defaults
- local-worker and upstream proxy trust boundaries
- auth, secret-handling, and writable-path assumptions

`v1.0.0` should only ship after those review results are addressed or documented with a clear mitigation plan.

Current `v1.0.0` baseline is aimed at:

- dashboard CSP hardening without turning the no-build UI into a separate frontend app
- reduced leakage of upstream provider failure details in client responses
- clearer trust-boundary validation for provider base URLs
- a documented release-gate security review with explicit residual risks
- a separate npm CLI package that complements the Python gateway instead of replacing it

## Updated near-term PR sequence

The next sequence should ladder directly into the release path above:

1. `feat(provider): add modality-aware provider contracts, starting with image generation`
2. `feat(provider): extend modality contracts toward image editing where supported`
3. `feat(onboarding): add provider/client onboarding helpers and validation workflows`
4. `feat(dist): add Docker release path and PyPI publishing baseline`
5. `feat(ops): add update alerts and an optional auto-update enabler for controlled deployments`
6. `feat(cli): define the separate npm or TypeScript CLI package path for the v1.0.0 line`

## Check on the earlier sequence

The earlier near-term sequence is now effectively complete up through the routing and observability foundation:

1. `docs: add fusionAIze Gate roadmap and rename note` -> done
2. `feat(config): add provider capability schema` -> done
3. `feat(router): add policy-based provider selection` -> done
4. `feat(provider): add local worker provider contract` -> done
5. `feat(api): add client profile support` -> done
6. `feat(obs): add route introspection and policy metrics` -> done, and now extended with traces and local worker probing
7. `feat(ext): add optional request hook interfaces` -> done
8. `feat(router): add first multi-dimensional route-fit inputs for cache, context windows, provider limits, and locality` -> done
9. `feat(obs): harden the simple dashboard around traces, provider/client filters, and route visibility` -> done

## Detailed near-term backlog

### 1. Optional request hook interfaces

Why:

- this creates the seam for context, memory, and optimization layers without hard-coupling them

Examples:

- optional memory or context enrichment before routing
- request-shaping hooks for RTK-like CLI optimization
- operator-controlled extension points that can stay disabled by default

### 2. Multi-dimensional routing inputs

Why:

- routing should understand more than keywords and simple tier preferences

Examples:

- cache-read vs cache-miss economics
- context window fit
- locality and policy constraints
- latency/health tradeoffs
- provider-specific max context and cache behavior

### 3. Simple dashboard hardening

Why:

- fusionAIze Gate already exposes a dashboard endpoint, but operators need a clearer read-only control surface

Examples:

- route trace table with provider and client filters
- provider health panel with capabilities and contract type
- quick links to dry-run routing and recent failure context

### 4. Image generation and editing routing

Why:

- multi-modal routing is a natural next expansion for a gateway plane

Examples:

- image-generation-capable provider contracts
- image-editing-capable provider contracts
- explicit modality routing so chat, image generation, and image editing stay understandable

### 5. Provider and client onboarding helpers

Why:

- many-provider, many-client deployments need a clearer adoption path than manual config editing alone

Examples:

- bootstrap helpers for provider credentials and base URLs
- starter profiles for OpenClaw, n8n, CLI, and future AI-native applications
- preflight config validation before a rollout or restart

### 6. Update alerts and optional automatic update enablers

Why:

- operators need a safer path than only ad hoc manual updates

Current baseline:

- cached release checks via `GET /api/update`
- dashboard visibility for current vs latest known release
- local helper access via `faigate-update-check`
- opt-in eligibility reporting and helper-driven apply flow via `faigate-auto-update`

This should remain opt-in and operationally conservative as it expands toward scheduled helper use, stronger rollout controls, clearer operator approval boundaries, and small rollout-ring/channel distinctions.

### 7. Distribution channels

Why:

- the project should become easier to adopt without coupling packaging strategy to one runtime

Examples:

- GitHub Releases as the default channel now
- Docker images and PyPI packages by `v0.5.0`
- a separate npm or TypeScript CLI package by `v1.0.0`, not a Node rewrite of the core gateway

### 8. Security review as a release gate

Why:

- `v1.0.0` needs a credible stability and security bar, not just a larger feature list

Examples:

- dashboard rendering review for XSS and HTML or CSS injection paths
- request routing review for injection, header abuse, and unsafe forwarding behavior
- dependency and configuration review for known vulnerabilities and insecure defaults
- documentation review so security expectations and deployment assumptions are explicit

## Documentation direction

fusionAIze Gate should be understandable from the outside in under a few minutes.

That means keeping these docs current:

- README for the landing page
- architecture for technical orientation
- integrations for OpenClaw, n8n, CLI, and future clients
- onboarding for many-provider and many-client adoption
- troubleshooting for operators
- process docs for contributors

## Review cadence

Every 4 or 5 merged PRs, run a broader review pass:

- review unit tests
- review integration tests
- review functional coverage against real workflows
- update every relevant doc
- refresh the roadmap and process docs if the direction changed

This is necessary because fusionAIze Gate is evolving quickly and the docs can drift even when individual PRs are clean.

## Provider discovery and recommendation links

fusionAIze Gate should be able to help operators and end users discover suitable providers, but it should not turn recommendation output into a monetized marketplace.

That means the future recommendation-link line should stay deliberately staged:

### First slices that make sense soon

- add optional provider-catalog fields for signup URLs, disclosure labels, and source ownership
- surface those links in CLI or later browser-based control-center output only when they are available and disclosed
- allow operator-managed secret or env-backed provider-link overrides rather than baking them into normal client-visible config

### Later slices that make sense after that

- optional managed short-link or landing-page wrappers
- richer provider discovery views in a small browser control center
- trust/performance signals derived from historical provider behavior, so recommendations can explain quality and reliability more concretely

The non-negotiable rule is simple: recommendation quality must stay fully independent from provider-link metadata, and signup links may only follow from a recommendation rather than shaping it.

## Assumptions

- OpenAI-compatible HTTP remains the default interoperability surface in the near term
- OpenClaw, n8n, and CLI tools should keep sharing one gateway unless a client truly requires a dedicated adapter
- modality expansion should stay contract-driven instead of adding ad hoc special cases
- context, memory, and optimization remain optional layers around the gateway core
