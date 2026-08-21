# Catalog Provenance (pub-shared provider catalog, WS-B)

Status: documentation only. This file records the provenance of the public
provider catalog and reconciles the `auth_modes` OAuth discrepancy (TASK-007,
WS-B). It is evidence-only; it changes no code and no catalog content.

## 1. What the artifact is

`faigate/assets/metadata/catalog.v1.json` is a **bundled snapshot** of the
curated public provider catalog. It is not generated from code; it is copied
verbatim from the public metadata repo at release-cut time.

- `schema_version`: `fusionaize-provider-catalog/v1.1` (asset line 2)
- `generated_at`: `2026-08-20T00:00:00Z` (asset line 3)
- `source_repo`: `fusionaize-metadata-public` (asset line 4)
- 47 provider entries (verified `len(providers) == 47`)

Package docstring `faigate/assets/metadata/__init__.py` states the snapshot is
"refreshed by `scripts/refresh-bundled-catalog`" and is the offline
first-install fallback; `CatalogResolver` prefers freshly synced caches.

## 2. Generator, repo, cadence

**Generator.** `scripts/refresh-bundled-catalog` (23 lines). It does not
synthesize data — it `curl`s the public repo and atomically swaps the snapshot:

```bash
SOURCE_URL="https://raw.githubusercontent.com/fusionAIze/fusionaize-metadata-public/main/providers/catalog.v1.json"  # line 9
curl -fsSL "$SOURCE_URL" -o "$TMP"   # line 14
mv "$TMP" "$SNAPSHOT"                # line 21
```

The only validation is structural (a `providers` key must exist, script line 16).

**Canonical repo.** `fusionAIze/fusionaize-metadata-public` (public,
anonymous-readable). Confirmed by `faigate/catalog_resolver.py:31-33`
(`DEFAULT_PUBLIC_URL`) and `docs/CATALOG-UPDATER.md:15`.

**Cadence.** Two independent rhythms:

1. *Bundled snapshot* — "run at release-cut time" (script header line 3) and
   `docs/CATALOG-UPDATER.md:199-210`. There is no scheduled job; a human runs
   `./scripts/refresh-bundled-catalog && git add ... && git commit` before a tag.
2. *Runtime refresh* — `DEFAULT_REFRESH_INTERVAL_SECONDS = 24*60*60`
   (`faigate/catalog_resolver.py:37`), ETag-cached tier resolution. So a running
   faigate refreshes daily from the public repo, while the *bundled* copy only
   moves at release-cut.

## 3. Why `auth_modes` is `api_key`-only in parts (the OAuth claim)

The OAuth claim is real, but the authority for OAuth modes is **split across two
independent artifacts that drift**:

| Artifact | Kind | OAuth-mode providers |
|---|---|---|
| `faigate/provider_catalog.py` | in-code static dict | `claude-code` (:669), `google-antigravity` (:686), `google-gemini-cli` (:711), `qwen-portal` (:959), `kiro` (:1083), `qoder` (:1100), `openai-codex` (:1118), `github-copilot` (:1172, `oauth`+`api_key`) — 8 entries |
| `faigate/assets/metadata/catalog.v1.json` | bundled snapshot of public repo | `openai-codex`, `google-vertex` (`oauth`+`adc`), `kiro`, `qoder` — 4 entries |

The JSON is **not** serialized from `provider_catalog.py` (the refresher script
fetches the JSON from GitHub, it does not emit the Python dict). The opposite
direction does not apply either — nothing imports the JSON back into the dict.
They are curated separately and have diverged.

**Verdict: metadata-completeness gap, not a serialization bug.** OAuth is
implemented and observable (`faigate/oauth/`, dispatched via
`faigate/providers.py:93-101`; see `faigate_v2_research/TASK-006-oauth-provenance.md`).
The gap is that the curated public JSON has not caught up with the in-code
catalog: `claude-code`, `google-antigravity`, `google-gemini-cli`, `qwen-portal`,
and `github-copilot` carry OAuth in `provider_catalog.py` but are absent from the
snapshot (and `google-antigravity` is absent from the JSON entirely, first noted
in TASK-006 line 62-65). The snapshot also models `google-vertex` (`oauth`+`adc`)
under a key the code does not use for OAuth.

## 4. Target schema location for the OAuth mode

The catalog-level field already exists and is correct: per-provider
`auth_modes: ["oauth", ...]` on the catalog entry, i.e.:

```
providers.<provider-id>.auth_modes   (string array; values "api_key" | "oauth" | "adc" | ...)
```

No new top-level field or nested `.auth` object is required. The field is
present in both the schema example (`docs/FUSIONAIZE-SHARED-METADATA.md:123`) and
the live JSON. The OAuth *mode string* for OAuth-backed providers is `"oauth"`.

Closing the gap is a **data** change, not a schema change: bring the public
repo's `providers/catalog.v1.json` entries for `claude-code`, `google-antigravity`,
`google-gemini-cli`, `qwen-portal`, and `github-copilot` into parity with
`provider_catalog.py` (and re-run `scripts/refresh-bundled-catalog` before the
next release-cut). No faigate schema or resolver change is needed.

## 5. Evidence map

- `faigate/assets/metadata/catalog.v1.json:2-4` — schema_version, generated_at, source_repo.
- `faigate/assets/metadata/__init__.py:1-10` — snapshot provenance + refresh-script pointer.
- `scripts/refresh-bundled-catalog:3,9,14,16,21` — release-cut curl+swap, structural validation only.
- `faigate/catalog_resolver.py:31-37` — public URL + 24h runtime refresh interval.
- `docs/CATALOG-UPDATER.md:13-17,199-210` — repo split, resolution chain, bundled-refresh procedure.
- `docs/FUSIONAIZE-SHARED-METADATA.md:56-59,107-140` — public/private split, catalog shape with `auth_modes`.
- `faigate/provider_catalog.py:669,686,711,959,1083,1100,1118,1172` — in-code OAuth-mode entries.
- `faigate_v2_research/TASK-006-oauth-provenance.md:20-76` — prior reconciliation of the OAuth "implemented" claim.
