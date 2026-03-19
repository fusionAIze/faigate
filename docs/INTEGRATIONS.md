# fusionAIze Gate Integrations

## Current integration model

fusionAIze Gate works best when clients use the same OpenAI-compatible base URL and let the gateway handle routing and failover.

That keeps integrations shallow and makes routing policy reusable across tools.

## OpenClaw

OpenClaw is a first-class target for fusionAIze Gate.

Current coverage:

- one-agent traffic through the normal OpenAI-compatible endpoint
- many-agent or delegated traffic when `x-openclaw-source` is present
- direct model aliases via the OpenClaw-side config
- caller-aware defaults through the `openclaw` client preset or explicit profile rules
- image generation and image editing through the same fusionAIze Gate provider entry

Use:

- [openclaw-integration.jsonc](../openclaw-integration.jsonc)
- [examples/openclaw-faigate.jsonc](./examples/openclaw-faigate.jsonc)
- [examples/openclaw-faigate-full.jsonc](./examples/openclaw-faigate-full.jsonc)
- `client_profiles.presets: ["openclaw"]` for a standard starting point

Important rule:

- the model ids under `models.providers.faigate.models` in OpenClaw must match the provider ids returned by `GET /v1/models` from fusionAIze Gate
- that means OpenClaw should use ids such as `auto`, `deepseek-chat`, `local-worker`, or `image-provider`
- it should not guess raw upstream ids unless fusionAIze Gate itself exposes those exact provider ids

Minimal direction:

```json
{
  "baseUrl": "http://127.0.0.1:8090/v1",
  "primary": "faigate/auto"
}
```

For a smaller starter snippet without the full alias block, use [examples/openclaw-faigate.jsonc](./examples/openclaw-faigate.jsonc).

Recommended OpenClaw defaults:

- `model.primary: "faigate/auto"`
- `imageModel.primary: "faigate/auto"` when fusionAIze Gate should choose among image-capable providers
- `subagents.model: "faigate/auto"` when delegated traffic should stay inside the same routing plane

Use an explicit image provider only when OpenClaw should pin image traffic:

```json
{
  "imageModel": {
    "primary": "faigate/image-provider",
    "fallbacks": []
  }
}
```

fusionAIze Gate-side config that helps OpenClaw most:

- readable, stable provider ids because those become OpenClaw model ids
- `client_profiles.presets: ["openclaw"]`
- `contract: local-worker` for local LLM workers
- `contract: image-provider` for image-capable backends
- `capabilities.image_editing: true` only when edits really work upstream
- `image.policy_tags`, `supported_sizes`, and `max_outputs` for stronger image routing

For delegated or many-agent traffic, start from [examples/openclaw-delegated-request.json](./examples/openclaw-delegated-request.json) and keep `x-openclaw-source` stable across sub-agents so traces stay attributable.

Keep delegated/client headers short and stable. The runtime now bounds routing-header values before they reach traces, metrics, and rollout logic.

Validate OpenClaw wiring in this order:

1. `GET /v1/models` to confirm the provider ids OpenClaw should reference
2. `POST /api/route` for chat routing previews
3. `POST /api/route/image` for image routing previews
4. only then send real `POST /v1/chat/completions`, `POST /v1/images/generations`, or `POST /v1/images/edits` traffic

## n8n

n8n can use fusionAIze Gate as a stable local model gateway.

Recommended pattern:

- send requests to the OpenAI-compatible endpoint
- set `X-faigate-Client: n8n`
- enable the `n8n` client preset or an explicit `n8n` profile
- optionally enable `request_hooks` if a workflow should prefer one provider or stay local-only

This gives you:

- cheaper default routing for workflow traffic
- shared fallback behavior
- route debugging through `POST /api/route`

Minimal direction:

```text
Base URL: http://127.0.0.1:8090/v1
Model: auto
Header: X-faigate-Client: n8n
```

For an importable HTTP Request node example, use [examples/n8n-faigate-http-request.json](./examples/n8n-faigate-http-request.json).

## CLI clients

CLI tools should also use the same local gateway where possible.

Examples:

- Codex CLI
- Claude Code wrappers
- KiloCode CLI
- future DeepSeek-oriented wrappers

Recommended pattern:

- point the client to fusionAIze Gate
- set `X-faigate-Client: codex`, `claude`, `kilocode`, or another stable client tag
- use the built-in `cli` preset or a tighter custom profile
- optionally enable request hooks for per-request locality or provider hints:
  - `X-faigate-Prefer-Provider`
  - `X-faigate-Locality`
  - `X-faigate-Profile`

Minimal direction:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8090/v1
export OPENAI_API_KEY=local
```

For a reusable shell starter, use [examples/cli-faigate-env.sh](./examples/cli-faigate-env.sh).

As with other clients, prefer token-like client tags over long free-form values so the bounded header surface remains readable in traces and operator views.

If you want a small Node-facing helper instead of shell aliases, the separate npm package lives in [packages/faigate-cli](../packages/faigate-cli).

### opencode

`opencode` can use fusionAIze Gate as a custom OpenAI-compatible provider through its `provider` config.

- starter: [examples/opencode-faigate.json](./examples/opencode-faigate.json)
- recommended header: `X-faigate-Client: opencode`
- recommended model: pick one of the fusionAIze Gate model ids exposed by `GET /v1/models`, usually `auto`

The current opencode docs recommend `@ai-sdk/openai-compatible` for custom OpenAI-compatible providers and a custom `provider.<id>.options.baseURL` value for the gateway endpoint. This fusionAIze Gate starter follows that pattern and keeps the provider-local model ids aligned with `GET /v1/models`.

## AI-native app clients

For future app-specific clients, keep the same OpenAI-compatible base URL and add one stable app header before creating multiple custom profiles.

Recommended pattern:

- set `X-faigate-Client: your-app`
- create one explicit app profile
- only split into `ops`, `private`, or `local-only` profiles when real routing differences emerge

Starter snippet:

- [examples/client-ai-native-app-profile.yaml](./examples/client-ai-native-app-profile.yaml)

## First-wave agent and framework starters

The first post-`1.0` expansion wave focuses on clients that can already use fusionAIze Gate cleanly through the common OpenAI-compatible path.

### SWE-AF

- starter: [examples/swe-af-faigate.env.example](./examples/swe-af-faigate.env.example)
- recommended header: `X-faigate-Client: swe-af`
- recommended profile name: `swe-af`

### paperclip

- starter: [examples/paperclip-faigate.env.example](./examples/paperclip-faigate.env.example)
- recommended header: `X-faigate-Client: paperclip`
- recommended profile name: `paperclip`

### ship-faster

- starter: [examples/ship-faster-faigate.env.example](./examples/ship-faster-faigate.env.example)
- recommended header: `X-faigate-Client: ship-faster`
- recommended profile name: `ship-faster`

### LangChain

- starter: [examples/langchain-faigate.env.example](./examples/langchain-faigate.env.example)
- recommended header: `X-faigate-Client: langchain`
- recommended profile name: `langchain`

### LangGraph

- starter: [examples/langgraph-faigate.env.example](./examples/langgraph-faigate.env.example)
- recommended header: `X-faigate-Client: langgraph`
- recommended profile name: `langgraph`

These starters are intentionally small:

- keep one local OpenAI-compatible base URL
- keep one stable client tag
- use client profiles only when the framework traffic really needs distinct routing behavior
- validate with `POST /api/route` and `GET /api/traces` before adding policies or hooks

## Second-wave framework starters

The second wave keeps the same integration discipline while extending fusionAIze Gate coverage into more active agent ecosystems.

### Agno

- starter: [examples/agno-faigate.env.example](./examples/agno-faigate.env.example)
- recommended header: `X-faigate-Client: agno`
- recommended profile name: `agno`

### Semantic Kernel

- starter: [examples/semantic-kernel-faigate.env.example](./examples/semantic-kernel-faigate.env.example)
- recommended header: `X-faigate-Client: semantic-kernel`
- recommended profile name: `semantic-kernel`

### Haystack

- starter: [examples/haystack-faigate.env.example](./examples/haystack-faigate.env.example)
- recommended header: `X-faigate-Client: haystack`
- recommended profile name: `haystack`

### Mastra

- starter: [examples/mastra-faigate.env.example](./examples/mastra-faigate.env.example)
- recommended header: `X-faigate-Client: mastra`
- recommended profile name: `mastra`

### Google ADK

- starter: [examples/google-adk-faigate.env.example](./examples/google-adk-faigate.env.example)
- recommended header: `X-faigate-Client: google-adk`
- recommended profile name: `google-adk`

## Third-wave framework starters

The third wave rounds out the most visible remaining framework set from the AI-native matrix.

### AutoGen

- starter: [examples/autogen-faigate.env.example](./examples/autogen-faigate.env.example)
- recommended header: `X-faigate-Client: autogen`
- recommended profile name: `autogen`

### LlamaIndex

- starter: [examples/llamaindex-faigate.env.example](./examples/llamaindex-faigate.env.example)
- recommended header: `X-faigate-Client: llamaindex`
- recommended profile name: `llamaindex`

### CrewAI

- starter: [examples/crewai-faigate.env.example](./examples/crewai-faigate.env.example)
- recommended header: `X-faigate-Client: crewai`
- recommended profile name: `crewai`

### PydanticAI

- starter: [examples/pydanticai-faigate.env.example](./examples/pydanticai-faigate.env.example)
- recommended header: `X-faigate-Client: pydanticai`
- recommended profile name: `pydanticai`

### CAMEL

- starter: [examples/camel-faigate.env.example](./examples/camel-faigate.env.example)
- recommended header: `X-faigate-Client: camel`
- recommended profile name: `camel`

## Provider onboarding

When onboarding a new provider:

1. define the provider stanza in `config.yaml`
2. declare the right contract and capabilities
3. verify health and `/v1/models`
4. test routing with `POST /api/route`
5. then route real traffic

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

## Client onboarding

When onboarding a new client:

1. keep the client on the OpenAI-compatible API if possible
2. assign a stable client tag or header
3. start with a built-in preset or a minimal custom profile
4. add request hooks only if the client needs per-request overrides
5. use `/api/route` and `/api/traces` to validate behavior
6. only add a dedicated adapter if the client cannot cleanly use the common API surface

## Integration extensions

These are the main extension seams beyond the common client starters:

- image generation and image editing through `POST /v1/images/generations` and `POST /v1/images/edits` for providers that declare `contract: image-provider`
- optional request hooks for context or optimization
- richer CLI-sidecar adapters
- provider and client onboarding helpers
