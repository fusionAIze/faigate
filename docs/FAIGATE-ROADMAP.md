# fusionAIze Gate Roadmap

## Status

`v1.14.1` is shipped.

Gate is no longer just a routing core with helper scripts around it. The
current product baseline is now clear:

- one local gateway runtime
- one OpenAI-compatible surface
- one optional Anthropic-compatible bridge
- direct providers, aggregators, and local workers under one routing core
- an operator shell made up of dashboard, doctor, catalog, probe, and guided setup

The roadmap should now stay disciplined. The next release lines should deepen
operator trust, routing explainability, and daily-use client confidence instead
of expanding sideways into a second platform.

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

## Parity Targets

The roadmap keeps three parity goals separate.

### Full Anthropic parity

Working definition:

- `POST /v1/messages` request and response compatibility
- SSE streaming parity
- content-block compatibility
- header, version, and beta compatibility
- compatible error envelopes and stop reasons
- trustworthy token-count semantics

### Full Claude Code parity

Working definition:

- daily coding sessions feel normal against local Gate
- streaming and tool flows work
- aliases and fallback do not constantly disrupt the session
- routing remains inside Gate instead of being pushed into client config

### Full Claude Desktop parity

Working definition:

- stable local endpoint configuration where override is supported
- acceptable session behavior for the desktop feature set that actually matters
- no recurring compatibility papercuts that keep the setup feeling experimental

## Release Sequence

### `v1.15.x` - operator trust and metadata truth

Primary outcome:

- Gate becomes more trustworthy as an operator product
- dashboard, shell, and config tell the same story
- cost and catalog signals become reviewable instead of hand-wavy

Implementation slices:

1. cost truth and catalog freshness
   - explicit tracked / stale / untracked state
   - stronger provider pricing provenance
   - refresh visibility in dashboard and shell
2. route and lane explainability
   - why this lane
   - why this route
   - same-lane fallback vs downgrade
   - clearer lane-family summaries
3. command bar intelligence and shell parity
   - shell-backed scope suggestions
   - parity between dashboard pivots and CLI/YAML terms
   - safe preview/diff/apply config actions
4. shared metadata-source foundation
   - fusionAIze-internal JSON metadata boundary
   - reusable across Gate and future fusionAIze products only

Success bar:

- operators can trust the dashboard without treating it as a decorative shell
- cost and freshness signals are explainable
- route choice is easier to reason about from UI, CLI, and config

### `v1.16.x` - adaptive routing trust

Primary outcome:

- richer live routing behavior without turning Gate into a black box

Implementation slices:

1. route pressure and cooldown visibility
2. same-lane-first adaptation before weaker downgrade paths
3. clearer route maps and trace-level route narratives
4. more explicit premium drift, fallback pressure, and quota coupling signals

Success bar:

- adaptation under pressure is visible and mostly unsurprising
- operators can explain route changes after the fact without reading source code

### Later `v1.x` line - Claude Desktop parity if demand justifies it

This should be validated by real operator demand, not assumed.

If the client demand is real, the next parity-focused slices should cover:

1. supported endpoint override flows
2. desktop-specific compatibility hardening
3. clearer troubleshooting and real local workflow validation

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

## Immediate Near-Term Order

1. cost truth and catalog freshness
2. route and lane explainability
3. command bar intelligence and shell/config parity

This order matters.

First make the truth source believable. Then make route choice legible. Then
add smarter operator controls on top of a clearer model.

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
