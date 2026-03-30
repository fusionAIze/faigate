# fusionAIze Gate Dashboard IA

## Why this exists

Gate already has more runtime substance than the current dashboard surface
 communicates.

We can already answer many operator questions through:

- `/health`
- `/api/providers`
- `/api/stats`
- `/api/traces`
- `/api/recent`
- provider catalog and refresh guidance
- lane family and request-readiness metadata

The gap is no longer "do we have data?".
The gap is "do we present the right information in the right order for the
 operator's real jobs?".

This document turns that into a product-surface plan.

## What to borrow from LLM AIRouter

The useful parts are not the hosted funnel or the copy.
The useful parts are the clear information architecture and the way the docs
 and dashboard map to operator jobs.

Worth adapting:

- a clearer top-level split between overview, providers, analytics, stacks,
  request history, and setup
- docs that explain one concept per page instead of burying everything in one
  long reference
- explicit quickstart, CLI-tools, troubleshooting, cache, circuit-breaker, and
  cost-management surfaces
- a product surface that feels like a coherent tool, not a pile of local
  endpoints

Not worth copying directly:

- the hosted-router onboarding shape
- opaque "stack" abstractions that hide the actual route and YAML reality
- claims about secret storage or hosted key management that do not match Gate's
  local-first design

## What Gate should do differently

Gate should not become "LLM AIRouter, but local".

Gate's product advantage is different:

- local-first
- operator-owned config
- agent-native
- direct, aggregator, and local-worker routes in one scoring core
- canonical lanes instead of provider-string roulette
- explainable routing, not black-box stack magic

That means the dashboard should optimize for these questions:

1. Is my gateway safe and request-ready right now?
2. Which clients are burning money or taking the slow path?
3. Which lane and route did Gate choose, and why?
4. Which providers, aggregators, or local workers are unhealthy, stale, or
   quota-coupled?
5. What should I change next?

## Design principles

### 1. Jobs first, metrics second

Each page should answer one operator job clearly.

The operator should not need to mentally reconstruct:

- where health lives
- where cost lives
- where route explainability lives
- where setup help lives

### 2. Confidence before detail

The first screen should answer:

- service up?
- request-ready?
- fallback pressure?
- premium spend?
- top issue?

The second step can show tables.

### 3. Explainability by default

If Gate used an expensive route, downgraded a lane, skipped a provider, or
 protected a premium quota, the UI should say so plainly.

### 4. Progressive disclosure

Overview should stay compact.
Provider, route, and request detail pages can go deep.

### 5. Read-only first, action-linked second

The web surface should stay operationally safe.
In the near term it should link clearly to helper CLIs and config-edit flows
 rather than pretending to be a full control plane.

### 6. Distinctive but disciplined design

The dashboard should feel intentionally designed, not like a default admin
 table.

That means:

- stronger visual hierarchy
- clearer section identity
- better grouping
- more purposeful typography and color
- fewer undifferentiated tables

It does not mean turning Gate into a heavy frontend app.

## Recommended dashboard areas

## 1. Overview

Primary operator job:

- "Tell me if Gate is healthy, trustworthy, and worth touching right now."

Should show:

- request-ready summary
- healthy vs unhealthy routes
- premium spend and 24h spend
- fallback share
- top alert
- top client
- top lane family
- "priority next" block

Why this matters:

- current cards already expose many of these signals
- they are just not grouped around one first-run confidence story yet

## 2. Providers

Primary operator job:

- "Which upstreams exist, which ones are really usable, and which ones are the
  weak links?"

Should show:

- provider identity and route type
- canonical lane and lane family
- request-readiness
- billing mode
- quota group / quota isolation
- health and runtime penalties
- freshness status
- route-add recommendation when a family is fragile

Why this matters:

- this is where Gate differentiates from simple proxy routers
- route-aware aggregator handling has to be visible here, not hidden in traces

## 3. Clients

Primary operator job:

- "Which tools are using Gate, and which of them need cheaper or safer
  defaults?"

Should show:

- client profile
- client tag
- request / token / cost totals
- failure rate
- average latency
- recommended scenario or routing mode
- top expensive / slow / failure-heavy clients

Why this matters:

- Gate is not only provider-native, it is client-native
- Claude Code, opencode, openclaw, Codex, and automation clients should be
  legible as distinct traffic shapes

## 4. Routes

Primary operator job:

- "Why did Gate choose this path instead of another one?"

Should show:

- chosen canonical lane
- chosen execution route
- selection path
- same-lane fallback vs cluster downgrade
- route penalty / cooldown / recovery state
- why-not-selected summaries for important skipped candidates

Why this matters:

- this is the bridge between "smart router" and "trustworthy operator tool"

## 5. Analytics

Primary operator job:

- "Where is my money going, and how is traffic shifting over time?"

Should show:

- spend by client
- spend by lane family
- spend by provider / route type
- token trends
- fallback trend
- premium escalation share
- cache hit share
- projected monthly spend

Why this matters:

- the current raw stats are strong enough to build this now
- the UI should make cost-management a first-class narrative, not a derived
  exercise

## 6. Request Log

Primary operator job:

- "What just happened?"

Should show:

- recent requests
- route traces
- selected provider
- model / lane
- layer and rule
- success / failure
- latency
- trace id

Why this matters:

- request history is the fastest debugging entry point
- it should be easy to pivot from recent request -> trace -> provider detail

## 7. Catalog

Primary operator job:

- "Are my assumptions about providers still fresh enough to trust?"

Should show:

- tracked sources
- due refreshes
- stale benchmark assumptions
- pricing drift alerts
- provider discovery guidance
- explicit next review action

Why this matters:

- Gate's provider-catalog and freshness model are already stronger than most
  router surfaces
- this should be productized instead of buried

## 8. Integrations

Primary operator job:

- "How do I wire my actual tools into Gate?"

Should show:

- Claude Code
- opencode
- openclaw
- Codex CLI
- Cline / Continue / Cursor-style OpenAI-compatible paths
- n8n and scripts

Should include:

- copy/paste env vars
- recommended model ids or routing modes
- note on when to use `auto` vs `coding-auto` vs `premium`

Why this matters:

- LLM AIRouter is right that tool setup deserves first-class visibility
- Gate already supports more surfaces than "just one CLI", so this should be a
  stronger differentiator for us

## 9. Troubleshooting

Primary operator job:

- "Something is wrong. What is the shortest path to the fix?"

Should show:

- unauthorized / missing key
- provider unhealthy / request-not-ready
- quota-domain confusion
- slow responses
- model not found
- bridge-compatibility mismatch
- local-worker reachability

Why this matters:

- user-centered design is not only about happy-path polish
- it is also about fast recovery when things break

## Suggested navigation model

Recommended top-level web navigation:

- Overview
- Providers
- Clients
- Routes
- Analytics
- Request Log
- Catalog
- Integrations
- Troubleshooting

Recommended shell helper mapping:

- `faigate-dashboard --overview`
- `faigate-dashboard --providers`
- `faigate-dashboard --clients`
- `faigate-dashboard --activity`
- `faigate-dashboard --alerts`
- future:
  - `--routes`
  - `--catalog`
  - `--integrations`
  - `--troubleshooting`

## Near-term implementation shape

### `v1.15.x` first slice

Ship the information architecture before chasing fancy visuals.

Minimum meaningful surface:

- overview
- providers
- clients
- routes
- analytics
- request log

These can still be read-only and no-build.

### `v1.15.x` second slice

Add stronger operator guidance:

- priority-next cards
- clearer expensive-client and premium-escalation flags
- quota-domain and billing-mode visibility
- route drilldowns with same-lane vs downgraded explanation

### `v1.15.x` third slice

Add setup and docs integration:

- integrations page
- troubleshooting page
- quick links into helper CLIs and relevant docs

## Design direction

The current dashboard should evolve from "dense local admin page" to "operator
 cockpit".

Recommended visual moves:

- stronger left-rail or top-nav sectioning
- overview cards grouped by confidence, spend, traffic, and actions
- more contrast between healthy, degraded, stale, and expensive states
- more deliberate typography pairing between headings and tabular detail
- fewer giant all-purpose tables
- compact detail panels that answer "why this matters" inline

The target feeling:

- serious
- technical
- calm under pressure
- more distinctive than default admin templates
- still lightweight enough to ship as part of Gate

## Licensing boundary

### Tier A — Apache 2.0

Should include:

- local read-only dashboard
- provider, client, route, and request-log views
- local analytics from Gate's own metrics
- integrations and troubleshooting pages
- catalog freshness and route-readiness visibility

These features strengthen adoption and product clarity.
They should stay in the open Gate surface.

### Tier B — source-available or premium packs

Reasonable later candidates:

- saved custom views and operator alerts
- richer cost analytics overlays
- policy simulation and route what-if tools
- budget packs and team-aware dashboards

### Tier C — commercial control plane

Reasonable later candidates:

- shared multi-instance dashboards
- org-wide governance and audit
- Grid-backed fleet visibility
- RBAC and centralized rollout controls

## Success criteria

The dashboard work is successful when a new operator can answer these questions
 within a few minutes:

1. Which client is costing me the most?
2. Which provider or route is currently the weakest link?
3. Are expensive lanes being used because they are needed, or because my
   defaults are bad?
4. Can I explain the last major routing decision?
5. What is the next safest action to improve cost, reliability, or setup?
