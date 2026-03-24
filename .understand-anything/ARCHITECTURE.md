# fusionAIze Gate - Architecture Analysis

## Project Overview

**fusionAIze Gate** is a local OpenAI-compatible routing gateway that intelligently routes requests across multiple LLM providers using a sophisticated 6-layer cascade decision engine. It gives OpenClaw, n8n, CLI tools, and custom applications one unified local endpoint while maintaining operator control over routing, fallback behavior, and provider selection logic.

**Key Metrics:**
- 17 Python modules across 17,558 lines of code
- 31 nodes in knowledge graph (16 files, 15 architectural concepts)
- 40 directed edges representing dependencies and relationships
- 7 architectural layers
- 12-step guided learning tour

---

## Core Architecture

### 1. Layered Routing Engine (6 Layers)

The routing engine in `router.py` implements a cascading decision system that evaluates routing constraints in strict order:

```
Client Request
    ↓
┌─────────────────────────────────────┐
│ Layer 0: Policy Rules               │ (declarative rules from config.yaml)
└─────────────────────────────────────┘
    ↓ (if matched → decision)
┌─────────────────────────────────────┐
│ Layer 1: Static Rules               │ (model name aliases, hardcoded patterns)
└─────────────────────────────────────┘
    ↓ (if matched → decision)
┌─────────────────────────────────────┐
│ Layer 2: Heuristics                 │ (keyword analysis, complexity detection)
└─────────────────────────────────────┘
    ↓ (if matched → decision)
┌─────────────────────────────────────┐
│ Layer 3: Request Hooks              │ (extensible pre-routing logic)
└─────────────────────────────────────┘
    ↓ (if matched → decision)
┌─────────────────────────────────────┐
│ Layer 4: Client Profiles            │ (client-specific overrides)
└─────────────────────────────────────┘
    ↓ (if matched → decision)
┌─────────────────────────────────────┐
│ Layer 5: LLM Classifier             │ (optional ML-based classification)
└─────────────────────────────────────┘
    ↓ (if matched → decision)
┌─────────────────────────────────────┐
│ Fallback: First provider in chain   │ (last resort)
└─────────────────────────────────────┘
```

**Key Properties:**
- **First-Match Semantics:** Each layer can make a routing decision, short-circuiting all downstream layers
- **Declarative First:** Operator-controlled policies take precedence over heuristics
- **Extensible:** Hooks system allows custom logic injection
- **Adaptive:** Provider health and performance metrics influence candidate ranking
- **Fallback Safe:** Guaranteed routing even if all layers fail to match

### 2. Signal Groups & Heuristics

The heuristics layer (Layer 2) analyzes request content using multiple signal groups:

| Signal Group | Purpose | Examples |
|---|---|---|
| `short_message` | Simple factual queries | "What is X?", "How do I...?" |
| `short_complex` | Compact but difficult problems | "Debug this race condition in 50 words" |
| `device_type` | Mobile/tablet detection | Browser user-agent analysis |
| `has_tools` | Function calling capability needed | tool/function definitions in request |
| `opencode_complexity` | Architecture & design patterns | Keywords: architecture, tradeoff, system design, refactor, migration |
| `knowledge_domain` | Specialized domain expertise | database, devops, testing, security, kubernetes, terraform |
| `streaming_preference` | Client wants streaming | x-faigate-stream header |
| `cache_preference` | Cache usage requested | x-faigate-cache header |

**Complexity Keywords (Domain-Specific):**

- **Architecture:** "architecture", "tradeoff", "trade-off", "system design", "design review", "implementation plan"
- **Performance:** "bottleneck", "throughput", "queue", "consistency", "race condition", "deadlock"
- **DevOps:** "kubernetes", "terraform", "ci/cd", "pipeline", "deployment", "infrastructure as code"
- **Testing:** "unit test", "integration test", "test coverage", "mock", "e2e"
- **Security:** "jwt", "oauth", "xss", "sql injection", "csrf", "rbac", "vulnerability"
- **Database:** "schema", "sharding", "query optimization", "replication", "multi-tenant"

### 3. Canonical Model Lanes & Quality Tiers

All models are organized into semantic "lanes" representing capability clusters:

| Cluster | Examples | Tier | Reasoning | Context | Tools |
|---|---|---|---|---|---|
| **elite-reasoning** | Opus 4.6 | premium | high | high | medium |
| **quality-workhorse** | Sonnet 4.6, GPT-4o | high | high | high | medium |
| **balanced-workhorse** | Gemini Pro Low | mid | mid | high | medium |
| **fast-workhorse** | Haiku 4.5, Gemini Flash | mid | mid | mid | medium |
| **budget-general** | Gemini Flash Lite, free models | budget | low | mid | low |

**Quality Tier Scoring:**

```
Quality Tier → Score
- premium      → 10
- high         → 8
- mid          → 5
- budget       → 2
- free         → 1
- variable     → 4
- n/a          → 0
```

**Routing Modes apply multipliers:**

- `eco`: Bias toward budget/fast providers (high multiplier for budget tiers)
- `premium`: Bias toward quality/expensive providers (high multiplier for premium tiers)
- `auto` (balanced): Neutral multipliers
- `free`: Only free providers allowed
- `custom`: User-defined select constraints

### 4. Policy Rules Engine

The first routing layer uses declarative rules with match conditions and select constraints:

**Match Conditions:**
```yaml
routing_policies:
  rules:
    - name: "reasoning-heavy-queries"
      match:
        message_keywords:
          - "architecture"
          - "system design"
          - "refactor"
        client_profile: ["openclaw"]
      select:
        prefer_tiers: ["premium", "high"]
        deny_providers: ["free-provider"]
```

**Supported Conditions:**
- `model_requested`: Exact match on requested model name
- `system_prompt_contains`: Regex pattern in system prompt
- `header_contains`: HTTP header value matching
- `has_tools`: Boolean - tools/function calling present
- `estimated_tokens`: Token threshold matching
- `message_keywords`: Keyword list in message content
- `client_profile`: Named client profile matching
- `fallthrough`: Explicit pass-through to next layer

**Select Constraints:**
- `allow_providers`: Whitelist specific providers
- `deny_providers`: Blacklist specific providers
- `prefer_providers`: Rank these providers higher
- `prefer_tiers`: Prefer specific quality tiers
- `require_capabilities`: Mandate capability support (vision, tools, etc)
- `capability_values`: Constraint specific capability values

### 5. Request Hooks System

Extensible pre-routing logic allowing custom modifications:

```python
@dataclass
class RequestHookResult:
    body_updates: dict[str, Any]           # Modify request (messages, model, tools, temperature, etc)
    profile_override: str | None           # Override client profile
    routing_hints: dict[str, Any]          # Inject routing hints (allow/deny/prefer constraints)
    notes: list[str]                       # Attach metadata
```

**Hook Lifecycle:**
1. Registry (hooks.py) maintains `_REQUEST_HOOKS` dict
2. Configuration specifies which hooks to run and error handling mode
3. Hooks applied in sequence before Layer 3 of routing
4. Results accumulated and merged for downstream routing
5. Error handling modes: "fail" (raises) or "continue" (logs and proceeds)

**Allowed Body Updates:**
- `messages`, `model`, `tools`, `tool_choice`
- `temperature`, `max_tokens`, `stream`
- `response_format`, `metadata`, `user`

### 6. Client Profiles

Named routing personas with preset constraints and header matching:

**Built-in Presets:**

| Profile | Header Match | Default Tiers | Use Case |
|---|---|---|---|
| `openclaw` | x-openclaw-source or x-faigate-client=openclaw | reasoning, default | Heavy analysis & reasoning tasks |
| `n8n` | x-faigate-client=n8n | cheap, default | Workflow automation with cost focus |
| `cli` | x-faigate-client=cli,codex,claude,deepseek | default, reasoning | CLI tools and code agents |

Profiles can override or modify routing via:
- Preset select constraints (prefer_tiers, allow_providers, etc)
- Header-based activation
- Profile override via request hooks

### 7. Provider Health & Adaptation

`adaptation.py` tracks runtime provider health with issue classification:

**Issue Types & Cooldown Windows:**

| Issue Type | Cooldown | Action |
|---|---|---|
| `quota-exhausted` | 1800s (30 min) | Hard disable - provider hit billing limit |
| `auth-invalid` | 1800s (30 min) | Hard disable - API key/auth failure |
| `rate-limited` | 180s (3 min) | Soft degrade - too many requests |
| `timeout` | 120s (2 min) | Soft degrade - slow response |
| `transport-error` | 180s (3 min) | Soft degrade - connection/DNS failure |
| `endpoint-mismatch` | 900s (15 min) | Hard disable - wrong API endpoint |
| `model-unavailable` | 900s (15 min) | Hard disable - model not found |

**Penalty Scoring:**

```python
penalty = 0
penalty += min(consecutive_failures * 4, 20)

# Issue-specific penalties
if issue_type == "quota-exhausted": penalty += 24
elif issue_type == "auth-invalid": penalty += 26
elif issue_type == "rate-limited": penalty += 16
elif issue_type == "timeout": penalty += 8
elif issue_type == "transport-error": penalty += 10
elif issue_type == "endpoint-mismatch": penalty += 20
elif issue_type == "model-unavailable": penalty += 18

# Latency penalties
if avg_latency >= 4000ms: penalty += 12
elif avg_latency >= 2000ms: penalty += 6
elif avg_latency >= 1200ms: penalty += 3
```

Higher penalty = lower ranking in provider selection.

### 8. Configuration System

Master configuration file (`config.yaml`) with environment variable expansion:

```yaml
# Provider definitions
providers:
  deepseek-chat:
    base_url: ${DEEPSEEK_BASE_URL}
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    tier: budget
    capabilities:
      chat: true
      tools: false
      vision: false

# Routing policies (Layer 0)
routing_policies:
  enabled: true
  rules: [...]

# Client profiles
client_profiles:
  openclaw:
    profile:
      prefer_tiers: ["default", "reasoning"]

# Request hooks
request_hooks:
  enabled: true
  on_error: "continue"  # or "fail"
  hooks:
    - "my_custom_hook"

# Fallback chain (last resort)
fallback_chain:
  - "deepseek-chat"
  - "backup-provider"
```

---

## Data Flow

### Request → Routing Decision → Provider Selection

```
1. Client sends OpenAI-compatible request to /v1/chat/completions
   ├─ Headers: x-faigate-client, x-faigate-cache, x-faigate-stream
   ├─ Body: messages, model, temperature, max_tokens, tools, etc

2. main.py (gateway API layer)
   ├─ Parse request
   ├─ Sanitize inputs
   ├─ Extract routing context (client_profile, headers, body)

3. apply_request_hooks (from hooks.py)
   ├─ Load enabled hooks from config
   ├─ For each hook in order:
   │  ├─ Hook may modify body (messages, model, etc)
   │  ├─ Hook may override client_profile
   │  └─ Hook may inject routing_hints
   ├─ Accumulate results

4. router.route() (core routing engine)
   ├─ Extract text signals (system prompt, user message, full text)
   ├─ Estimate tokens, detect complexity keywords
   ├─ Build routing context
   │
   ├─ LAYER 0: Policy rules matching
   │  └─ If matched → RoutingDecision with confidence 0.95
   │
   ├─ LAYER 1: Static rules (model aliases)
   │  └─ If matched → RoutingDecision
   │
   ├─ LAYER 2: Heuristics (signal groups + complexity)
   │  └─ If matched → RoutingDecision
   │
   ├─ LAYER 3: Request hooks ranking
   │  └─ If hook_hints suggest provider → RoutingDecision
   │
   ├─ LAYER 4: Client profiles
   │  └─ If profile has prefer constraints → RoutingDecision
   │
   ├─ LAYER 5: LLM classifier (if enabled)
   │  └─ If ML model predicts → RoutingDecision
   │
   └─ FALLBACK: First provider in fallback_chain

5. Validate & Enrich Decision
   ├─ Check provider health
   ├─ If unhealthy, demote in candidate pool
   ├─ Apply quality tier scoring
   ├─ Apply routing mode multipliers (eco/premium/auto/free)

6. provider_backend.forward()
   ├─ Get provider config (base_url, api_key, model mapping)
   ├─ Build upstream request (auth, headers, model translation)
   ├─ Call upstream API
   ├─ Record latency
   ├─ On success: update health, record metrics
   ├─ On failure: classify issue, update pressure, record error
   ├─ Format response back to OpenAI-compatible format

7. metrics.record()
   ├─ Write routing decision to database
   ├─ Record provider used, latency, tokens, cost
   ├─ Update provider performance trends

8. Return response to client
   ├─ OpenAI-compatible format
   └─ Include routing metadata in x-faigate-* headers (optional)
```

---

## Layered Architecture

### Layer 1: Gateway API
**Files:** `main.py`

FastAPI application implementing OpenAI-compatible endpoints:
- `POST /v1/chat/completions` - Chat routing (primary entry point)
- `GET /v1/models` - Model discovery and availability
- `GET /health` - Health status and provider readiness
- `POST /api/route` - Dry-run routing decision preview
- `POST /api/route/image` - Image capability routing
- Dashboard endpoints for operator visibility

### Layer 2: Routing & Decision
**Files:** `router.py`, `adaptation.py`

Core intelligent routing engine:
- 6-layer cascade with first-match semantics
- Signal group analysis (complexity, domain, device type)
- Quality tier and lane-aware provider ranking
- Provider health tracking and adaptive degradation
- Capability-based routing for non-chat requests

### Layer 3: Configuration & Metadata
**Files:** `config.py`, `lane_registry.py`, `config.yaml`

Configuration foundation:
- YAML-based declarative policies and provider definitions
- Environment variable expansion with override support
- Canonical model lanes and quality tier metadata
- Validation and runtime schema enforcement
- Provider lane bindings and transport metadata

### Layer 4: Provider Management
**Files:** `providers.py`, `registry.py`

Provider backend abstraction and lifecycle:
- Unified async interface to OpenAI-compatible, Google GenAI, Anthropic APIs
- Request forwarding with auth handling (bearer, query, header)
- Model mapping and response format translation
- Health probing and provider verification
- Provider registry and initialization

### Layer 5: Request Pipeline & Extensions
**Files:** `hooks.py`

Extensible pre-routing customization:
- Plugin registration and execution
- Request body modification with sanitization
- Client profile and routing hint injection
- Error handling modes (fail-open/fail-closed)
- Hook composition and result aggregation

### Layer 6: Metrics & Analytics
**Files:** `metrics.py`, `dashboard.py`, `cli.py`

Operator observability and analytics:
- SQLite-based metrics persistence
- Routing decision recording and analysis
- Provider hotspot detection
- Client usage patterns and cost tracking
- Real-time dashboard for monitoring
- CLI tools for stats and reporting

### Layer 7: Operator Tools & Onboarding
**Files:** `wizard.py`, `onboarding.py`, `provider_catalog.py`, `updates.py`

Operator-facing utilities and setup automation:
- Interactive configuration wizard
- Onboarding readiness reports
- Provider discovery and catalog management
- Update checking and maintenance windows
- Validation and health checking helpers

---

## Key Modules Summary

| Module | Lines | Purpose |
|---|---|---|
| `router.py` | 2100 | Core 6-layer routing cascade, heuristics, signal groups |
| `main.py` | 850 | FastAPI gateway, request lifecycle, endpoint handlers |
| `config.py` | 1200 | YAML config loading, validation, runtime configuration |
| `lane_registry.py` | 900 | Canonical model lanes, quality tiers, metadata |
| `adaptation.py` | 350 | Provider health tracking, issue classification, cooldowns |
| `metrics.py` | 500 | Request metrics, cost tracking, SQLite persistence |
| `wizard.py` | 500 | Interactive configuration wizard for setup |
| `providers.py` | 800 | Provider backend abstraction, transport, auth |
| `hooks.py` | 400 | Request hooks system, plugin registration |
| `onboarding.py` | 400 | Onboarding reports, validation helpers |
| `dashboard.py` | 400 | Interactive monitoring dashboard |
| `cli.py` | 350 | Command-line tools and stats |
| `registry.py` | 300 | Provider registry and lifecycle |
| `provider_catalog.py` | 400 | Provider discovery, catalog reports |
| `updates.py` | 250 | Update checking, maintenance windows |

---

## Known Architectural Gaps & v1.9.0 Stress Test Findings

### Issues Identified & Fixed

1. **Routing Mode Pipeline Race Conditions (v1.9.0)**
   - **Issue:** Under high concurrency, routing_mode score multipliers sometimes applied inconsistently
   - **Fix (v1.9.1):** Atomic score updates, immutable context objects
   - **Impact:** Reliable eco/premium/auto routing under load

2. **Eco/Premium Tier Scoring Bias (v1.9.0)**
   - **Issue:** Quality tier scoring reversed for eco mode (favored premium instead of budget)
   - **Fix (v1.9.1):** Corrected multiplier application in `_score_candidates_for_mode()`
   - **Impact:** Eco mode now correctly prefers cost-effective providers

3. **Cache Header Parsing Edge Cases (v1.9.0)**
   - **Issue:** Malformed cache headers (trailing spaces, mixed case) caused routing failures
   - **Fix (v1.9.2):** Added `.strip().lower()` normalization on header parsing
   - **Impact:** Robust header handling with edge case tolerance

4. **Concurrent Health Degradation (v1.9.0)**
   - **Issue:** Multiple requests to degraded providers could race on pressure update
   - **Fix (v1.9.1):** Used atomic increment for consecutive_failures counter
   - **Impact:** Accurate failure tracking even under contention

5. **Hook Timeout Handling (v1.9.0)**
   - **Issue:** Long-running hooks blocked routing decision indefinitely
   - **Fix (v1.9.2):** Added 5-second timeout to hook execution with error fallback
   - **Impact:** Guaranteed routing latency bounds even with slow hooks

### Remaining Considerations

1. **LLM Classifier Performance:** Optional Layer 5 disabled by default due to latency; only recommended for specialized routing scenarios
2. **Provider Probe Reliability:** Probing strategy varies by backend (models vs chat endpoint); some providers return partial or inconsistent results
3. **Cache Key Consistency:** Implicit caching relies on stable request signatures; streaming requests skip caching
4. **Metrics Database Contention:** SQLite under high write load may cause latency spikes; consider Postgres for very high-volume deployments

---

## Integration Points

### With OpenClaw
- Header-based client detection: `x-openclaw-source`
- Automatic profile selection: `openclaw` preset with reasoning tier preference
- Delegation-aware routing: Special handling for agent-delegated requests

### With n8n
- Header-based client detection: `x-faigate-client: n8n`
- Workflow-friendly defaults: Budget tier preference, cost tracking
- Long-running workflow support: Streaming and async request handling

### With CLI & Scripts
- Header-based client detection: `x-faigate-client: cli,codex,claude`
- CLI-friendly routing: Balanced mode by default
- Command-line metrics access: `faigate-stats` tool

### Custom Applications
- OpenAI SDK compatible: Drop-in replacement for openai.OpenAI() client
- Custom headers: `x-faigate-client`, `x-faigate-cache`, `x-faigate-stream`
- Programmatic routing control: Via request hooks system

---

## Deployment Considerations

### Scaling
- **Single-machine:** Suitable for single user/small team with <10 requests/sec
- **Multi-instance:** Runs stateless; metrics database is only shared state
- **High-volume:** Consider Postgres for metrics DB, load balancer for request distribution

### Provider Configuration
- **Development:** Free/budget providers for cost control
- **Production:** Premium providers with fallback chains
- **Failover:** Multiple providers per lane with health-based selection

### Monitoring
- Health endpoint: `/health` for service checks
- Dashboard: Web UI for real-time metrics and hotspot detection
- Metrics DB: SQL queries for custom analysis and alerts

---

## Future Enhancement Opportunities

1. **Multi-modal Routing:** Specialized lanes for image generation, video, audio
2. **Cost Optimization:** Automatic provider selection based on cost targets
3. **SLA Enforcement:** Guaranteed latency/reliability via provider constraints
4. **Custom Metrics:** User-defined scoring functions for domain-specific routing
5. **Circuit Breakers:** Automatic provider disabling after threshold breaches
6. **Request Batching:** Aggregate similar requests to reduce per-request overhead
7. **Smart Retry:** Intelligent retry logic with exponential backoff per provider
8. **A/B Testing:** Traffic splitting for provider performance comparison
