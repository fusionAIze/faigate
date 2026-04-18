# fusionAIze Gate Roadmap

## Status

`v2.0.0` is shipped.

Gate is no longer just a routing core with helper scripts around it. The
current product baseline is now clear:

- one local gateway runtime
- one OpenAI-compatible surface
- one optional Anthropic-compatible bridge (SSE streaming, tool continuity, Claude Code aliases)
- direct providers, aggregators, and local workers under one routing core
- an operator shell made up of dashboard, doctor, catalog, probe, and guided setup
- package renewal alerts and cost projection wizard

### Recent Achievements (v1.15.0 - v2.0.0)
- **Anthropic bridge production-ready**: SSE streaming adapter, tool result continuity, Claude Code model ID mapping
- **Dashboard enhancements**: Package renewal alerts, cost trends CLI, uPlot charts integration
- **Operator tools**: Branch management guidelines, model shortcut alias conflict detection
- **Provider catalog live**: Local route visibility overlays, operator alert summaries
- **Claude Desktop parity finalization**: Desktop endpoint override flows, bridge hardening, workflow validation (v1.19.x)
- **External metadata integration**: Git-based metadata sync, model/provider/price mapping, cost truth visualization (v1.20.x)
- **Route explainability & operator trust**: Lane family decision factors, selection path categorization, route decision drilldowns (v1.21.x)
- **Shell parity & complete provider coverage**: CLI deep‑links, config workflows, local worker discovery, all LLM AI Router custom endpoints, KiloCode model‑level lanes (v2.0.0)

The roadmap should now stay disciplined. The next release lines should finalize
Claude Desktop parity, then deepen operator trust through metadata truth and
routing explainability.

## Architecture Readout

The refreshed `Understand-Anything` pass confirms four high-value themes:

1. the gateway core is still healthy and understandable
2. the operator surface is now a first-class product surface
3. the Anthropic bridge is part of the real runtime contract
4. the next trust gap is metadata truth, not raw routing breadth

The practical implication is simple:

- Gate does not need a bigger feature list first
- Gate needs clearer truth about cost, freshness, route choice, and operator controls

## Product Direction

Gate remains gateway-first.

That means:

- request routing stays the product center
- provider contracts stay explicit
- operator visibility stays close to the runtime
- shell, dashboard, and config must describe the same system

It does **not** mean:

- turning Gate into a generic agent platform
- hiding routing logic behind opaque UI magic
- introducing hosted-only assumptions into a local-first product

## Parity Status & Targets

### Current Parity Status (v1.18.0)

| Capability | Anthropic Bridge | Claude Code | Claude Desktop |
|------------|------------------|-------------|----------------|
| `POST /v1/messages` non-streaming | ✅ Production-ready | ✅ Production-ready | ✅ Supported |
| SSE streaming parity | ✅ Implemented | ✅ Working | ⚠️ Needs validation |
| `tool_use` / `tool_result` continuity | ✅ Implemented | ✅ Working | ⚠️ Needs validation |
| Claude model ID aliasing | ✅ Built-in mappings | ✅ Working | ⚠️ Needs validation |
| Header/version/beta compatibility | ✅ Basic support | ✅ Working | ⚠️ Needs validation |
| Exact token counting | ⚠️ Char-based estimates | ⚠️ Estimates okay | ⚠️ Estimates okay |
| Desktop endpoint override flows | N/A | N/A | ⚠️ Needs implementation |
| Session continuity under fallback | ✅ Working | ✅ Working | ⚠️ Needs validation |

### Full Anthropic parity (Target)

Working definition:

- `POST /v1/messages` request and response compatibility
- SSE streaming parity (✅ achieved)
- content-block compatibility
- header, version, and beta compatibility
- compatible error envelopes and stop reasons
- **trustworthy token-count semantics** (remaining gap)

### Full Claude Code parity (✅ Mostly achieved)

Working definition:

- daily coding sessions feel normal against local Gate (✅)
- streaming and tool flows work (✅)
- aliases and fallback do not constantly disrupt the session (✅)
- routing remains inside Gate instead of being pushed into client config (✅)

### Full Claude Desktop parity (Next priority)

Working definition:

- stable local endpoint configuration where override is supported
- acceptable session behavior for the desktop feature set that actually matters
- no recurring compatibility papercuts that keep the setup feeling experimental

## Release Sequence (v1.19.x - v1.21.x)

### `v1.19.x` - Claude Desktop Parity Finalization

**Primary outcome:**
- Claude Desktop becomes a first-class client with stable local endpoint configuration
- Desktop-specific workflows work reliably without recurring compatibility issues
- Bridge hardening completes the Anthropic parity line

**Implementation slices:**
1. **Desktop endpoint override flows**
   - Stable local endpoint configuration support
   - Clear troubleshooting guides for desktop setup
   - Validation against real Claude Desktop workflows
2. **Bridge hardening for desktop use**
   - Enhanced header/version/beta compatibility
   - Session continuity validation under desktop usage patterns
   - Error mapping improvements for desktop-specific error cases
3. **Desktop workflow validation**
   - Real workflow testing with Claude Desktop
   - Common papercut identification and fixes
   - Performance and stability validation

**Success bar:**
- Operators can configure Claude Desktop to use local Gate without recurring issues
- Desktop sessions feel stable and production-ready
- Bridge parity gaps are documented and addressed

### `v1.20.x` - External Metadata Integration (#186)

**Primary outcome:**
- Gate integrates with external metadata repository for provider/model/pricing truth
- Cost-aware routing uses real pricing data from trusted sources
- Operators gain visibility into pricing provenance and freshness

**Implementation slices:**
1. **Git-based metadata sync** (Phase 2a from #186)
   - External metadata repository integration
   - Background update daemon (2-3 hour intervals)
   - Offline fallback and cache management
2. **Model/provider/price mapping**
   - Canonical model definitions with multi-provider offerings
   - Pricing provenance tracking (source, timestamp, freshness)
   - Router integration for price-aware routing decisions
3. **Dashboard integration**
   - Cost truth visualization with source indicators
   - Promotion tracking and expiration alerts
   - Provider mix analytics and cost savings reporting

**Success bar:**
- Gate uses external metadata for accurate pricing and model mappings
- Operators can trust cost reporting with clear provenance
- Routing decisions consider real prices and promotions

### `v1.21.x` - Route Explainability & Operator Trust

**Primary outcome:**
- Route decisions become transparent and explainable to operators
- Dashboard provides clear "why this route/why this lane" explanations
- Operators gain confidence in Gate's routing intelligence

**Implementation slices:**
1. **Route decision explainability**
   - "Why this lane / why this route" drilldowns in dashboard
   - Same-lane fallback vs downgrade visual indicators
   - Lane-family summary cards with decision factors
2. **Operator trust tooling**
   - Route trace narratives with decision context
   - Pressure and cooldown visibility in real-time
   - Premium drift and fallback pressure indicators
3. **Shell parity and intelligence**
   - Shell-backed scope suggestions matching dashboard
   - Deep links between dashboard panels and CLI views
   - Safe config preview/diff/apply workflows

**Success bar:**
- Operators can understand and explain route decisions without reading source code
- Dashboard and shell tell the same story about routing behavior
- Route adaptation under pressure is visible and understandable

## Shared Metadata Repository Direction

The provider metadata line should be designed from the start as a reusable
fusionAIze capability, not a Gate-only sidecar.

Scope guardrail:

- this shared metadata line is for fusionAIze products only
- it is not intended to become a generic shared metadata service for unrelated repositories

### Working shape

- versioned JSON documents, not a mandatory hosted database
- static-hostable and cacheable
- reviewable in Git
- publishable on a fixed cadence by automation
- consumable locally without requiring fusionAIze-operated hosting

### What it should eventually serve

- Gate
- Grid
- Lens
- Fabric
- future fusionAIze operator products that need provider, model, offer, or pricing truth

### What belongs in that source

- provider identity and aliases
- model and offer identifiers
- modality and capability metadata
- pricing metadata
- provenance metadata
- freshness metadata
- operator-reviewed overrides

### Provenance requirements

Every meaningful cost or offer field should be able to answer:

- where did this value come from?
- when was it last refreshed?
- what kind of source is it?
- is it tracked, stale, or untracked?

Example source types:

- `provider-docs`
- `aggregator-offer`
- `manual-review`
- `observed-usage`

### Delivery model

Recommended first delivery model:

1. dedicated versioned metadata repo
2. JSON snapshots published from that repo
3. scheduled refresh job outside Gate
4. Gate-side refresh/update mechanism tied to restart and normal update flow

This keeps the truth source inspectable and shared, while avoiding a premature
hosted control-plane dependency.

## Completed Release Lines (v1.19.x - v1.21.x)

✅ **v1.19.x - Claude Desktop Parity Finalization** (Completed)
   - Desktop endpoint override flows
   - Bridge hardening for desktop usage
   - Real workflow validation

✅ **v1.20.x - External Metadata Integration** (Completed)
   - Git-based metadata sync implementation
   - Model/provider/price mapping foundation
   - Dashboard cost truth visualization

✅ **v1.21.x - Route Explainability & Operator Trust** (Completed)
   - Route decision drilldowns and explanations
   - Operator trust tooling and visibility
   - Lane family decision factors and selection path categorization
   - _(Shell parity and intelligent suggestions deferred to v2.0.0)_

This order proved effective: first completing client parity with Claude Desktop,
then building metadata truth for trustworthy cost routing, and finally adding
explainability so operators understand and trust routing decisions.

## v2.0.0 Planning

**Target: Major release with shell parity, local worker support, complete provider coverage, and enhanced client profiles**

### Core Themes
1. **Shell parity and intelligence** ✓ _(implemented)_
   - Shell-backed scope suggestions matching dashboard ✓
   - Deep links between dashboard panels and CLI views ✓
   - Safe config preview/diff/apply workflows ✓
   - Config workflow suggestions and deep‑link generation ✓

2. **Local worker support** ✓ _(implemented)_
   - First‑class local model worker integration ✓ (cost‑tier mapping, auto‑discovery CLI)
   - Worker health monitoring and auto‑recovery ✓ (basic health probes)
   - Cost‑aware routing between local and cloud providers ✓ (local cost tier scoring)
   - Example configurations for Ollama, vLLM, LM Studio, LiteLLM ✓

3. **Complete provider coverage** ✓ _(implemented)_
   - All LLM AI Router custom endpoints represented in provider catalog ✓
   - Generic provider support (OpenAI, Anthropic, Google) with config examples ✓
   - Full provider families (Mistral, Groq, xAI, HuggingFace, Cerebras, etc.) ✓
   - KiloCode model‑level access with individual catalog entries ✓
   - Consistent `recommended_model` values across all providers ✓

4. **Enhanced client profiles** ⚠️ _(deferred to v2.1.0)_
   - Advanced client policy management
   - Per‑client routing rules and cost controls
   - Client‑specific observability and reporting

5. **Observability improvements** ⚠️ _(deferred to v2.1.0)_
   - Advanced metrics and alerting
   - Performance tracing across request chains
   - Automated anomaly detection

### Considerations
- v2.0.0 may include breaking changes for cleaner APIs and configuration
- Migration paths will be documented for existing deployments
- Focus remains on gateway‑first architecture and operator trust
- **Provider coverage now matches LLM AI Router’s custom endpoints**; each KiloCode model can be accessed individually via API key
- **Local worker examples** added to config.yaml; generic providers available as commented templates

 *Detailed planning and issue creation pending review of current priorities and community feedback.*

## v2.1.0 Planning

**Target: Managed provider OAuth wrapper, enhanced local worker integration, and advanced client profiles**

### Core Themes
1. **Managed provider OAuth wrapper** ✓ _(implemented)_
   - OAuth‑based authentication for managed providers (Gemini, Antigravity, etc.) ✓
   - Interactive device‑code login flows (Google, Qwen, Antigravity) ✓
   - Token store and generic OAuth backend ✓
   - Antigravity provider in registry, catalog, and lane registry (ag/ model family) ✓
   - claude_code_oauth() reading token from local claude CLI settings ✓

2. **Local worker completion** ✓ _(implemented)_
   - Grid integration: reads `~/.faigrid/config.json` + legacy state file ✓
   - GPU/VRAM metrics via Ollama `/api/ps` and vLLM `/metrics` ✓
   - Dynamic model enumeration from `/v1/models` endpoints ✓
   - `dynamic_models` field in DiscoveredWorker; surfaced in generate_provider_config ✓
   - _(Lifecycle management hooks deferred — requires Grid daemon integration)_

3. **Enhanced client profiles** ✓ _(implemented)_
   - `cost_limit_usd_day` and `cost_limit_usd_month` per profile ✓
   - Config validation with type checking ✓
   - HTTP 429 enforcement before routing when budget is reached ✓
   - Provider allow/deny lists already live in policy layer ✓
   - _(Advanced policy management UI deferred)_

4. **Observability suite** ✓ _(implemented)_
   - `MetricsStore.get_anomalies()`: error rate, latency, cost, and traffic spike detection ✓
   - `GET /api/alerts` endpoint with configurable lookback and baseline windows ✓
   - GPU utilization surfaced from local worker probes ✓
   - _(External alerting integrations and Prometheus export deferred)_

### Considerations
- Maintain backward compatibility with v2.0.0 configurations
- Focus on operator trust through enhanced visibility
- Keep gateway‑first architecture principle
- OAuth wrapper should be optional; API‑key providers remain the default
- Interactive login flows must be clearly separated from automated routing core

## v2.3.0 Planning

**Target: Quota visibility parity with CodexBar, a desktop menubar companion, and generic multi-provider balance fetchers**

Motivation: the v2.2.x release line landed real package polling (DeepSeek
`/user/balance`, Kilo tRPC batch) and an external catalog with nine real
packages, but the quotas dashboard still shows placeholder numbers for
OpenRouter, OpenAI, Anthropic subscriptions, Codex, and Blackbox. The inspiration
is [steipete/CodexBar](https://github.com/steipete/CodexBar) — a small macOS
menubar app that already aggregates subscription and credit state for several
providers. The next larger UI batch should bring Gate's quota surface up to that
level and give operators a native OS affordance.

### Core Themes

1. **CodexBar-style quota dashboard widget** _(informed by items 3 from the
   v2.2.3 triage)_
   - Re-skin `/dashboard/quotas` so every package surfaces the same visual shape
     regardless of `package_type` (credits / rolling_window / daily)
   - Per-package card: provider logo, remaining amount, progress bar, confidence
     badge, source provenance (api_poll / header_capture / local_count /
     manual), last-refreshed timestamp, and renewal/expiry countdown
   - Group cards by client-facing routing lane (coding-auto / coding-premium /
     eco / free) so operators see "which lane will start throttling next"
   - Retain the CodexBar pattern of collapsing providers with no introspection
     path into a discreet "manual" section rather than hiding them

2. **Faigate menubar companion** _(item 4)_
   - Native macOS menubar app (SwiftUI, Sparkle auto-update) that pulls from the
     local `GET /api/quotas` endpoint every 30–60 s
   - One compact status line per provider: glyph + remaining % + next-reset
     hint; colour-coded via the shared `QuotaStatus.alert` levels
   - Click-through actions: open dashboard, run `faigate doctor`, copy the
     current `OPENAI_BASE_URL`, toggle the fast-lane poll interval
   - Ship as an optional Homebrew cask (`faigate-menubar`) so the core CLI/LLM
     gateway stays headless

3. **Generic multi-provider balance fetchers** _(item 5 — the engine behind 1+2)_
   - Extend `quota_poller.py` with the same provider coverage CodexBar has,
     starting with the six that still show placeholder data today:
     - OpenRouter `/auth/key` (JSON balance + usage)
     - OpenAI billing (best-effort: `x-ratelimit-remaining-tokens` header +
       dashboard-scrape fallback, documented as medium-confidence)
     - Anthropic subscription state (scrape-based like CodexBar, gated behind
       explicit opt-in because there is no official API)
     - GitHub Copilot entitlement + Amp/Cursor subscription probes
     - Gemini free-tier token-count via `aistudio` metadata when user opts in
     - Blackbox free-tier via session cookie
   - Split each fetcher into a small Strategy class so third-party contributors
     can add new providers without touching the poller core
   - Surface each provider's status on the dashboard and in the menubar widget
     through the existing `QuotaPackage` schema — no second data model

### Sequencing

- **v2.3.0-alpha1**: refactor `quota_poller` into a Strategy registry, port the
  existing DeepSeek + Kilo fetchers onto it, land the OpenRouter
  `/auth/key` fetcher as the first new provider (lowest-risk, official API).
- **v2.3.0-beta1**: ship the redesigned `/dashboard/quotas` widget backed by
  the new Strategy registry, including source/confidence badges.
- **v2.3.0**: cut the menubar companion into a separate GitHub repo / Homebrew
  cask, documented as an optional add-on; the core Gate release only gains the
  `/api/quotas` contract guarantees the menubar relies on.
- **v2.3.x patch line**: add one provider fetcher per patch release (OpenAI,
  Anthropic subscription, Copilot, Amp, Cursor, Gemini, Blackbox) so each ships
  with its own live-verification note in the CHANGELOG.

### Success bar

- Every package in the external catalog has a `source != "manual"` path, or an
  explicit documented reason why it has to stay manual.
- Operators can glance at the menubar and predict which lane will throttle next
  without opening the dashboard.
- Contributors can add a new provider fetcher by implementing one Strategy
  class and one JSON catalog entry.

### Scope boundaries

- The menubar is an _optional_ companion — no feature of Gate's routing core
  may depend on it being installed.
- CodexBar-style subscription scrapes must stay behind an explicit opt-in flag;
  headless defaults remain the three official levels (`api_poll`,
  `header_capture`, `local_count`).
- No new hosted metadata or control-plane requirement. The Strategy registry
  reads from the same `fusionaize-metadata/packages/catalog.v1.json` that
  v2.2.x already consumes.

## Anti-Goals

- no second routing runtime just for Anthropic traffic
- no opaque “smart routing” layer that cannot explain itself
- no hosted-only metadata dependency for basic local use
- no control-plane sprawl before operator trust is earned
- no product claims that outrun live workflow validation

## Review Rule

After every 4 or 5 merged PRs:

- review unit and integration coverage
- review real operator workflows
- refresh docs across README, roadmap, architecture, integrations, onboarding, and troubleshooting
- check whether current release priorities still match the product direction
