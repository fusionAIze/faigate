# AGENTS.md — fusionAIze Gate

## Project identity

This repository hosts `fusionAIze Gate`, a public Apache-2.0-licensed local-first AI gateway.

fusionAIze Gate provides:

1. one OpenAI-compatible local endpoint,
2. routing across multiple upstream providers,
3. fallback and health-aware request handling,
4. a path toward local workers, client profiles, and optional context or optimization hooks.

## Naming status

The product, runtime, and GitHub repository use `fusionAIze Gate` identifiers.

## Product priority

The gateway is the product.

Do not turn this repository into a monolithic agent framework, workflow engine, or memory platform.

Prioritize:

- reliable request routing,
- clear provider contracts,
- policy-driven behavior,
- local and cloud portability,
- operational visibility,
- clean integration points for higher-level tools.

## Architecture principles

Use a pragmatic gateway-first architecture:

- small gateway core,
- clear provider boundaries,
- client adapters instead of one-off integrations,
- optional extensions for context, memory, or optimization,
- operational simplicity over platform sprawl.

Prefer standard API surfaces first.
If a tool can speak an OpenAI-compatible endpoint cleanly, use that before adding a custom adapter.

## Supported interaction surfaces

fusionAIze Gate should support these surfaces over time:

### Current

- OpenAI-compatible HTTP clients
- OpenClaw
- local operators using helper scripts and systemd

### Near term

- n8n and automation clients
- local or network-local model workers
- CLI-oriented adapters or proxy wrappers

### Later

- optional dashboards or admin surfaces
- optional context, memory, and optimization hooks

## Implementation rules

Implement now:

- routing reliability,
- provider capability metadata,
- policy-based routing,
- local worker support,
- client profile support,
- observability improvements,
- release and process documentation.

Defer or keep optional:

- heavy UI surfaces,
- hard-coupled memory systems,
- mandatory token optimization in the core request path,
- tool-specific integrations when a standard API already works.

## Code quality rules

- keep modules small and testable
- prefer explicit contracts over implicit behavior
- avoid hidden routing magic
- keep operational failure modes visible in logs and health output
- preserve backwards compatibility where it is intentionally promised

## Workflow rules

Work in small coherent steps.
Prefer commit-sized implementation blocks.
Stop after each major block and summarize what changed, what remains, and what is intentionally deferred.

After every 4 or 5 merged PRs, do a full review pass that includes:

- unit test coverage review
- integration test coverage review
- functional test review against real workflows where possible
- documentation review and update across every relevant Markdown file
- roadmap and process review if the project direction changed
- community-health and security baseline review (`CODE_OF_CONDUCT.md`, `SECURITY.md`, issue templates, PR template, Dependabot, CodeQL)

Follow the branch workflow defined in:

- `docs/process/git-workflow.md`

Default branch model:

- `main`
- `feature/<topic>-<date>`
- `review/<topic>-<date>`
- `hotfix/<topic>-<date>` when production-oriented urgency justifies it

Do not introduce a long-lived `develop` branch unless the repository truly needs one.

## RTK shell command preference

For Codex and other shell-driven agents without stronger native command hooks, prefer RTK-wrapped shell commands whenever applicable.

Use raw commands only when RTK is not available or not a good fit, and state that briefly.

## Documentation rules

Maintain:

- the README as the primary public landing page,
- roadmap documentation,
- architecture, integration, onboarding, and troubleshooting docs for external users,
- release and changelog documentation,
- process documentation for workflow-critical conventions,
- migration notes when external names and runtime names differ.

Do not document features that do not exist.

## Security rules

- never hardcode secrets
- never commit `.env`, keys, databases, sqlite files, or logs
- keep runtime state outside the repo checkout
- treat repo-safety rules as mandatory guardrails, not optional hygiene

## Release rules

- `main` should remain stable and releaseable
- document user-visible changes in `CHANGELOG.md`
- use lightweight semantic versioning in `x.y.z` form
- prefer minor bumps for meaningful features or operational behavior changes
- prefer patch bumps for fixes, polish, and small compatibility updates
- reserve major bumps for explicit breaking changes and documented migrations

## Content boundary

Release notes, changelogs, PR descriptions, and commit messages **must
not** reference non-faigate topics — personal tooling, local setup
details, operator-machine specifics, or unrelated projects. The
prerelease workflow (`.github/workflows/prerelease.yml`) filters these
automatically using `.github/scripts/filter-changelog.py`, but agents
and humans should keep the source clean so the filter is a safety net,
not a load-bearing rewrite step.

Concrete examples that don't belong in faigate-public surfaces:

- personal memory or env-management tools running on the operator's box
- absolute paths under `/Users/<name>/`, `~/Library/`, `~/Documents/`
- operator-specific machine setup steps unrelated to faigate runtime

When such context is genuinely relevant to a change, keep it in the PR
conversation or in `docs/process/` — never in user-visible commit
messages, release titles, or `CHANGELOG.md` entries.

## Where to work — Forgejo-first

- **Canonical origin:** `git.langevc.com/fusionaize/faigate` (Forgejo). **Do not push to GitHub** — it is a read-only mirror.
- **Local clone:** `~/Documents/repositories/forgejo/fusionaize/faigate`.
- **Remotes:** `origin` = Forgejo (canonical), `github` = GitHub mirror (read-only).
- **Pull requests:** open on Forgejo (`git.langevc.com/fusionaize/faigate/pulls`).
- **CI:** GitHub Actions workflows are guarded with `if: ${{ github.server_url == 'https://github.com' }}` so Forgejo skips them and the GitHub mirror runs them. `.forgejo/workflows/mirror.yml` (Forgejo-only) force-pushes every branch + tag back to GitHub.
