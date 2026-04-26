# Catalog Updater

faigate keeps its provider catalog (pricing, model aliases, capabilities,
freshness flags) in a separate metadata repo so we can ship updated pricing
and new models without cutting a faigate release.

This document describes how the catalog syncs at runtime, the env vars and
auth that control it, the CLI commands that drive it, and how to debug it
when it misbehaves.

## What lives where

| Repo | Visibility | Holds |
|------|------------|-------|
| [fusionaize-metadata-public](https://github.com/fusionAIze/fusionaize-metadata-public) | public | `providers/`, `models/`, `offerings/`, schemas |
| [fusionaize-metadata](https://github.com/fusionAIze/fusionaize-metadata) | private | `products/gate/overlays.v1.json`, `packages/` |
| `faigate/assets/metadata/catalog.v1.json` | bundled in wheel | snapshot used as last-resort fallback |

## Resolution chain

When a faigate process needs the provider catalog, the resolver walks four
sources in order and uses the first one that returns valid data:

```
1. FAIGATE_PROVIDER_METADATA_FILE / FAIGATE_PROVIDER_METADATA_DIR (local)
2. Private remote   (only if FAIGATE_METADATA_TOKEN is set)
3. Public  remote   (anonymous)
4. Bundled snapshot (shipped in the wheel)
```

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

Metadata sync state is written next to each cache tier and surfaced through
the existing catalog alert pipeline:

- `sync-stale` — last successful sync is older than 7 days, or no sync has
  ever succeeded.
- `sync-invalid` — remote JSON parsed but failed catalog validation.
- `sync-auth` — private metadata request returned 401/403.

The alerts appear in `/api/provider-catalog`, dashboard summaries, and any
surface already consuming `build_catalog_alerts`.

## Troubleshooting

### `faigate-models status` shows `bundled  present=no`

The wheel was built without `assets/metadata/catalog.v1.json`. Either run
`scripts/refresh-bundled-catalog` and rebuild, or add the file manually
before installing. The runtime resolver still works against remote tiers
in this state, but offline boots have no fallback.

### Private tier always falls through to public

Verify the token, scope, and target URL:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $FAIGATE_METADATA_TOKEN" \
  https://raw.githubusercontent.com/fusionAIze/fusionaize-metadata/master/providers/catalog.v1.json
# expect: 200
```

A 401/403 means token is wrong or doesn't have access. A 404 means the
resource path moved (after the public/private split, the private repo no
longer holds `providers/catalog.v1.json` — the URL above will 404 by
design; that is correct).

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

## Related

* [docs/blueprints/model-updater/prd.md](blueprints/model-updater/prd.md) — full PRD
* [docs/FUSIONAIZE-SHARED-METADATA.md](FUSIONAIZE-SHARED-METADATA.md) — design rationale & repo layout
