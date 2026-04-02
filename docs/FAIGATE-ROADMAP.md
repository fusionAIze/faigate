# fusionAIze Gate Roadmap

## Status

`v1.21.0` is shipped.

Gate is no longer just a routing core with helper scripts around it. The
current product baseline is now clear:

- one local gateway runtime
- one OpenAI-compatible surface
- one optional Anthropic-compatible bridge (SSE streaming, tool continuity, Claude Code aliases)
- direct providers, aggregators, and local workers under one routing core
- an operator shell made up of dashboard, doctor, catalog, probe, and guided setup
- package renewal alerts and cost projection wizard

### Recent Achievements (v1.15.0 - v1.21.0)
- **Anthropic bridge production-ready**: SSE streaming adapter, tool result continuity, Claude Code model ID mapping
- **Dashboard enhancements**: Package renewal alerts, cost trends CLI, uPlot charts integration
- **Operator tools**: Branch management guidelines, model shortcut alias conflict detection
- **Provider catalog live**: Local route visibility overlays, operator alert summaries
- **Claude Desktop parity finalization**: Desktop endpoint override flows, bridge hardening, workflow validation (v1.19.x)
- **External metadata integration**: Git-based metadata sync, model/provider/price mapping, cost truth visualization (v1.20.x)
- **Route explainability & operator trust**: Lane family decision factors, selection path categorization, route decision drilldowns (v1.21.x)

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

**Target: Major release with shell parity, local worker support, and enhanced client profiles**

### Core Themes
1. **Shell parity and intelligence**
   - Shell-backed scope suggestions matching dashboard
   - Deep links between dashboard panels and CLI views
   - Safe config preview/diff/apply workflows

2. **Local worker support**
   - First-class local model worker integration
   - Worker health monitoring and auto-recovery
   - Cost-aware routing between local and cloud providers

3. **Enhanced client profiles**
   - Advanced client policy management
   - Per-client routing rules and cost controls
   - Client-specific observability and reporting

4. **Observability improvements**
   - Advanced metrics and alerting
   - Performance tracing across request chains
   - Automated anomaly detection

### Considerations
- v2.0.0 may include breaking changes for cleaner APIs and configuration
- Migration paths will be documented for existing deployments
- Focus remains on gateway-first architecture and operator trust

*Detailed planning and issue creation pending review of current priorities and community feedback.*

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
