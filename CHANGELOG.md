# fusionAIze Gate Changelog

## v2.0.1 - 2026-04-04

### Added

- **OAuth wrapper for managed providers**: token store, generic OAuth backend, device-code flows for Google, Qwen, and Antigravity; `claude_code_oauth()` reads token from local claude CLI settings
- **Antigravity provider**: full registry, catalog, and lane-registry integration for `ag/` model family (Claude Opus/Sonnet 4.6, Gemini 3.x variants via Google Antigravity gateway)
- **Local worker GPU metrics**: probe GPU/VRAM usage from Ollama (`/api/ps`) and vLLM (`/metrics`); `GpuInfo` surfaced in discovery output and provider config
- **Dynamic model enumeration**: `dynamic_models` field on `DiscoveredWorker`; discovered models preferred over static defaults in `generate_provider_config`
- **Grid worker discovery**: reads `~/.faigrid/config.json` (JSON format) with fallback to legacy key=value state file
- **Per-client budget limits**: `cost_limit_usd_day` and `cost_limit_usd_month` fields in client profile config; HTTP 429 returned before routing when threshold is reached
- **Anomaly detection**: `MetricsStore.get_anomalies()` compares recent window to rolling baseline for error rate, latency, cost, and traffic spikes
- **Alerts API**: `GET /api/alerts` with configurable `lookback_hours` and `baseline_hours` parameters

### Changed

- `google-vertex` renamed to `google-gemini-cli` in registry and catalog (alias preserved for backward compatibility)

## v2.0.0 - 2026-04-03

### Added

- **Shell parity and intelligence**: CLI commands now integrate deeply with dashboard
  - `--suggest` argument analyzes metrics to recommend relevant CLI commands
  - `--link` generates dashboard deep‑link URLs with filters preserved
  - All CLI commands (`overview`, `recent`, `daily`, `trends`) show dashboard links
  - Filter arguments (`--provider`, `--modality`, `--client‑profile`, etc.) work across commands
  - Dashboard links include matching filters for seamless CLI→dashboard navigation
- **Safe config workflows**: New `faigate-config` CLI for config management
  - `preview`: Preview config changes before applying
  - `diff`: Show detailed config differences  
  - `apply`: Apply config changes with backup and confirmation
  - `validate`: Validate config syntax and structure
- **Clipboard integration**: `--copy` flag copies dashboard URLs to clipboard (macOS/Linux/Windows)
- **Scope suggestions**: CLI suggests relevant commands based on metrics analysis (failure rates, provider concentration, costs, recent activity)
- **Local worker auto‑discovery**: `faigate-config discover` automatically detects local AI workers (Ollama, vLLM, LM Studio, LiteLLM) and suggests configuration snippets
- **Complete provider coverage**: All LLM AI Router custom endpoints now represented in the provider catalog
  - Added missing providers: xAI, Z.AI, Mistral, Groq, HuggingFace, MoonshotAI, MiniMax, Volcano Engine, BytePlus, Qwen, OpenAI Codex, OpenCode Zen, Cerebras, GitHub Copilot, Synthetic, Kimi Coding, Vercel AI Gateway
  - Generic provider support (OpenAI, Anthropic, Google) with config examples
  - KiloCode model‑level access: individual catalog entries for `kilo‑auto/frontier`, `kilo‑auto/balanced`, `kilo‑auto/free`
  - Consistent `recommended_model` values across all providers
- **Local worker examples**: Commented configuration templates for Ollama, vLLM, LM Studio, LiteLLM in `config.yaml`
- **Enhanced provider catalog**: 41 curated provider entries (up from 17) with official source URLs, signup links, and volatility ratings

### Changed

- CLI help text updated with new arguments and examples
- Dashboard deep links use proper URL encoding and parameter validation
- Existing CLI commands remain fully backward compatible

## v1.21.0 - 2026-04-02

### Added

- Lane family decision factors table in dashboard Routes view with selection path breakdown per family
- Selection path categorization (same‑lane fallback, downgrade, primary) with colored pills
- Routes KPIs extended with same‑lane fallback and downgrade traffic percentages
- Enhanced route explainability for operator trust (v1.21.x roadmap)

### Changed

- Updated dashboard HTML and JavaScript to include new panel and aggregation logic
- Bumped version to 1.21.0

### Fixed

- No breaking changes; existing routing behavior remains compatible

## v1.20.0 - 2026-04-02

### Added

- External metadata integration: promotion alerts, source badges, provider-mix analytics endpoint (Issue #186)
- Route explainability dashboard and metrics: route_summary column, decision history panel, why_selected and alternatives display (Issue #188)
- Added `/api/analytics/provider-mix` endpoint for comparing providers based on external catalog pricing
- Enhanced dashboard Routes view with "Route decision history" table showing routing explanations
- Added `route_summary` field to metrics DB and `/api/traces` endpoint

### Changed

- Updated config.yaml metrics db_path default to `./faigate.db` and enabled metrics by default
- Extended `_build_route_summary` function to populate why_selected and alternatives
- Updated all six `log_request` calls to include route_summary

### Fixed

- No breaking changes; existing routing behavior remains compatible

## v1.17.0 - 2026-04-01

### Added

- Added router integration with offerings catalog for price-aware routing decisions (Phase 2b)
- Added package scoring based on remaining credits and expiry dates for intelligent routing
- Added detailed package overview to dashboard with credits, expiry, and provider mapping
- Added `_metadata_packages_detail()` function for detailed package insights
- Enhanced dashboard with package details section and cost projection improvements

### Changed

- Updated router cost estimation to prefer offering-specific pricing over provider defaults
- Improved provider dimension scoring with package score integration
- Extended dashboard metadata catalogs summary with package details
- No breaking changes; existing routing behavior remains compatible
## v1.18.0 - 2026-04-01

### Added

- Added cost projection wizard CLI (`faigate-stats --project`) for estimating costs across providers based on token usage patterns (Phase 2c)
- Added package management UI with enhanced dashboard views for packages, expiry alerts, and credit tracking
- Added analytics integration with `--trends` flag showing daily cost trends and projected monthly spend
- Added `faigate.cost` module with provider cost estimation and cross-provider comparison utilities

### Changed

- Extended dashboard alerts view with packages block showing credits, expiry, and expiring-soon warnings
- Enhanced CLI with `--trends` flag for historical cost/performance trend analysis
- No breaking changes; existing routing behavior remains compatible

## v1.16.0 - 2026-04-01

### Added

- Added external metadata schemas and catalogs for models, offerings, and packages (Phase 2a)
- Added environment variables `FAIGATE_OFFERINGS_METADATA_FILE` and `FAIGATE_PACKAGES_METADATA_FILE`
- Added `get_offerings_catalog()` and `get_packages_catalog()` public API functions
- Updated `sync-metadata.sh` to touch offerings and packages catalog files

### Changed

- Extended provider catalog loading to support offerings and packages catalogs alongside providers
- No breaking changes; all existing functionality remains unchanged

## v1.14.2 - 2026-03-31

### Added

- Added an optional shared provider metadata overlay path so Gate can load repo-backed provider catalog snapshots and merge them into the runtime catalog.
- Added `faigate-provider-metadata-sync` plus restart/update integration so provider metadata snapshots can be materialized automatically before Gate restarts.

### Changed

- Documented the fusionAIze-only shared metadata repo shape and shipped example catalog/overlay JSON for Gate, including initial tracked metadata coverage for `anthropic-haiku`, `anthropic-sonnet`, and `gemini-pro`.

## v1.14.1 - 2026-03-31

### Added

- (New release baseline)

## v1.14.0 - 2026-03-31

### Added

- (New release baseline)

## v1.15.0 - 2026-04-01

### Added

- Enhanced provider catalog system with cost truth reporting, priority clusters, and actionable recommendations similar to llmairouter.com
- Integrated external `fusionaize-metadata` repository for centralized provider metadata management
- Added numeric pricing rates lookup from external catalog, overlay, and built-in registry
- Added dashboard metric cards for cost truth and priority cluster visualizations
- Added provider discovery recommendations with actionable improvement suggestions

### Changed

- Increased line length to 120 characters (modern standard) across codebase
- Reframed Claude-native bridge model aliases around routing intent instead of direct frontier spend: built-in Claude Code model ids now resolve to `auto`, `premium`, or `eco` so Gate can still choose the cheapest capable route for the request
- Tightened the shipped config and integration examples around coding auto modes, so `claude`, `opencode`, `openclaw`, and related coding clients can share clearer `coding-auto`, `coding-fast`, and `coding-premium` entry points instead of muddled provider-first defaults
- Updated the roadmap and implementation plan to prioritize cost-aware coding auto modes first, then stronger product surfaces and licensing-aware stack boundaries for Gate as a standalone product
- Added a dedicated dashboard IA document so the next web and shell dashboard work is grouped around operator jobs such as overview, providers, clients, routes, analytics, request log, integrations, and troubleshooting instead of one long admin surface

## v1.15.1 - 2026-04-01

### Fixed

- Removed hardcoded user path (`/Users/andrelange/Documents/repositories/github/fusionaize-metadata`) from external metadata integration
- Changed default metadata root to non-existent path, preventing unauthorized directory access requests
- Updated `sync-metadata.sh` to use `~/.faigate/metadata` or `FAIGATE_METADATA_DIR` environment variable
- External metadata remains opt-in via `FAIGATE_PROVIDER_METADATA_DIR` environment variable

## Unreleased

## v1.13.0 - 2026-03-30

### Added

- Added an optional Anthropic-compatible bridge inside Gate with `POST /v1/messages` and `POST /v1/messages/count_tokens`, so Claude-native clients can enter through a dedicated surface without splitting routing, policy, health, or fallback behavior into a second gateway
- Added an internal canonical request and response layer for bridge traffic, which keeps Anthropic-shaped ingress mapping separate from the existing routing and completion core instead of adding one-off protocol logic directly in the router
- Added a community `claude-code-router` hook that can prefer coding-strong, tool-capable, and larger-context routes for Claude Code traffic without making the bridge itself depend on any one routing policy
- Added bridge-specific validation and release-readiness helpers, including a client-near validation script and an explicit bridge release checklist for opt-in production rollouts
- Expanded the provider source catalog scope beyond `blackbox`, `kilo`, and `openai` so Gate can also track mirrored official source data for `anthropic`, `deepseek`, and `google`
- Added local models-endpoint overlays per configured route, which lets Gate compare what a specific key can really see against the mirrored global provider catalog

### Changed

- Hardened Anthropic bridge compatibility for real operator workflows: basic `tool_use` / `tool_result` flows now stay on the same execution path, Anthropic version and beta headers survive the bridge, and bridge responses expose the key route-resolution headers needed for debugging
- Improved quota-aware fallback behavior for Anthropic-shaped traffic by introducing shared quota metadata on routes, which lets Gate avoid blindly retrying another path that is still backed by the same exhausted Anthropic or BYOK quota domain
- Clarified the Bridge release position across docs: `v1.13.0` ships the Anthropic surface as opt-in and production-usable for early adopters, but does not claim full Anthropic, Claude Code, or Claude Desktop parity yet
- Aligned the doctor and bridge validation tooling with non-default live configs so release validation runs against the same configured DB, env file, and runtime instance instead of silently falling back to repo-local defaults
- Provider source alerts now distinguish more clearly between global catalog drift and key-specific route/model visibility drift
- Catalog summaries now include local route counts, local visible model counts, and route-vs-catalog mismatch hints instead of only source freshness and change counts

## v1.12.0 - 2026-03-29

### Added

- Added a provider source catalog line with startup refresh, dashboard/API summaries, and operator-facing alert actions across `faigate-doctor`, `faigate-provider-probe`, and Quick Setup so model/pricing drift is visible earlier instead of hiding behind stale curated assumptions
- Added explicit Kilo paid workhorse lanes for Sonnet and Opus plus Kilo-specific routing fit scoring, which lets Gate model premium, balanced, and free Kilo traffic without relying on opaque `kilo-auto/*` header behavior
- Added route-preview coverage for Kilo frontier lane selection so operators can see when Gate chose `kilo-opus`, `kilo-sonnet`, or `kilocode` and why
- Added stronger release automation dry-run coverage so the release helper itself is exercised in CI before a tagged release is cut

### Changed

- Hardened release automation end-to-end: local release scripts now validate versions more strictly, verify package metadata coherency, and point to the dedicated `fusionAIze/homebrew-tap` repository instead of assuming a local formula in this repo
- Release artifact publishing now validates tag/version alignment before publishing and reuses prebuilt Python artifacts for PyPI instead of rebuilding a second time in the publish job
- Reframed the legacy `blackbox-free` route as a low-cost burst path rather than a guaranteed free path, because the currently working curated model is not reliably the `:free` SKU for every key
- Updated Kilo defaults and examples to use the current gateway base URL without the stale `/v1` suffix

## v1.11.2 - 2026-03-29

### Changed

- Restored Python 3.10 compatibility for the release update helpers by falling back cleanly when `datetime.UTC` is unavailable, which fixes the release CI collection failure that blocked the `v1.11.x` line
- Realigned the runtime version surfaces so package metadata, `faigate --version`, and the FastAPI app version all move together again instead of reporting mixed `1.10.1` / `1.11.x` values

## v1.11.1 - 2026-03-29

### Changed

- Established the current release-driven changelog baseline so subsequent `v1.11.x+` entries stay grouped by real user-visible behavior instead of placeholder release notes

## v1.11.0 - 2026-03-29

### Added

- **Gemini 3 / 3.1 Modernization** — full rollout of Google Gemini 3 Flash and Gemini 3.1 Pro (High/Low) models across all surfaces:
  - `google/gemini-flash` now resolves to `gemini-3-flash`
  - `google/gemini-flash-lite` now resolves to `gemini-3-flash-lite`
  - `google/gemini-pro-high` and `google/gemini-pro-low` added for high-reasoning and balanced Gemini 3.1 Pro lanes
- **Flexible Model Labels** — centralized model version mapping in `lane_registry.py`:
  - New `_ACTIVE_MODEL_VERSIONS` and `_MODEL_VERSION_LABELS` lookup tables
  - Decouples canonical lanes (e.g. `openai/gpt-4o`) from concrete provider strings (e.g. `gpt-4o`)
  - Ensures consistent labels and IDs across config, catalog, wizard, and dashboard
- **Updated Catalog & Wizard** — `provider_catalog.py` and `wizard.py` refactored to use dynamic model helpers:
  - Removes hardcoded Gemini 2.5 strings from recommendation logic
  - Synchronizes curated aliases and notes with the new versioned metadata
- **Release Automation** — new `scripts/faigate-release` Python tool to automate version bumping, changelog updates, and Homebrew formula syncing.

### Changed

- `lane_registry.py` now exports `get_active_model_id(canonical_id)` and `get_active_model_label(canonical_id)` for shared use.
- Anthropic default model in wizard updated to `claude-3-5-sonnet-20241022` (Sonnet 4.6).

## v1.10.1 - 2026-03-25

### Added

- **`hooks/adapters/grok_api_adapter.py`** — OpenAI-compat adapter that bridges faigate's virtual `grok-xai` provider to Grok's web interface (no XAI API key required):
  - Exposes `GET /v1/models` and `POST /v1/chat/completions` on port 8091
  - Translates OpenAI messages array → single Grok prompt (system prompt + history + last user message)
  - Maps model names: `grok-3` → `grok-3-auto`, `grok-3-fast`, `grok-4`, `grok-4-mini-*`
  - Full streaming via SSE (uses Grok-Api's `stream_response` token list)
  - Runs from fusionAIze/grok-api-hook fork for stability
  - `GET /health` endpoint for liveness checking
- **Virtual provider registration** — community hooks can now register providers programmatically without `config.yaml` entries:
  - `register_virtual_provider(name, config)` in `hooks.py` — validates `base_url` + `model`, sets safe defaults
  - `get_virtual_providers()` — returns all registered virtual providers
  - `load_community_hooks()` now passes `register_virtual_provider` as optional second arg when hook's `register()` accepts it
  - `main.py` startup merges virtual providers into `_providers` after config-defined providers (config wins on name collision)
- **`grok-wrapper` updated** — now registers `grok-xai` as a virtual provider (tier: mid, cost: free, latency: slow) pointing to `http://127.0.0.1:8091/v1` with full lane + capabilities metadata

### Changed

- `hooks/grok-wrapper.py` now uses two-arg `register(register_fn, register_provider_fn)` signature
- All references updated to use fusionAIze/grok-api-hook fork

## v1.10.0 - 2026-03-24

### Added

- **Cache Intelligence layer** — all providers now carry precise cache metadata in `config.yaml` and the routing engine uses it for cost estimation and scoring:
  - `cache.min_prefix_tokens` — minimum stable prefix required for cache activation (provider-specific: 64 for DeepSeek, 1024 for Google, 1024 for Anthropic)
  - `cache.ttl_seconds` — provider cache lifetime (0 = unknown; Google: 3600 s, Anthropic: 300 s)
  - `cache.max_cached_tokens` — maximum prefix retained in cache (64k for DeepSeek, 1M for Google, 32k for Anthropic)
  - `cache.cache_read_discount` — actual cost ratio of cached vs fresh input tokens (e.g. DeepSeek: 0.07, Anthropic: 0.10, Google Flash: 0.04)
  - `cache.cache_write_surcharge` — write cost multiplier for explicit-mode caches (Anthropic: 1.25, others: 1.0)
  - Cache threshold in `router.py` is now provider-aware (`max(64, min_prefix_tokens)` per provider)
  - Cache scoring bonus in `router.py` rewards providers where cache is likely to activate given the current request shape
  - `/route` endpoint response now includes a `cache_intelligence` block with activation forecast, estimated savings, TTL, and write surcharge
- **Community / plugin hook system** — faigate now supports dropping custom Python hooks into a directory without editing core code:
  - `load_community_hooks(plugin_dir)` in `hooks.py` scans `*.py` files in the configured dir and calls their `register(register_fn)` entry point
  - `community_hooks_dir` config key added to `request_hooks` section; community hooks are loaded before hook-name validation so plugin names pass cleanly
  - Community hooks are logged at startup and exposed in `/health` response under `community_hooks`
  - `get_community_hooks_loaded()` utility function for observability
- **`hooks/grok-wrapper.py`** — first community hook example, ships with faigate:
  - Automatically routes requests to `grok-xai` when the model name is a known Grok variant (`grok-3`, `grok-3-mini`, `grok-3-fast`, `grok-2`, …) or starts with `grok-`
  - Also triggered by `X-Faigate-Grok: 1` / `true` / `yes` request header
  - Includes full install instructions and self-documenting docstring
- **`grok-xai` provider template** in `config.yaml` section B — full lane + cache + capabilities metadata for xAI Grok 3 (commented out; activate with `XAI_API_KEY`)
- Updated `request_hooks` config comment block to document `community_hooks_dir`, example usage, and grok-wrapper installation steps

## v1.9.2 - 2026-03-24

### Fixed

- Fixed `routing_mode` from request hooks being silently discarded — `_sanitize_routing_hints` now accepts and preserves `routing_mode` as a first-class hint field; `_merge_routing_hints` propagates it through the hook pipeline so `X-faigate-Mode` header overrides correctly reach the scoring layer
- Fixed `X-faigate-Mode: eco` and `X-faigate-Mode: premium` being ignored on short prompts — `_evaluate_heuristic_match` now bypasses `short-message` and `general-default` rules when an explicit `routing_mode` hint is present, allowing mode-specific scoring to run regardless of token count

### Added

- Three new providers using existing API keys — no new credentials required:
  - `anthropic-sonnet`: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — quality-workhorse lane, `cost_tier: standard` (~$3/MTok input), high reasoning and tool strength, degrade-to: haiku → deepseek-chat
  - `anthropic-haiku`: Claude Haiku 3.5 (`claude-haiku-3-5`) — fast-workhorse lane, `cost_tier: cheap` (~$0.80/MTok input), degrade-to: deepseek-chat → gemini-flash
  - `gemini-pro`: Gemini 2.5 Pro (`gemini-2.5-pro`) — quality-workhorse lane, `cost_tier: premium`, high reasoning and context strength (1M token context window), degrade-to: gemini-flash → deepseek-reasoner
- Added proper `lane:` metadata block to `gemini-flash-lite` (was missing, preventing correct cluster-based scoring)
- Updated global `fallback_chain` to reflect full provider depth: deepseek-chat → anthropic-haiku → gemini-flash → deepseek-reasoner → anthropic-sonnet → gemini-pro → openai-gpt4o → openrouter-fallback → anthropic-claude → kilocode → blackbox-free
- Updated `routing_modes.eco` to explicitly prefer anthropic-haiku, gemini-flash-lite, gemini-flash, deepseek-chat
- Updated `routing_modes.premium` to prefer anthropic-sonnet, openai-gpt4o, gemini-pro, anthropic-claude, deepseek-reasoner
- Updated `opencode` client profile to include `high` quality tier so Sonnet/Gemini Pro are reachable in auto mode
- Added `anthropic-sonnet`, `anthropic-haiku`, `gemini-pro` to `model_shortcuts`
- Enabled `routing_modes` (was `enabled: false`)

## v1.9.1 - 2026-03-24

### Fixed

- Corrected version strings in `__init__.py` and `main.py` which incorrectly reported `1.8.0` after the v1.9.0 release
- Fixed `load_dotenv()` in `config.py` so the service correctly resolves `faigate.env` from the config directory (`/opt/homebrew/etc/faigate/`) instead of searching upward from the package installation path, which caused all providers to start in `unresolved-key` state when run via Homebrew launchd

### Added

- Added `mode-override-header` request hook that reads the new `X-faigate-Mode` header and maps it to a routing posture (`auto`, `eco`, `premium`, `free`, plus common aliases `quality`, `save`, `cheap`, `balanced`, `standard`); unknown values are silently ignored
- Updated `_routing_posture()` to check `hook_hints.routing_mode` before `profile_hints.routing_mode` so the header override takes effect end-to-end
- Expanded `opencode` signal groups from 5 to 10 by adding `devops` (kubernetes, terraform, helm, ci/cd, …), `testing` (unit tests, integration tests, pytest, jest, tdd, coverage, …), `security` (jwt, oauth, xss, sql injection, csrf, rbac, …), and `database` (schema, query optimization, index, replication, sharding, …) — each group triggers `short_complex` escalation to reasoning lanes when ≥ 2 groups fire on a brief prompt
- Added plural keyword forms (`unit tests`, `integration tests`) to the `testing` signal group so word-boundary matching no longer silently drops plural prompts
- Extended `_OPENCODE_COMPLEXITY_HINTS` and `_OPENCODE_COMPLEXITY_RULE_KEYWORDS` with event sourcing, cqrs, kubernetes, terraform, infrastructure as code, unit test, integration test, jwt, sql injection, vulnerability, schema, replication, and query optimization terms
- Added `short_complex` and `prefer_providers` bypass guards in `_evaluate_heuristic_match` so brief cross-domain prompts and explicit provider-preference requests skip the `short-message` and `general-default` fallthrough rules and reach the profile scoring layer

## v1.9.0 - 2026-03-23

### Changed

- Strengthened short-but-risky `opencode` prompt detection so brief architecture, queue/backpressure, and rollout-planning requests escalate out of cheap lanes earlier instead of being flattened by generic short-query heuristics
- Expanded route-preview explainability with structured complexity reasons plus explicit `why_not_selected` guidance for cheaper alternatives, so operators can now see why a lower-cost lane lost on reasoning depth, benchmark fit, freshness, or runtime pressure

## v1.8.0 - 2026-03-22

### Changed

- Started the adaptive-orchestration runtime line with canonical model-lane and provider-route metadata in config, wizard, runtime inventory, and provider-catalog surfaces
- Added the first lane-aware router scoring slice so `quality`, `balanced`, `eco`, and `free` postures now influence candidate ranking through lane cluster, benchmark cluster, route type, and runtime pressure instead of only provider tier
- Added Same-Lane-Route fallback preference before weaker cluster downgrades when a compatible alternate route exists for the same canonical model
- Added an in-memory adaptation state for rate-limit, quota, timeout, and latency pressure so hot routes can be demoted conservatively at runtime
- Persisted routing explainability fields such as `canonical_model`, `route_type`, `lane_cluster`, `selection_path`, and `decision_details` into metrics and route traces
- Expanded candidate cards, client scenarios, and provider dashboard drilldowns so operators can now see route mirrors, degrade chains, canonical lanes, and runtime penalties directly in Gate

## v1.7.1 - 2026-03-22

### Changed

- Tightened the terminal header rendering again so interactive screens no longer insert apparent blank spacer lines between the three wordmark rows
- Fixed the client-scenario apply flow so choosing `Write config` now returns cleanly to the calling menu after the confirmation step instead of dropping operators straight back into the same scenario list

## v1.7.0 - 2026-03-22

### Changed

- Added internal Gate drilldowns for client quickstarts, provider discovery, and dashboard details so operators no longer need to leave the menu just to open one parameterized view
- Expanded client scenarios into lane-based explanations with explicit quality, reasoning, workhorse, budget, and fallback roles so templates like `opencode / balanced` now explain why `kilocode`, `blackbox-free`, or `openrouter-fallback` are in or out
- Added family-coverage hints for scenario output so operators can see when a provider family currently has only one quality or balanced slot and would need separate provider entries for richer `Opus / Sonnet / Haiku`-style splits
- Refined the shell header color segmentation again to match the tighter blue / yellow / blue / green brand grouping across all three wordmark rows

## v1.6.3 - 2026-03-22

### Changed

- Hardened config-wizard merge writes so existing configs with `null` sections such as `client_profiles.rules`, `routing_policies.rules`, or `request_hooks.hooks` now merge into real runtime config safely instead of failing mid-write
- Closed the remaining Homebrew helper-parity gap so user-facing commands such as `faigate-config-wizard`, `faigate-status`, `faigate-restart`, `faigate-logs`, `faigate-start`, `faigate-stop`, `faigate-update`, and `faigate-auto-update` ship through the Brew formula too
- Refined the terminal wordmark again with the new three-color brand palette and kept the inline version sourced dynamically from the current package version

## v1.6.2 - 2026-03-22

### Changed

- Fixed the config-wizard write path so guided `Write config` flows persist the actual runtime config instead of accidentally writing the `purpose/client/suggestions` summary payload back into `config.yaml`
- Added an explicit doctor warning when `config.yaml` appears to contain wizard summary keys, which makes accidental miswrites easier to catch before restart and rollout work
- Restored executable bits for packaged helper scripts such as `faigate-config-wizard`, `faigate-config-overview`, `faigate-provider-discovery`, and the onboarding/client helper scripts so Brew-installed helper entrypoints no longer fail with `Permission denied`

## v1.6.1 - 2026-03-20

### Changed

- Fixed the packaged `faigate-dashboard` helper so the shipped script keeps its executable bit and the Brew-installed dashboard no longer fails with `Permission denied`
- Polished the interactive terminal wordmark again so the large `I` aligns with the intended shape and the current version now appears inline at the right edge of the logo in the same subdued tone as the subtitle

## v1.6.0 - 2026-03-20
### Added

- Added `faigate-provider-setup` plus matching `Quick Setup` / `Configure` menu entries so operators can add known providers, custom OpenAI-compatible upstreams, and local workers before dropping into the purpose-aware config wizard
- Added `faigate-provider-probe` so configured sources can be checked against config, env, and the live `/health` payload before client rollout begins
- Added `faigate-client-scenarios` plus matching menu entries so operators can apply named templates such as `opencode / eco`, `opencode / quality`, `n8n / reliable`, or `cli / free` instead of thinking only in raw profile-mode edits
- Added `faigate-dashboard` plus a new top-level `Dashboard` menu section so operators now get one shell-native performance view for traffic, latency, spend, token volume, provider/client hotspots, and action-oriented alerts

### Changed

- Tightened the onboarding docs and main README around the new provider-source-first UX so first setup now reads more like `Provider Setup -> Provider Probe -> API Keys -> Full Config Wizard -> Client Scenarios -> Validate -> Client Quickstarts`
- Renamed the old `FOUNDRYGATE STATS` CLI banner to `fusionAIze Gate Stats` so the terminal metrics surfaces stay on-brand
- Expanded client scenarios with clearer `budget`, `best when`, and `tradeoff` guidance so operators can pick templates by intent instead of only by routing-mode names
- Expanded the new dashboard with budget, quota, and routing-pressure hints so it now helps answer whether traffic should shift, a cheaper scenario is worth trying, or a provider likely needs more budget

- Added a dedicated adaptive-orchestration roadmap that sketches the path from lane metadata to scoring, live adaptation, benchmark freshness, and budget-/quota-aware routing through the `v1.10.x` and `v1.11.x` lines

## v1.5.1 - 2026-03-20

### Changed

- Reworked the interactive config wizard candidate screen so purpose/client selection now shows compact `Ready now`, `More options if you add keys`, and `Optional specialty add-ons` cards instead of a raw provider metadata dump
- Improved the client quickstart surfaces so the menu and client helper now show a clearer `Best next step` hint and friendlier `Preset matches` wording instead of implying that `Presets 0` means something is broken
- Clarified the API-key helper so provider base URL overrides are explicitly labeled as optional upstream overrides, reducing confusion between local Gate client URLs and upstream provider endpoints
- Nudged the terminal logo spacing closer to the intended fusionAIze Gate wordmark in interactive screens

## v1.5.0 - 2026-03-20

### Changed

- Fixed the standalone shell helpers on macOS/Homebrew so service status, logs, and service-manager labels now recognize the Brew-managed `homebrew.mxcl.faigate` path instead of assuming only the manual LaunchAgent path
- Fixed `faigate-menu` model listing so it parses the `/v1/models` payload correctly instead of trying to read JSON through a broken stdin pipeline
- Fixed `faigate-auto-update` on macOS's default Bash 3.2 by removing the `mapfile` dependency from its payload parsing path
- Fixed user-facing helper scripts so `--help` exits safely instead of accidentally triggering live install/update logic in shell environments that only wanted usage text
- Improved `faigate-health`, `faigate-update-check`, and `faigate-menu` so operators now see compact human-readable summaries before diving into raw payloads
- Added a service-manager mismatch warning when `/health` responds but the configured manager reports a stopped or missing service, which helps catch stale old runtimes still bound to the same port
- Polished the terminal header to align more closely with the intended fusionAIze Gate visual identity in interactive terminals
- Added a dedicated `Quick Setup` happy path and summary cards for gateway, config, providers, and clients in the main menu flows
- Updated the client helper and the `Clients` menu so operators see compact recommendation cards first and can drill into one client without dumping the full cross-client quickstart wall every time
- Added first `Next step` receipts after the key guided actions in the shell flow so wizard, validation, restart, and client-setup paths now end with a short operator-oriented “what to do next” block

## v1.4.5 - 2026-03-19

### Added

- Added a first `faigate-menu` control center with a shared terminal UI, the new fusionAIze Gate header, and consistent `q`/`c` navigation across status, configure, explore, validate, control, and update menus
- Added `faigate-api-keys` and `faigate-server-settings` so API keys, host, port, and log-level changes have a Gate-native interactive path instead of living only in external orchestration layers
- Added `faigate-routing-settings` so the global default routing mode and client-profile routing defaults can be reviewed and adjusted from the same Gate-native control flow
- Added `faigate-client-integrations` plus a `Clients` section in `faigate-menu` so OpenClaw, n8n, opencode, and generic CLI quickstarts can be reviewed and driven through client-scoped wizard flows
- Added `faigate-config-overview` plus a clearer `Current Config` / `Guided Setup` / `Direct Settings` split inside `faigate-menu` so configuration flows now map more cleanly to the later Grid-style orchestration model

### Changed

- Aligned helper scripts such as `faigate-health`, `faigate-status`, `faigate-update-check`, `faigate-auto-update`, and `faigate-doctor` around shared config/env/port resolution so repo, packaged, and later Grid-driven flows can behave consistently
- Extended install and Homebrew helper exposure so the new menu/config helpers can ship through the same operator-facing paths as the existing scripts
- Expanded `faigate-status`, `faigate-logs`, and `faigate-restart` so service control now carries clearer service-manager context, recent-vs-live log flows, and restart verification instead of only raw process-manager commands
- Polished `faigate-menu` with compact runtime/config snapshots in the main and control/config submenus plus short inline tips so the shell UX stays self-orienting between steps

## v1.4.0 - 2026-03-19

### Changed

- Renamed the product branding from `FoundryGate` to `fusionAIze Gate` across the repository, documentation, examples, and operator-facing surfaces
- Renamed the technical runtime slug from `foundrygate` to `faigate`, including the Python package, npm CLI package, helper scripts, example file names, service templates, and Homebrew formula path
- Moved the repository references from `typelicious/FoundryGate` to `fusionAIze/faigate` and aligned env prefixes, headers, and operational examples with the new `FAIGATE_` / `x-faigate-*` naming
- Completed the first release-prep baseline for the rebrand so future releases, installs, and documentation no longer depend on the old names

## v1.3.0 - 2026-03-19

### Added

- Added a first `faigate-config-wizard` helper that suggests an initial `config.yaml` from the API keys already present in `.env`
- Added first-class `routing_modes` and `model_shortcuts` config blocks so virtual model ids such as `auto`, `eco`, `premium`, `free`, or custom names can participate in routing
- Added wizard candidate listing and conservative config merging so operators can select multiple provider candidates during first setup or later catalog-driven updates
- Added config-aware wizard update suggestions so existing installs can see `recommended_add`, `recommended_replace`, and `recommended_keep` groups before applying provider changes
- Added wizard `recommended_mode_changes` suggestions so existing client profiles can be nudged toward the current purpose-aware routing defaults without silently rewriting them
- Added an `apply suggestions` wizard flow so selected provider and client-mode recommendations can be merged into an existing config without manual copy/paste
- Added a wizard dry-run change summary so operators can preview added providers, model replacements, fallback changes, and client-mode changes before writing config updates
- Added optional wizard write-backup snapshots so config updates can keep a local pre-change copy before overwriting `config.yaml`
- Added a built-in `faigate-config-wizard --help` flow so first setup, catalog review, update suggestions, dry-run previews, and backup-aware writes are all discoverable directly from the CLI
- Added optional provider-catalog discovery metadata and env-backed signup-link overrides so future CLI or control-center surfaces can show disclosed provider links without mixing link configuration into normal config files
- Added first CLI surfacing of disclosed provider discovery links in onboarding and doctor outputs, always alongside a link-neutral recommendation policy signal
- Added `faigate-provider-discovery` for one compact text/JSON discovery view that later browser or control-center work can consume
- Added discovery-link filters for CLI and API views so operators can narrow provider links by `offer_track`, `link_source`, or `disclosed_only`

### Changed

- `client_profiles` can now choose a default `routing_mode`, letting one client keep the global mode while another uses a different or custom mode by default
- `GET /v1/models`, route previews, and runtime response headers now expose configured routing modes and resolved shortcut/mode metadata
- `faigate-doctor`, onboarding reports, and the provider-catalog API now surface curated model-drift, source-confidence, volatility, and catalog-freshness alerts for configured providers
- Provider catalog entries now distinguish direct providers from aggregators and wallet routers, track auth modes such as `api_key`, `byok`, and `wallet_x402`, and keep community watchlists explicitly secondary to official sources
- `faigate-config-wizard` can now filter candidates by purpose and client, accept multi-select provider input, and merge selected providers back into an existing config instead of forcing a full rewrite
- Tightened the roadmap and user-facing docs around `v1.3.0` so guided setup, catalog-assisted updates, and future recommendation-link work stay transparent and clearly separated from ranking logic
- Provider discovery metadata now carries an explicit link-neutral recommendation policy so provider-link configuration can never be mistaken for a ranking signal

## v1.2.3 - 2026-03-19

### Changed

- Hardened the Homebrew formula so native Python extensions such as `pydantic-core` and `watchfiles` are built from source with extra Mach-O header padding on macOS instead of relying on the vendored wheel layout
- Strengthened the formula test so it validates the wrapped `faigate --version` entrypoint instead of only importing the package inside `libexec`
- Fixed the Python service entrypoint so `python -m faigate.main` and the Brew-managed wrapper both execute the runtime correctly
- Clarified in the README, workstation guide, and troubleshooting docs that active Python virtualenvs can shadow the Brew-installed `faigate` binary

## v1.2.1 - 2026-03-19

### Changed

- Switched the Homebrew formula baseline from `python@3.13` to `python@3.12` to reduce macOS packaging friction around vendored native Python wheels
- Clarified in the README and workstation docs that `brew install faigate` resolves cleanly after tapping `fusionAIze/faigate`, while the fully qualified install path remains the safest first-run example

## v1.2.0 - 2026-03-19

### Added

- Added a workstation operations guide for Linux, macOS, and Windows runtime layouts
- Added a macOS `launchd` LaunchAgent example for local workstation installs
- Added Windows PowerShell and Task Scheduler starter examples for local workstation installs
- Added platform-aware runtime helper scripts so macOS can use the same `faigate-install` / `start` / `stop` / `status` flow style as Linux
- Added a project-owned Homebrew formula plus `brew services` guidance for packaged macOS workstation installs
- Added explicit `FAIGATE_CONFIG_FILE` config discovery and `faigate --config` / `--version` support so service wrappers and packaged installs can point to config outside the repo
- Added a helper-level onboarding smoke test for explicit config/env/python wiring

### Changed

- Updated the README quickstart so Linux, macOS, Windows, and Homebrew paths are visible earlier
- Replaced the weak PyPI workflow badge with clearer workstation and Homebrew badges

## v1.1.0 - 2026-03-16

### Added

- Added richer client usage reporting in `GET /api/stats` and the dashboard, including per-client tokens, failures, success rate, and aggregate client totals
- Added a second wave of AI-native starter templates for Agno, Semantic Kernel, Haystack, Mastra, and Google ADK
- Added client highlight summaries to `GET /api/stats` and the built-in dashboard for top request, token, cost, failure, and latency signals
- Added a third wave of AI-native starter templates for AutoGen, LlamaIndex, CrewAI, PydanticAI, and CAMEL

### Changed

- Tightened `static` and `heuristic` match semantics so combined fields now behave as cumulative constraints unless `any:` is used explicitly
- Tightened `policy` match semantics so `client_profile` acts as an additive constraint inside one rule instead of bypassing sibling static or heuristic fields

## v1.0.0 - 2026-03-15

### Added

- Added dashboard CSP hashes plus stricter response-security defaults for the no-build operator UI
- Added stronger provider base URL validation so non-local upstreams must use `https`
- Added reduced leakage of upstream provider failure details in client-facing error payloads
- Added a separate npm CLI package under `packages/faigate-cli` for basic health, model, update, and route-preview checks
- Added a documented `v1.0.0` security review with mitigations and residual-risk notes
- Added functional API coverage for upstream error sanitization on top of the earlier dashboard and request-boundary hardening tests
- Streamlined the root README into a shorter landing page and moved deeper API, configuration, and operations detail into dedicated docs pages

## v0.9.0 - 2026-03-15

### Added

- Added conservative response-security headers plus a dashboard CSP for the no-build operator UI
- Added explicit `security` config controls for JSON body size, upload size, and bounded routing-header values
- Added functional API coverage for dashboard headers, JSON request limits, upload limits, and sanitized routing-header behavior

## v0.8.0 - 2026-03-15

### Added

- Added `faigate-onboarding-report` plus a testable onboarding report module for many-provider and many-client readiness checks
- Added `faigate-onboarding-validate` so onboarding blockers can fail fast in local setup and CI-style validation flows
- Added built-in OpenClaw, n8n, and CLI quickstart examples to the onboarding report and integration docs so client onboarding can stay copy/paste friendly
- Added staged provider-rollout reporting and fallback/image readiness warnings so many-provider onboarding is easier to phase safely
- Added a client matrix to the onboarding report so profile match rules and routing intent are visible before traffic goes live
- Added starter example files for OpenClaw, n8n, and CLI clients under `docs/examples/` so onboarding can begin from copy/pasteable templates
- Added starter provider snippets for cloud, local-worker, and image-provider setups under `docs/examples/`
- Added matching provider `.env` starter files for cloud, local-worker, and image-provider onboarding flows
- Added provider env placeholder checks to `faigate-doctor` so missing `.env` values are surfaced before rollout
- Added `--markdown` output to `faigate-onboarding-report` so onboarding state can be pasted into issues, PRs, or hand-off notes
- Added delegated OpenClaw request and generic AI-native app profile starters to round out the `v0.8.x` onboarding path

## v0.7.0 - 2026-03-12

### Added

- Added stronger update-alert metadata to `GET /api/update`, including update type, alert level, and recommended action for operators and dashboard consumers
- Added an opt-in `auto_update` policy block plus `faigate-auto-update` so controlled deployments can gate helper-driven updates without enabling silent self-updates
- Added `GET /api/operator-events` plus operator-event metrics for update checks and helper-driven auto-update attempts
- Added dashboard cards and tables for operator-side update checks and apply attempts
- Added provider-health rollout guardrails so helper-driven auto-updates can block when gateway health is already degraded
- Added `update_check.release_channel` and `auto_update.rollout_ring` so operators can distinguish stable vs preview checks and tighter rollout rings
- Added `auto_update.min_release_age_hours` so helper-driven auto-updates can wait for a release to age before becoming eligible
- Added `auto_update.maintenance_window` so helper-driven auto-updates can stay inside explicit local maintenance hours
- Added `auto_update.provider_scope` so rollout-health guardrails can evaluate only a selected provider subset
- Added `auto_update.verification` so helper-driven auto-updates can run a post-update check and emit a rollback hint on failure

## v0.6.0 - 2026-03-12

### Added

- Added modality-aware metrics and filters so stats, traces, recent requests, and the dashboard can distinguish `chat`, `image_generation`, and `image_editing`
- Added `POST /api/route/image` for dry-run preview of image-generation and image-editing routing decisions
- Added optional `image` provider metadata (`max_outputs`, `max_side_px`, `supported_sizes`) so image-capable providers can be ranked against `n` and `size`
- Added top-level capability coverage to `GET /health` plus `GET /api/providers` for filtered provider inventory and dashboard coverage views
- Added shared request validation for image-generation, image-editing, and image-route preview payloads so invalid `size`, `n`, and scalar fields fail fast before provider calls
- Added optional `image.policy_tags` plus request-side image-policy hints so image routing can prefer providers tagged for `quality`, `cost`, `balanced`, `batch`, or `editing`

## v0.5.0 - 2026-03-12

### Added

- Added `contract: image-provider` plus OpenAI-compatible `POST /v1/images/generations` and `POST /v1/images/edits` paths for image-capable providers
- Added a shipped Dockerfile and tag-driven release-artifacts workflow for Python distributions, GHCR images, and optional PyPI publishing
- Added public community-health and security baseline files: Code of Conduct, Security Policy, issue templates, PR template, Dependabot, and CodeQL
- Added generic onboarding helpers (`faigate-bootstrap`, `faigate-doctor`) and a publish-dry-run workflow for GHCR and Python package validation
- Added cached release update checks via `GET /api/update`, the dashboard, and `faigate-update-check`

## v0.4.0 - 2026-03-12

### Changed

- Added optional `request_hooks` with a small built-in hook registry for per-request provider preferences, locality hints, and profile overrides
- Added a dedicated routing layer for hook-provided hints before client-profile defaults
- Added dry-run route output for applied hooks, effective request metadata, and candidate ranking details
- Added provider route-fit metadata for `context_window`, token limits, and cache behavior
- Added filtered stats, recent-request, and trace queries for provider, client, layer, and success views
- Hardened the built-in dashboard with provider health, client breakdowns, route traces, URL-persisted filters, summary cards, and escaped rendering
- Deepened provider scoring so routing now considers health, latency, recent failures, cache alignment, and request headroom instead of only first-fit dimension checks
- Hardened request hooks with sanitized body updates and routing hints plus optional fail-closed behavior via `request_hooks.on_error`

## v0.3.0 - 2026-03-12

### Changed

- Rebranded the public documentation around the fusionAIze Gate product name
- Completed the technical rename from earlier runtime identifiers to `faigate`
- Added validated provider capability metadata with normalized local/cloud and streaming defaults
- Added an optional policy layer for capability-aware provider selection on `auto` requests
- Added an explicit `local-worker` provider contract for network-local OpenAI-compatible runtimes
- Added optional client profiles for caller-aware routing defaults based on request headers
- Added a dry-run route introspection endpoint at `POST /api/route`
- Added enriched route traces and client/profile breakdowns in metrics, stats, and CLI output
- Added startup and `/health` probing for `contract: local-worker` providers via `GET /models`
- Added built-in `client_profiles` presets for `openclaw`, `n8n`, and `cli`
- Added a repository `AGENTS.md` and a documented Git workflow for `main`, `feature/*`, `review/*`, and `hotfix/*`
- Aligned release guidance around semantic-style `x.y.z` versioning with `v0.3.0` as the first fusionAIze Gate-branded release

### Docs

- Reworked the README into a more generic, portable open-source landing page
- Added clearer API, configuration, deployment, and helper script documentation
- Added release process documentation, roadmap updates, and a lightweight release checklist template
- Added architecture, integrations, onboarding, and troubleshooting docs for external users
