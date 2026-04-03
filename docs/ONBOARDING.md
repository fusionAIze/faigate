# fusionAIze Gate Onboarding

## Goal

fusionAIze Gate should be understandable and usable for a deployment with many providers and many clients.

The safest onboarding order is:

1. one provider
2. one client
3. bootstrap + diagnostics
4. second provider
5. client-specific defaults
6. policy constraints

## Provider onboarding sequence

### 0. Bootstrap the local checkout

Run the generic helpers before changing config:

```bash
./scripts/faigate-menu
./scripts/faigate-bootstrap
./scripts/faigate-provider-setup
./scripts/faigate-doctor
./scripts/faigate-onboarding-report
```

If you prefer a guided shell flow over remembering individual helper names, start with `./scripts/faigate-menu`. It wraps the new performance dashboard, provider setup, the wizard, API-key editing, HTTP settings, routing-mode editing, client quickstarts, validation helpers, service control, and update checks behind one consistent control-center layout.

The `Configure` section now splits cleanly into:

- `Current Config`
- `Provider Setup`
- `Guided Setup`
- `Direct Settings`

That keeps the Gate-native flow closer to the later Grid orchestration pattern without hiding the low-level settings when you need them.

The main menu and the service/config submenus also show small runtime snapshots and inline tips now, so operators get a quick sense of the current bind, health, provider count, and default routing posture before choosing the next action. Once requests are flowing, the `Dashboard` section becomes the operator surface for traffic, latency, spend, token volume, provider/client hotspots, and routing pressure.

`Provider Setup` is the right first stop when the source itself is missing, not just the key:

- `Known Providers` for the curated source list
- `Custom Provider` for an OpenAI-compatible upstream not yet in the catalog
- `Local Worker` for LM Studio, Ollama-style bridges, or another local/LAN worker

After the sources exist, `Provider Probe` is now the compact operator check for:

- which configured providers really look ready right now
- which providers still only have config but no usable key
- whether `/health` already sees them as healthy
- common failure classes such as rate-limited, quota-exhausted, or model-unavailable

Then `Client Scenarios` gives named templates such as `opencode / eco` or `n8n / reliable`, so the next step feels like choosing an intended client posture instead of hand-editing profile modes.

`faigate-doctor` now also checks whether provider env placeholders referenced in `config.yaml` are actually present in `.env`.

`faigate-config-wizard` gives you a first pass at:

- detected provider blocks from the API keys already present in `.env`
- stock routing modes such as `auto`, `eco`, `premium`, and `free`
- model shortcuts
- client defaults for OpenClaw, n8n, CLI, and `opencode`
- purpose-/client-aware candidate lists you can multi-select instead of taking one hardcoded set
- conservative merges into an existing `config.yaml` for later provider additions

Useful flows:

```bash
./scripts/faigate-config-wizard --help
./scripts/faigate-config-wizard --purpose coding --client opencode --list-candidates
./scripts/faigate-config-wizard --current-config config.yaml --purpose coding --client opencode
./scripts/faigate-config-wizard --purpose coding --client opencode \
  --select deepseek-chat,deepseek-reasoner,anthropic-claude > config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --merge-existing \
  --select openrouter-fallback,kilocode --write config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --purpose coding --client opencode \
  --apply recommended_add,recommended_replace,recommended_mode_changes \
  --select kilocode,openrouter-fallback --select-profiles opencode --write config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --purpose coding --client opencode \
  --apply recommended_add,recommended_replace,recommended_mode_changes \
  --select kilocode,openrouter-fallback --select-profiles opencode --dry-run-summary
./scripts/faigate-config-wizard --current-config config.yaml --purpose coding --client opencode \
  --apply recommended_add,recommended_replace,recommended_mode_changes \
  --select kilocode,openrouter-fallback --select-profiles opencode \
  --write config.yaml --write-backup --backup-suffix .before-wizard
```

If you only need a compact refresher for the flags and example flows, `./scripts/faigate-config-wizard --help` now prints the whole first-setup / update / dry-run / backup path directly in the CLI.

When a current config is present, the suggestion output now also flags client-profile mode deltas such as `recommended_mode_changes`, so you can see when `n8n`, `openclaw`, or `opencode` probably want a different default mode for the selected purpose.

`faigate-onboarding-report` now includes concrete OpenClaw, n8n, and CLI quickstart hints plus a staged provider-rollout view. Use it after every provider or client change to keep the deployment understandable for the next operator as well.

It now also includes provider-catalog alerts for:

- configured models that drift away from the curated recommendation
- providers that are not tracked yet
- catalog entries that have gone stale and need review
- volatile free-/BYOK-/marketplace-backed offer tracks
- mixed/community-backed catalog entries that deserve faster review

The same catalog can now also carry optional provider-discovery links for CLI or later browser surfaces. Those links can be operator-configured through env vars, but they are deliberately downstream of the recommendation itself: ranking stays performance-led and link-neutral.

Today that means:

- `faigate-onboarding-report` can show the resolved provider discovery URL
- `faigate-doctor` can print the same disclosed link for configured providers
- `faigate-provider-discovery` can give one compact text or JSON view for later automation or browser work
- that discovery helper can now also filter by `offer_track`, `link_source`, or `disclosed_only`
- both surfaces also print the link-neutral policy state alongside the links

It also prints a client matrix:

- which client profiles exist
- whether they come from presets or custom config
- how they match traffic
- which routing hints they actually apply

If you want that client view without the full onboarding report, use:

```bash
./scripts/faigate-client-integrations
./scripts/faigate-client-integrations --matrix
./scripts/faigate-client-integrations --json --client n8n
./scripts/faigate-config-overview
```

### 1. Add one provider

- define the provider in `config.yaml`
- set the required API key or local auth value in `.env`
- keep the fallback chain simple

Starter snippets:

- [examples/provider-openai-compat.yaml](./examples/provider-openai-compat.yaml)
- [examples/provider-openai-compat.env.example](./examples/provider-openai-compat.env.example)
- [examples/provider-local-worker.yaml](./examples/provider-local-worker.yaml)
- [examples/provider-local-worker.env.example](./examples/provider-local-worker.env.example)
- [examples/provider-image-provider.yaml](./examples/provider-image-provider.yaml)
- [examples/provider-image-provider.env.example](./examples/provider-image-provider.env.example)
- [examples/provider-kilocode.yaml](./examples/provider-kilocode.yaml)
- [examples/provider-kilocode.env.example](./examples/provider-kilocode.env.example)
- [examples/provider-blackbox.yaml](./examples/provider-blackbox.yaml)
- [examples/provider-blackbox.env.example](./examples/provider-blackbox.env.example)
- [examples/faigate-multi-provider-stack.yaml](./examples/faigate-multi-provider-stack.yaml)

### 2. Verify provider health

- check `GET /health`
- check `GET /v1/models`
- for `contract: local-worker`, confirm that `GET /models` works on the worker
- for `contract: image-provider`, confirm that the upstream exposes `POST /images/generations`

### 3. Validate routing

- use `POST /api/route`
- confirm the selected provider and attempt order

### 4. Only then add another provider

Repeat the same path before introducing more routing complexity.

If you want a fuller multi-provider starting point instead of enabling one block at a time, use [examples/faigate-multi-provider-stack.yaml](./examples/faigate-multi-provider-stack.yaml) as a copy source and then trim it down to the providers that are actually available in your environment.

For many-provider rollouts, run the onboarding report after every provider change:

```bash
./scripts/faigate-onboarding-report
./scripts/faigate-onboarding-report --markdown
./scripts/faigate-onboarding-report --json
./scripts/faigate-onboarding-validate
```

The rollout section is intentionally staged:

1. stage 1 primary: ready local/default chat providers
2. stage 2 secondary: additional non-image providers
3. stage 3 modality: image-capable providers

This keeps provider growth incremental instead of introducing chat, fallback, and modality changes all at once.

## Client onboarding sequence

### 1. Keep the client on the common API

Prefer the standard OpenAI-compatible entry point.

### 2. Add a stable client tag

Examples:

- `x-openclaw-source`
- `X-faigate-Client: n8n`
- `X-faigate-Client: codex`

Keep these tags short and stable. The runtime now bounds routing-header values before they reach traces, client matrices, and rollout decisions.

### 3. Apply a preset or custom profile

Start with:

- `openclaw`
- `n8n`
- `cli`

Then tighten it only if the default is not good enough.

When the client set grows, use the client matrix from `faigate-onboarding-report` to catch profiles that only work through explicit overrides and still have no real match rule.

### 3a. Start from one of the built-in quickstarts

OpenClaw:

```json
{
  "baseUrl": "http://127.0.0.1:8090/v1",
  "primary": "faigate/auto"
}
```

Starter file: [examples/openclaw-faigate.jsonc](./examples/openclaw-faigate.jsonc)

Fuller deployment example: [examples/openclaw-faigate-full.jsonc](./examples/openclaw-faigate-full.jsonc)
Full reference block: [../openclaw-integration.jsonc](../openclaw-integration.jsonc)

Important:

- the model ids under `providers.faigate.models` must match `GET /v1/models`
- use `imageModel.primary: "faigate/auto"` if fusionAIze Gate should pick the image backend
- use `imageModel.primary: "faigate/<provider-id>"` only when the image path should be pinned

Delegated / many-agent example:

- [examples/openclaw-delegated-request.json](./examples/openclaw-delegated-request.json)

n8n:

```text
Base URL: http://127.0.0.1:8090/v1
Model: auto
Header: X-faigate-Client: n8n
```

CLI:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8090/v1
export OPENAI_API_KEY=local
```

Starter files:

- [examples/n8n-faigate-http-request.json](./examples/n8n-faigate-http-request.json)
- [examples/cli-faigate-env.sh](./examples/cli-faigate-env.sh)
- [examples/opencode-faigate.json](./examples/opencode-faigate.json)
- [examples/client-ai-native-app-profile.yaml](./examples/client-ai-native-app-profile.yaml)
- [examples/swe-af-faigate.env.example](./examples/swe-af-faigate.env.example)
- [examples/paperclip-faigate.env.example](./examples/paperclip-faigate.env.example)
- [examples/ship-faster-faigate.env.example](./examples/ship-faster-faigate.env.example)
- [examples/langchain-faigate.env.example](./examples/langchain-faigate.env.example)
- [examples/langgraph-faigate.env.example](./examples/langgraph-faigate.env.example)
- [examples/agno-faigate.env.example](./examples/agno-faigate.env.example)
- [examples/semantic-kernel-faigate.env.example](./examples/semantic-kernel-faigate.env.example)
- [examples/haystack-faigate.env.example](./examples/haystack-faigate.env.example)
- [examples/mastra-faigate.env.example](./examples/mastra-faigate.env.example)
- [examples/google-adk-faigate.env.example](./examples/google-adk-faigate.env.example)
- [examples/autogen-faigate.env.example](./examples/autogen-faigate.env.example)
- [examples/llamaindex-faigate.env.example](./examples/llamaindex-faigate.env.example)
- [examples/crewai-faigate.env.example](./examples/crewai-faigate.env.example)
- [examples/pydanticai-faigate.env.example](./examples/pydanticai-faigate.env.example)
- [examples/camel-faigate.env.example](./examples/camel-faigate.env.example)

### 3b. First-wave framework starters

The first post-`1.0` framework wave keeps every client on the same OpenAI-compatible entry point and varies only the stable client tag:

- `SWE-AF` -> `X-faigate-Client: swe-af`
- `paperclip` -> `X-faigate-Client: paperclip`
- `ship-faster` -> `X-faigate-Client: ship-faster`
- `LangChain` -> `X-faigate-Client: langchain`
- `LangGraph` -> `X-faigate-Client: langgraph`

Use the starter env files above first, then add explicit profile rules only if one framework needs different locality, provider, or cost behavior.

### 3c. Second-wave framework starters

The second post-`1.0` starter wave extends the same pattern to:

- `Agno` -> `X-faigate-Client: agno`
- `Semantic Kernel` -> `X-faigate-Client: semantic-kernel`
- `Haystack` -> `X-faigate-Client: haystack`
- `Mastra` -> `X-faigate-Client: mastra`
- `Google ADK` -> `X-faigate-Client: google-adk`

Keep these on the shared OpenAI-compatible path first. The right time to split them into more specialized profiles is after traces and stats show a real difference in locality, fallback, or cost behavior.

### 3d. Third-wave framework starters

The third post-`1.0` starter wave closes the biggest remaining framework gaps from the matrix:

- `AutoGen` -> `X-faigate-Client: autogen`
- `LlamaIndex` -> `X-faigate-Client: llamaindex`
- `CrewAI` -> `X-faigate-Client: crewai`
- `PydanticAI` -> `X-faigate-Client: pydanticai`
- `CAMEL` -> `X-faigate-Client: camel`

Treat these the same way as the earlier waves: stay on the shared OpenAI-compatible endpoint first, then split profiles only when traces and route previews show a real need.

### 4. Add request hooks only if needed

Keep hooks opt-in and narrow. Good uses are:

- `X-faigate-Prefer-Provider` for one explicit provider preference
- `X-faigate-Locality: local-only` for private or worker-local traffic
- `X-faigate-Profile` for a one-request profile override

### 5. Validate with route introspection

Use:

- `POST /api/route`
- `POST /api/route/image`
- `GET /api/traces`

## Many providers, many clients

When the stack grows, avoid changing everything at once.

Recommended rollout:

1. stabilize the provider set
2. group clients into a small number of profiles
3. introduce policies only for real constraints
4. keep route debugging enabled through traces and stats

## CLI Intelligence & Dashboard Integration (v2.0.0+)

fusionAIze Gate v2.0.0 brings deeper shell parity between the CLI and dashboard. Key enhancements:

### Dashboard Deep‑Links

All `faigate-stats` commands now generate matching dashboard URLs:

```bash
# Generate URL for current view/filters
faigate-stats --link --view routes --provider deepseek-chat
# Copy to clipboard
faigate-stats --link --view routes --provider deepseek-chat --copy
```

Filters work across all CLI commands:
- `--provider` – filter by provider id
- `--modality` – filter by modality (`chat`, `image`, `code`)
- `--client-profile` – filter by client profile (`opencode`, `n8n`, `openclaw`)
- `--layer` – filter by routing layer (`policy`, `profile`, `static`, `heuristic`)

### Intelligent Suggestions

The CLI can analyze metrics and suggest relevant commands:

```bash
# Get command suggestions based on failure rates, provider concentration, costs, recent activity
faigate-stats --suggest
```

### Safe Config Management

New `faigate-config` CLI provides safe config workflows:

```bash
# Preview config changes
faigate-config preview --provider xai --provider zai
# Show detailed diff
faigate-config diff config.yaml config.new.yaml
# Apply with backup and confirmation
faigate-config apply config.new.yaml --backup --confirm
# Validate syntax
faigate-config validate config.yaml
```

### Local Worker Auto‑Discovery

Automatically detect local AI workers:

```bash
# Scan for Ollama, vLLM, LM Studio, LiteLLM
faigate-config discover
# JSON output for automation
faigate-config discover --json
```

For each detected worker, the command suggests a ready‑to‑copy provider block for `config.yaml`.

### Complete Provider Coverage

The provider catalog now includes **43 curated entries** covering all LLM AI Router custom endpoints:

- **xAI / Grok**, **Z.AI / GLM**, **Mistral**, **Groq**, **HuggingFace Inference**
- **Moonshot AI / Kimi**, **MiniMax**, **Volcano Engine / Doubao**, **BytePlus**
- **Qwen**, **OpenAI Codex**, **OpenCode Zen**, **Cerebras**, **GitHub Copilot**
- **Synthetic**, **Kimi Coding**, **Vercel AI Gateway**
- **KiloCode model‑level lanes**: `kilo‑auto/frontier`, `/balanced`, `/free`

View the full catalog:

```bash
faigate-stats --link --view catalog
```

## Update operations

Current state:

- manual updates via Git or `faigate-update`
- cached release update checks via `GET /api/update` and `faigate-update-check`
- optional eligibility reporting and helper-driven apply flow via `faigate-auto-update`
- tag-driven release artifacts for Python distributions and container images
- publish dry-run workflow for Python packaging and GHCR container builds

Planned state:

- scheduled use of `faigate-auto-update --apply` in controlled environments

This remains opt-in. fusionAIze Gate does not self-schedule or mutate the checkout over HTTP.

### Controlled scheduling examples

Use scheduling only after you are comfortable with the manual path:

```bash
./scripts/faigate-update-check
./scripts/faigate-auto-update
```

Recommended `systemd` path:

1. review [examples/faigate-auto-update.service](./examples/faigate-auto-update.service)
2. review [examples/faigate-auto-update.timer](./examples/faigate-auto-update.timer)
3. install them under `/etc/systemd/system/`
4. enable the timer only after `auto_update.enabled: true` is set deliberately

Minimal flow:

```bash
sudo install -m 644 docs/examples/faigate-auto-update.service /etc/systemd/system/faigate-auto-update.service
sudo install -m 644 docs/examples/faigate-auto-update.timer /etc/systemd/system/faigate-auto-update.timer
sudo systemctl daemon-reload
sudo systemctl enable --now faigate-auto-update.timer
sudo systemctl list-timers faigate-auto-update.timer
```

Cron remains possible for simpler hosts. The example is in [examples/faigate-auto-update.cron](./examples/faigate-auto-update.cron), but `systemd` timers are usually the safer default because they provide visibility and persistence.
