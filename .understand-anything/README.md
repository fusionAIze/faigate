# fusionAIze Gate - Knowledge Graph & Architecture Guide

This directory contains comprehensive architectural analysis of the fusionAIze Gate codebase generated for deep understanding and navigation.

## Files in This Directory

### `knowledge-graph.json`
Machine-readable graph representation of the codebase structure.

**Contents:**
- **Project metadata:** Name, languages, frameworks, git commit hash
- **31 Nodes:** 16 source files, 15 architectural concepts
- **40 Edges:** Dependencies, implementations, usage relationships
- **7 Layers:** Architectural layering from API to operators
- **12-Step Tour:** Guided learning path through the system

**Schema:** See [KnowledgeGraph Format](#knowledge-graph-format) below.

### `ARCHITECTURE.md`
Comprehensive written guide to the codebase architecture.

**Sections:**
1. Project overview and metrics
2. Core architecture (6-layer routing, signal groups, quality tiers)
3. Policy rules engine and request hooks
4. Provider health and adaptation tracking
5. Configuration system and data flow
6. Layered architecture breakdown
7. Module summary table
8. Known gaps and stress test findings
9. Integration points (OpenClaw, n8n, CLI, custom apps)
10. Deployment and scaling considerations

**Start here** to understand how the system works end-to-end.

### `meta.json`
Metadata tracking for incremental updates.

Contains:
- Last analysis timestamp
- Git commit hash analyzed
- Number of files analyzed
- Schema version

---

## Quick Start

### Understanding the System

1. **Read `ARCHITECTURE.md`** (15 min) for the big picture:
   - 6-layer routing cascade
   - Signal groups and complexity detection
   - Policy rules and client profiles
   - Provider health and fallback chains

2. **Follow the 12-step tour** in `knowledge-graph.json`:
   - Start: Gateway entry point (main.py)
   - Middle: Core routing layers and configuration
   - End: Metrics, dashboards, and operator tools

3. **Explore key modules:**
   - `router.py` (2100 lines) - Core decision engine
   - `config.py` (1200 lines) - Configuration system
   - `main.py` (850 lines) - API gateway
   - `providers.py` (800 lines) - Provider backends

### Using the Knowledge Graph

**For developers integrating with faigate:**
```bash
# Query nodes by type
jq '.nodes[] | select(.type == "file") | {name, filePath}' knowledge-graph.json

# Find imports for a module
jq '.edges[] | select(.source == "file:faigate/router.py" and .type == "imports")' knowledge-graph.json

# List all architectural concepts
jq '.nodes[] | select(.type == "concept") | {name, summary}' knowledge-graph.json
```

**For understanding data flow:**
- See "Data Flow" section in ARCHITECTURE.md
- Trace edges from `file:faigate/main.py` through `file:faigate/router.py` to `file:faigate/providers.py`

**For routing decision logic:**
- Review `concept:routing-layers` and its contained layers
- Study `concept:signal-groups` for complexity detection
- Reference `concept:quality-tiers` for provider ranking

---

## Key Concepts

### 6-Layer Routing Cascade

The routing engine applies these layers in sequence; first match wins:

1. **Policy Rules** - Declarative rules from config.yaml with match conditions and select constraints
2. **Static Rules** - Hardcoded patterns (model aliases, known patterns)
3. **Heuristics** - Keyword analysis, complexity detection, signal groups
4. **Request Hooks** - Extensible pre-routing logic that can override or inject hints
5. **Client Profiles** - Named routing personas (openclaw, n8n, cli) with preset constraints
6. **LLM Classifier** - Optional ML-based classification (disabled by default)
7. **Fallback** - First provider in fallback_chain if no layer matches

### Signal Groups

Messages are classified using multiple signals:

- **Short message** → Fast/budget provider
- **Short + complex** → High-quality provider
- **Architecture/design keywords** → Reasoning-capable provider
- **Device type** (mobile) → Smaller/faster model
- **Has tools** → Tools-capable provider
- **Domain** (database, security, etc) → Domain-expert provider
- **Streaming requested** → Streaming-capable provider
- **Cache requested** → Cache-capable provider

### Quality Tiers & Lanes

Models grouped by capability cluster with quality scores:

- **elite-reasoning** (Opus, advanced): reasoning_strength=high, quality_tier=premium
- **quality-workhorse** (Sonnet, GPT-4o): reasoning_strength=high, quality_tier=high
- **balanced-workhorse** (mid-tier): reasoning_strength=mid, quality_tier=mid
- **fast-workhorse** (Haiku, Flash): reasoning_strength=mid, quality_tier=mid
- **budget-general** (free/cheap): reasoning_strength=low, quality_tier=budget

Tier scores: premium=10, high=8, mid=5, budget=2, free=1

### Provider Health & Adaptation

Health issues classified with cooldown windows:

- **quota-exhausted** (1800s) - Billing limit hit
- **auth-invalid** (1800s) - API key failure
- **rate-limited** (180s) - Too many requests
- **timeout** (120s) - Slow response
- **transport-error** (180s) - Connection failure
- **endpoint-mismatch** (900s) - Wrong API endpoint
- **model-unavailable** (900s) - Model not found

Penalty scoring penalizes issue_type, consecutive_failures, and high latency.

---

## Architecture at a Glance

```
┌────────────────────────────────────────────────────────┐
│                  Client Request                        │
│        (OpenAI-compatible /v1/chat/completions)       │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│              Gateway API Layer (main.py)               │
│          - Parse request, extract context              │
│          - Validate constraints, size limits            │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│           Request Hooks (hooks.py)                      │
│       - Modify body, override profile, inject hints    │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│        Routing & Decision Layer (router.py)            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Layer 0: Policy Rules                            │  │
│  │ Layer 1: Static Rules                            │  │
│  │ Layer 2: Heuristics & Signals                    │  │
│  │ Layer 3: Hook Hints                              │  │
│  │ Layer 4: Client Profiles                         │  │
│  │ Layer 5: LLM Classifier                          │  │
│  │ Fallback: First provider                         │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│      Provider Management (providers.py, registry.py)  │
│    - Health check, latency measurement, adaptation     │
│    - Auth handling, model mapping, transport           │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│    Upstream LLM Provider (OpenAI, Google, etc)        │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│      Metrics & Analytics (metrics.py)                  │
│   - Record decision, latency, tokens, cost             │
│   - Update provider trends, client usage               │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────┐
│   Monitoring & Dashboards (dashboard.py, cli.py)      │
│       - Real-time metrics, hotspots, alerts            │
└────────────────────────────────────────────────────────┘
```

---

## File Organization

```
faigate/
├── main.py               # FastAPI gateway, request lifecycle
├── router.py             # 6-layer routing cascade (2100 lines)
├── config.py             # Config loading, validation (1200 lines)
├── lane_registry.py      # Model lanes, quality tiers (900 lines)
├── adaptation.py         # Provider health tracking (350 lines)
├── providers.py          # Provider backend abstraction (800 lines)
├── hooks.py              # Request hooks plugin system (400 lines)
├── metrics.py            # Request metrics, SQLite persistence (500 lines)
├── registry.py           # Provider registry, lifecycle (300 lines)
├── provider_catalog.py   # Discovery, recommendations (400 lines)
├── updates.py            # Version checking, maintenance (250 lines)
├── dashboard.py          # Web monitoring dashboard (400 lines)
├── cli.py                # Command-line tools (350 lines)
├── wizard.py             # Interactive config wizard (500 lines)
├── onboarding.py         # Setup reports, validation (400 lines)
└── __init__.py

config.yaml              # Master configuration file (1100 lines)
```

---

## Common Tasks

### Adding a New Provider

1. **Define in config.yaml:**
   ```yaml
   providers:
     my-provider:
       base_url: ${MY_PROVIDER_BASE_URL}
       api_key: ${MY_PROVIDER_API_KEY}
       model: my-model-name
       tier: mid
       capabilities:
         chat: true
         tools: false
         vision: false
   ```

2. **Update fallback_chain:**
   ```yaml
   fallback_chain:
     - my-provider
     - existing-provider
   ```

3. **Optional: Add routing policy:**
   ```yaml
   routing_policies:
     rules:
       - name: "prefer-my-provider"
         match:
           client_profile: ["openclaw"]
         select:
           prefer_providers: ["my-provider"]
   ```

### Customizing Routing Logic

1. **Via Policy Rules** (recommended):
   - Add rules to `routing_policies.rules` in config.yaml
   - Match on: model_requested, keywords, tokens, client_profile, headers
   - Select using: prefer_tiers, allow_providers, require_capabilities

2. **Via Request Hooks** (advanced):
   - Implement hook function in custom module
   - Register in hooks.py: `register_request_hook("my_hook", my_function)`
   - Enable in config.yaml: `request_hooks.hooks: ["my_hook"]`
   - Hook can modify body, override profile, or inject routing_hints

3. **Via Client Profiles** (simple):
   - Define profile in config.yaml with preset select constraints
   - Match via request headers
   - Profile takes effect before LLM classifier

### Monitoring & Debugging

1. **Check health:**
   ```bash
   curl http://127.0.0.1:8090/health
   ```

2. **List available models:**
   ```bash
   curl http://127.0.0.1:8090/v1/models | jq
   ```

3. **Dry-run routing decision:**
   ```bash
   curl -X POST http://127.0.0.1:8090/api/route \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "..."}]}'
   ```

4. **View metrics:**
   ```bash
   faigate-stats --recent
   ```

5. **Access dashboard:**
   Navigate to `http://127.0.0.1:8091` in browser

---

## Known Issues & Mitigations

### v1.9.0 Stress Test Findings (Fixed in v1.9.1+)

1. **Routing Mode Race Conditions** → Fixed: Atomic score updates
2. **Eco/Premium Tier Scoring Bias** → Fixed: Corrected multiplier logic
3. **Cache Header Parsing** → Fixed: Strip and normalize headers
4. **Concurrent Health Degradation** → Fixed: Atomic failure counters
5. **Hook Timeout Handling** → Fixed: 5-second timeout with fallback

### Current Limitations

- **LLM Classifier disabled by default** - Adds latency, best for specialized scenarios
- **SQLite metrics under high load** - Consider Postgres for >1000 req/sec
- **Implicit caching key consistency** - Streaming requests skip caching
- **Provider probe variability** - Different backends use different probe strategies

---

## Knowledge Graph Format

### Nodes

```json
{
  "id": "file:faigate/router.py",
  "type": "file|function|class|module|concept",
  "name": "router.py",
  "filePath": "faigate/router.py",  // for file nodes
  "summary": "Core 6-layer routing engine...",
  "tags": ["routing", "decision-engine", "core"],
  "sizeLines": 2100  // for file nodes
}
```

### Edges

```json
{
  "source": "file:faigate/main.py",
  "target": "file:faigate/router.py",
  "type": "imports|calls|contains|implements|uses|depends_on|...",
  "weight": 0.9  // 0.0-1.0, indicates relationship strength
}
```

### Layers

```json
{
  "id": "layer:gateway-api",
  "name": "Gateway API Layer",
  "description": "FastAPI endpoints implementing...",
  "nodeIds": ["file:faigate/main.py", ...]
}
```

### Tour Steps

```json
{
  "order": 1,
  "title": "Gateway Entry Point",
  "description": "Start with the FastAPI application...",
  "nodeIds": ["file:faigate/main.py"],
  "languageLesson": "optional"
}
```

---

## Next Steps

1. **For quick understanding:** Read ARCHITECTURE.md sections 1-3
2. **For deep dive:** Follow the 12-step tour in knowledge-graph.json
3. **For implementation:** Review ARCHITECTURE.md section 8 (module summary)
4. **For operations:** Check ARCHITECTURE.md sections 9-10 (integration, deployment)
5. **For extension:** Study hooks.py and request_hooks section in config.yaml

---

## Related Files

- **Config Examples:** `config.yaml` (master configuration)
- **Test Files:** `tests/test_routing.py`, `tests/test_config.py`, etc
- **Documentation:** `README.md`, `docs/` directory
- **Scripts:** `scripts/faigate-*` (operator tools)

Generated: 2026-03-24
Git Commit: db0925bfa67f6421a08762e40fb8b5027d8b5f2e
Version: 1.0.0
