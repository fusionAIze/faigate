# Catalog Updater

faigate keeps its provider catalog (pricing, model aliases, capabilities,
freshness flags) in a separate metadata repo so we can ship updated pricing
and new models without cutting a faigate release.

This document describes how the catalog is generated from multiple sources,
how it syncs at runtime, the env vars and auth that control delivery, the CLI
commands that drive it, and how to debug it when it misbehaves.

## Catalog sources and precedence

The provider catalog is not hand-written. It is scraped from two foreign
sources and merged with an operator overlay by a fixed precedence rule:

| Source | Kind | What it contributes |
|--------|------|---------------------|
| overlay | operator-curated (private) | corrections that always beat foreign data |
| LiteLLM | foreign registry (`model_prices_and_context_window.json`) | prices, context windows, modalities, tier status for 300+ models |
| OmniRoute | foreign TypeScript configs (`open-sse/config/*.ts`) | provider/model catalog, free-tier budgets |

Precedence is fixed and highest first:

```
overlay  >  litellm  >  omniroute
```

When sources disagree about a model field, the higher-precedence source wins
and every conflict is recorded — field, both values, and the winning source —
so the choice stays auditable. A curated free price of `0.0` is a present
value, not "no data": it wins over a foreign non-zero price and logs a
conflict. The scrape runs as a weekly CI pipeline that opens a pull request
against the public repo; it never pushes to `main` directly.

## What lives where

| Repo | Visibility | Holds |
|------|------------|-------|
| [fusionaize-metadata-public](https://github.com/fusionAIze/fusionaize-metadata-public) | public | `providers/`, `models/`, `offerings/`, schemas |
| `fusionaize-metadata` (private) | private | `products/gate/overlays.v1.json`, `packages/` |
| `faigate/assets/metadata/catalog.v1.json` | bundled in wheel | snapshot used as last-resort fallback |

## Resolution chain

When a faigate process needs the provider catalog, the resolver walks three
tiers in order and uses the first one that returns valid data:

```
1. Private remote   (only if FAIGATE_METADATA_TOKEN is set)
2. Public  remote   (anonymous)
3. Bundled snapshot (shipped in the wheel)
```

A local checkout may short-circuit the chain entirely: if
`FAIGATE_PROVIDER_METADATA_FILE` or a populated `FAIGATE_PROVIDER_METADATA_DIR`
yields a catalog on disk, that file is loaded directly and the remote tiers
are never consulted. Otherwise the resolver falls through the three tiers.

Each remote tier caches its result at `~/.cache/faigate/metadata/{tier}/`
with a sibling `.etag` file; subsequent calls within the refresh interval
skip the network entirely. When TTL expires, the resolver sends an
`If-None-Match` request — a 304 response touches the cache and reuses the
existing payload at zero bandwidth.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FAIGATE_METADATA_TOKEN` | unset | GitHub fine-grained PAT (read-only on `fusionAIze/fusionaize-metadata`). Required for the private tier. |
| `FAIGATE_METADATA_PUBLIC_URL` | raw.githubusercontent.com path | Override the public catalog URL (e.g. for staging). |
| `FAIGATE_METADATA_PRIVATE_URL` | raw.githubusercontent.com path | Override the private catalog URL. |
| `FAIGATE_METADATA_REFRESH_INTERVAL_SECONDS` | `86400` (24h) | TTL for the cache before the next conditional GET. |
| `FAIGATE_PROVIDER_METADATA_FILE` | unset | Force-load a specific local catalog file. Bypasses sync. |
| `FAIGATE_PROVIDER_METADATA_DIR` | unset | Local checkout of the private repo (overlays, packages). |

## Auth setup (private tier)

For Pro / internal use only. OSS users do not need a token.

1. Visit <https://github.com/settings/tokens?type=beta>.
2. Generate a new **fine-grained personal access token**.
3. Resource owner: **fusionAIze**.
4. Repository access: **Only select repositories** → `fusionaize-metadata`.
5. Permissions → **Contents: Read** (no write, no metadata).
6. Copy the token (`github_pat_…`) and store it in your env manager:

   ```bash
   envctl set faigate FAIGATE_METADATA_TOKEN=github_pat_...
   ```

The token is sent only to `raw.githubusercontent.com` and is never logged.

## CLI commands

### `faigate-models status`

Print the cache state across all tiers. Useful as a quick health check.

```text
$ faigate-models status
Catalog cache status
----------------------------------------
  private   age=2.1h  providers=42  etag="W/\"3a7f\""
  public    age=2.1h  providers=41  etag="W/\"de91\""
  bundled   present=yes  providers=41
```

`--json` emits the same data as a JSON object for scripts.

### `faigate-models update`

Force-refresh the cache from remote.

```text
$ faigate-models update
updated: source=public providers=41
  etag: W/"de91"
```

Flags:

* `--check` — exit code-only health probe; **no network**. Returns 0 when a
  cached payload is younger than the refresh interval, 1 otherwise.
* `--diff` — after refresh, print added/removed/changed providers vs the
  previous cache.

### Programmatic access

```python
from faigate.catalog_resolver import CatalogResolver

resolver = CatalogResolver()
resolved = resolver.resolve()
print(resolved.source, len(resolved.payload["providers"]))
# "public", 41
```

## Daemon-tick refresh

The gateway starts a background metadata refresh task when `metadata.enabled`
is true and `metadata.refresh_interval_hours` is greater than zero. The
default interval is 24h. Set the interval to `0` to disable the daemon tick
and rely on lazy cache resolution plus manual `faigate-models update`.

```yaml
metadata:
  enabled: true
  refresh_interval_hours: 24
  timeout_seconds: 10
```

Scheduled failures do not crash the gateway. The loop backs off through 5m,
15m, and 1h retry delays, then returns to the configured interval after a
successful refresh.

## Sync alerts

Sync state is written next to the two remote tiers — `private` and
`public` — and surfaced through the existing catalog alert pipeline. The
`bundled` tier has no sync state: it exposes only `bundled_present` and
`bundled_providers_count` in `status()`, and never appears in the
`status()["tiers"]` dict that feeds `build_catalog_alerts`.

- `sync-stale` — last successful sync is older than 7 days, or no sync has
  ever succeeded.
- `sync-invalid` — remote JSON parsed but failed catalog validation.
- `sync-auth` — the `private` tier returned 401/403.

`faigate-models status` reports each remote tier's cache age, ETag, and
provider count (and bundled presence/count) so a dead delivery path is
visible instead of silently falling back. The last sync result is not part of
the default output; it is available only via `faigate-models status --json`,
and only when a sync-state file exists for that tier. The alerts appear in
`/api/provider-catalog`, dashboard summaries, and any surface already
consuming `build_catalog_alerts`.

## Troubleshooting

### `faigate-models status` shows `bundled  present=no`

The wheel was built without `assets/metadata/catalog.v1.json`. Either run
`scripts/refresh-bundled-catalog` and rebuild, or add the file manually
before installing. The runtime resolver still works against remote tiers
in this state, but offline boots have no fallback.

### Private tier always falls through to public

The private tier serves overlays and packages, not the provider catalog, so
falling through to the public tier for catalog data is expected for most
operators. When you expect the private tier to win, verify the token and
scope: a 401/403 means the token is wrong or lacks access to the private
repo, and a 404 means the private URL no longer points at live content.
Check which tier `faigate-models status` reports as the active source.

### Cache won't update

Inspect `~/.cache/faigate/metadata/`:

```bash
ls -la ~/.cache/faigate/metadata/public/
cat ~/.cache/faigate/metadata/public/catalog.v1.json.etag
```

Force-clear and re-fetch:

```bash
rm -rf ~/.cache/faigate/metadata/
faigate-models update
```

### Schema validation fails on remote

The resolver checks that `schema_version` starts with
`fusionaize-provider-catalog/` and that `providers` is a JSON object. If
the remote returns something else (e.g. a GitHub HTML 5xx page), the
resolver logs an `INVALID` status and keeps the prior cache. Surface the
issue with:

```bash
curl -sSf https://raw.githubusercontent.com/fusionAIze/fusionaize-metadata-public/main/providers/catalog.v1.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['schema_version'])"
```

### Logs show a redacted token

Expected. The redacted form (`ghp_…1234`) is a debugging aid; the
secrets-not-logged invariant is enforced by `tests/test_metadata_catalog_sync.py::test_fetch_does_not_log_token_value`.

## Refreshing the bundled snapshot

Run before a release to ensure new wheels ship with current catalog data:

```bash
./scripts/refresh-bundled-catalog
git add faigate/assets/metadata/catalog.v1.json
git commit -m "chore(catalog): refresh bundled snapshot for vX.Y.Z"
```

The script downloads the current public catalog, validates structure, and
swaps the snapshot file in place atomically.

## The model-knowledge cut: what lives where

faigate holds model knowledge in two regimes that once contradicted each other
silently: a catalog that updates without a release, and hardcoded Python
tables that need a release. The "cut" splits every model fact into one of four
bands, each with a single home. The split is by *kind of knowledge*, not by
source, and each band has a different authority and blast radius.

| Band | Kind | Home |
|------|------|------|
| **Facts** | capabilities, prices, modalities, aliases, versions, lifecycle | public catalog |
| **Assessment** | `quality_tier`, `reasoning_strength`, `cluster`, `degrade_to` | private overlay |
| **Wiring** | transport, auth, probe strategy | private overlay |
| **Policy** | scoring, fallback order | stays in code |

**Facts** are third-party verifiable and therefore public. Concrete example:
the per-model input caps are evidence-tagged facts resolved through
`faigate/provider_catalog.py:1420` (`get_model_input_cap_fact`), which returns
`None` for any id outside the curated set rather than the provider-wide
`262144` floor (`faigate/provider_catalog.py:416` has the placeholder value).

**Assessment** is the operator's own judgement (which model is "quality",
which one it degrades to) and carries the IP line decided 2026-04-26; it must
not ship public.

**Wiring** is operationally verifiable but a wiring error in *data* is harder to
localise than in code, so it migrates only under a stricter gate.

**Policy** — scoring and fallback order — is a program. It loses type checking
and testability the moment it moves into data, so it stays code
(`faigate/router.py` scoring; `faigate/main.py` fallback chain).

### Evidence rule

Every fact carries an `evidence` block by schema. The level follows a three-step
scale with distinct consequences:

| Level | Feeds | May do |
|-------|-------|--------|
| `belegt` | enforceable + advisory | carry hard decisions (router, capacity calc, error output) |
| `plausibel` | advisory only | best-effort routing, flagged to the client as an estimate |
| `unbestaetigt` | neither | nothing — invisible to router, capacity, error output |

The split is implemented in `faigate/catalog_views.py:86`
(`split_catalog_facts`); the level names are fixed at
`faigate/catalog_views.py:45-47`. The 413 path applies the rule through
`faigate/main.py:338` (`_resolve_advertised_input_limit`): a `belegt` cap is
advertised unchanged, a `plausibel` cap is marked `estimated: true`, and a
missing/unverified cap never invents a number — it passes through to the
provider or reports the operator byte limit, per `FAIGATE_UNVERIFIED_CAP_MODE`
(`faigate/main.py:372`). Machine-generated facts land as `unbestaetigt`; the
single human step is promotion to `belegt`, which requires a source and
`as_of`.

### ID path scheme

The canonical model identity is a path built from split fields, never a string
maintained by hand:

```
[hop/]vendor/model[:variant]
```

`auto/` is reserved for *intents* (auto, staged cascade), never a provider or
vendor. The path is built by `faigate/model_identity.py:29`
(`join_identity_path`, kept in lockstep with
`faigate.registry.provider_identity`). Resolution follows a fixed precedence —
exact long form, declared short name, derived short name, then kuerzel aliases
— and ambiguity is reported as a candidate list, never silently collapsed
(`faigate/model_identity.py:141`, `ModelIdentityResolver.resolve`). The long
form is what faigate returns, logs, and bills; a kuerzel alias (`ds`, `kc`)
resolves but never surfaces (`faigate/model_identity.py:1`).

### The migration order was deliberate

Facts moved first, assessment second, wiring last — the order is migration
safety, not value: the integrity guard must exist before the catalog carries
anything expensive. The sync guard rejects a catalog that shrinks below a
minimum or against the bundled baseline (`faigate/metadata_catalog_sync.py:133`,
`_validate_integrity`), and an unknown model id is answered with
`model_not_found` instead of a silent 200 from a substitute model
(`faigate/main.py:5386`, `_is_known_model_identity` at
`faigate/main.py:962`).

## Related

* [docs/blueprints/model-updater/prd.md](blueprints/model-updater/prd.md) — full PRD
* [docs/FUSIONAIZE-SHARED-METADATA.md](FUSIONAIZE-SHARED-METADATA.md) — design rationale & repo layout
