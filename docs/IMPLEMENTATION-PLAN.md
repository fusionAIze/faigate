# Implementation Plan

## Goal

Turn Gate's existing routing intelligence into the default daily-use behavior
for Claude Code, opencode, openclaw, and similar clients, then expose that
intelligence through a stronger standalone product surface.

## Scope

This document turns the roadmap into the next concrete release lines.

It stays biased toward the biggest product levers:

- Claude-native daily usability
- routing trust and operator explainability
- adaptive behavior under real pressure

It is not a parking lot for every possible feature.

## Principles

- keep `fusionAIze Gate` as the gateway, not a second platform
- prefer one coherent release theme over many mini-features
- do protocol hardening before bigger marketing claims
- do routing explainability before stronger live adaptation
- keep `v2.x` work behind clean product boundaries

## Parity Definitions

### Full Anthropic parity

Protocol parity for Gate's Anthropic-compatible surface.

Working definition:

- `messages` request and response compatibility
- SSE streaming compatibility
- content-block compatibility
- header/version/beta compatibility
- compatible error envelopes and stop reasons
- trustworthy token counting semantics

### Full Claude Code parity

Daily-workflow parity for Claude Code against local Gate.

Working definition:

- iterative coding sessions feel normal
- streaming works
- tool flows work
- aliases and fallback do not constantly disrupt the session
- operator routing behavior stays behind the gateway, not in the client

### Full Claude Desktop parity

Daily-use parity for Claude Desktop against local Gate where endpoint override
is supported.

Working definition:

- stable local endpoint configuration
- session behavior is acceptable for the feature set Claude Desktop actually uses
- no recurring compatibility papercuts that make the setup feel experimental

## Release Sequence

### `v1.14.x` - coding auto modes and Claude daily-use trust

Primary outcome:

- the cheapest capable route becomes the default for coding traffic instead of
  hardwiring Sonnet or Opus too early

Implementation slices:

1. map Claude-native model ids to routing intent instead of direct frontier providers
   - `claude-sonnet-* -> auto`
   - `claude-opus-* -> premium`
   - `claude-haiku-* -> eco`
2. add clear coding routing modes
   - `coding-auto`
   - `coding-fast`
   - `coding-premium`
3. align default client profiles
   - `claude`
   - `opencode`
   - `openclaw`
   - `codex`
4. harden Anthropic streaming parity
   - SSE streaming parity for `/v1/messages`
   - mid-stream failure handling
   - stop-reason correctness
   - stronger `tool_use` / `tool_result` continuity across longer sessions
5. validate against real workflows
   - Claude Code
   - opencode
   - openclaw

Success bar:

- Claude Code can be pointed at local Gate and used for normal iterative coding
  flows with acceptable behavior
- streaming and tool-oriented workflows do not immediately fall off the happy path
- coding clients enter through clear auto modes instead of muddled provider-first
  defaults

Guardrails:

- do not hide premium escalations
- do not bypass the scoring engine with provider aliases unless the operator
  asked for an explicit concrete provider
- keep bridge routing inside the same core, not as a parallel router

### `v1.15.x` - product surface and operator trust

Primary outcome:

- Gate becomes legible as a standalone product, not just a strong core hidden
  behind config files
- the dashboard answers operator jobs in a sane order instead of dumping one
  long admin page

Implementation slices:

1. overview dashboard
   - request-readiness first
   - provider health
   - spend and token trend
   - top alerts
   - priority-next actions
2. providers surface
   - route type
   - lane family
   - quota group
   - billing mode
   - readiness
3. clients surface
   - cost by client
   - latency by client
   - profile recommendations
   - premium-escalation hotspots
4. routes surface
   - chosen lane
   - chosen execution route
   - same-lane fallback vs downgrade
   - why selected / why not selected
5. analytics surface
   - cost by client
   - cost by stack
   - cost by lane family
   - routing posture distribution
   - downgrade and fallback visibility
6. request-log and route drilldowns
   - recent request stream
   - trace-first debugging
   - provider, client, and lane pivots
7. integrations and troubleshooting surface
   - Claude Code
   - opencode
   - openclaw
   - Codex / Cursor / Continue / automation setups
   - common symptom-to-fix views

Design constraints:

- keep the web surface read-heavy and operationally safe first
- do not hide YAML, traces, or helper CLIs behind opaque UI abstractions
- borrow the clarity of LLM AIRouter's docs and page structure, not its
  hosted-router assumptions
- make Gate feel more intentional and polished than a default admin panel

Reference:

- [Dashboard IA](./DASHBOARD-IA.md)

### Immediate operator-trust slices after dashboard v1

These are the next high-signal follow-ups now that the first dashboard surface
exists and exposes the real gaps.

They should be treated as short operator-trust slices, not as a second broad UI
redesign.

#### Cluster A - cost truth and catalog freshness

Observed gap:

- cost data is not yet trustworthy enough to explain spend posture per provider
- several providers still show as untracked in the catalog layer

Challenge:

- provider "price" is not one thing
- direct-provider list pricing, aggregator marketplace pricing, free-tier offers,
  and effective billed usage can diverge
- the product should not claim false precision where only a stale public price
  table exists

Recommendation:

- introduce a versioned provider-metadata source of truth that can live as JSON
  in a repo rather than as a hosted database
- design that metadata source as a shared fusionAIze boundary from day one so
  Gate is only the first consumer, not the only one
- keep that scope explicitly limited to fusionAIze products rather than turning
  it into a generic cross-repo metadata service
- keep cost provenance explicit per field:
  - source price
  - source timestamp
  - freshness status
  - source type (`provider-docs`, `aggregator-offer`, `manual-review`,
    `observed-usage`)
- add a small refresh job outside Gate that updates that metadata on a fixed
  rhythm
- pull that metadata into Gate through a conservative update path tied to normal
  catalog refresh and restart flows

Working shape:

- versioned JSON documents
- statically hostable if desired, but not dependent on a dedicated hosted
  database
- reusable later for `fusionAIze Grid`, `Lens`, `Fabric`, and similar products
- not intended for unrelated repositories outside the fusionAIze product line
- reviewable in Git with clear operator override paths

Immediate slices:

1. catalog schema for price provenance and freshness
2. tracked assumptions for `anthropic-haiku`, `anthropic-sonnet`, and
   `gemini-pro`
3. dashboard surfacing for `tracked`, `stale`, `untracked`, and `source age`
4. post-update metadata refresh hook tied to Gate's normal update cadence

#### Cluster B - route and lane explainability

Observed gap:

- operators can see routes and lanes, but not yet in a way that feels obvious
  at a glance

Challenge:

- a graphic by itself will not fix this if the underlying route explanation is
  still too implicit
- visual route maps should follow clearer route-decision semantics, not replace
  them

Recommendation:

- make route choice legible in layers:
  - requested intent
  - chosen lane
  - chosen execution route
  - same-lane fallback candidates
  - downgrade path if fallback crossed clusters
- then add a light visual route map once the textual explanation is already
  operator-trustworthy

Immediate slices:

1. "why this lane / why this route" drilldown in Routes and Request Log
2. explicit same-lane fallback vs downgrade markers
3. lane-family summary cards in Overview and Routes
4. lightweight visual route map once route trace semantics are stable

#### Cluster C - intelligent command bar and shell parity

Observed gap:

- the command bar filters well enough, but it is not yet intelligent
- the dashboard does not yet move in lockstep with shell capabilities and
  config workflows

Challenge:

- "intelligent" should not become another black box
- if the dashboard can suggest scopes or edits, the same logic must stay
  inspectable and reproducible from CLI and YAML

Recommendation:

- keep the command bar operator-first:
  - saved scopes
  - recommended pivots
  - next useful drilldowns
- build shell and dashboard against the same capability layer rather than
  inventing separate UX-only semantics
- add config actions only through safe preview/diff/apply flows, not direct
  opaque mutation

Immediate slices:

1. shell-backed scope suggestions (`high spend`, `fallback active`,
   `premium drift`, `untracked catalog`)
2. deep links from dashboard panels to equivalent shell or API views
3. dashboard config actions with preview, diff, backup, and explicit apply
4. parity review so dashboard filters, shell helpers, and YAML names stay
   aligned

#### Recommended near-term order

1. cost truth and tracked-catalog freshness
2. route and lane explainability
3. command bar intelligence and shell/config parity

This order keeps the next product gains grounded in trust:

- first make the cost and catalog story believable
- then make route choice more legible
- then add smarter operator controls on top of that clearer model

### `v1.16.x` - adaptive orchestration trust

Primary outcome:

- richer route decisions without turning Gate into a black box

Implementation slices:

1. benchmark and cost cluster refinement
2. live pressure adaptation under quota, latency, and failure
3. stronger operator explainability per routing decision
4. same-lane-first reactions before weaker-cluster degrade
5. richer traces that show attempted route order and downgrade reasons

Success bar:

- operators can look at a route decision and understand it without reading
  source code
- route switching under pressure is visible, understandable, and mostly
  unsurprising to operators

## Concrete Next Actions

### Immediate

1. finish the `v1.14.x` validation matrix
2. close remaining Claude-native daily-use gaps under real workflows
3. keep product-surface work operator-first and trace-friendly

### `v1.14.x` validation matrix

Minimum:

- `POST /v1/messages` non-streaming
- `POST /v1/messages` streaming
- `tool_use` / `tool_result`
- `count_tokens`
- version/beta header handling
- one real Claude Code local workflow

Stretch:

- Claude Desktop local override flow
- route fallback under Anthropic quota pressure

### Claude parity matrix

Use this matrix when deciding whether a release truly moved parity forward:

| Capability | Anthropic parity | Claude Code parity | Claude Desktop parity |
| --- | --- | --- | --- |
| Non-streaming `messages` | Required | Required | Required |
| SSE streaming | Required | Required | Likely required |
| `tool_use` / `tool_result` | Required | Required | Maybe, depending on product flow |
| Header/version/beta tolerance | Required | Required | Required |
| Stable model aliasing | Helpful | Required | Required |
| Session continuity under fallback | Helpful | Required | Required |
| Exact token counting | Strongly preferred | Helpful | Helpful |
| Real client workflow validation | Not sufficient alone | Required | Required |

## Deferred Lines

### Exact provider-side token counting

Recommendation:

- defer until after `v1.14.x`
- implement first for providers that expose reliable count endpoints or
  deterministic usage feedback
- keep the current bridge estimate until a route-specific exact path exists

### Virtual keys and per-key budgets

Recommendation:

- likely next after the `v1.16.x` trust line if operator-scale controls become
  the top demand

### OTEL trace-context forwarding

Recommendation:

- can move earlier than other `v2.x` items
- good candidate for a narrower cross-cutting observability release if demand
  is high

## Open Questions

- which Claude Code workflows are still meaningfully blocked after streaming lands?
- which bridge gaps are protocol gaps versus route-selection gaps?
- which exact providers should support exact token counting first?
- do operators want OTEL before virtual keys, or vice versa?

## Anti-Goals

- no second gateway runtime for Anthropic traffic
- no opaque routing magic that cannot be explained later
- no multi-instance infrastructure inside Gate just to claim clustering
- no semantic-cache detour before the simpler operator wins land
