# fusionAIze Shared Metadata

## Purpose

This document defines the intended shape of the shared metadata line for
fusionAIze products.

It is deliberately **not** a generic cross-repo metadata platform.

Scope:

- `fusionAIze Gate`
- future fusionAIze products such as `Grid`, `Lens`, and `Fabric`

Out of scope:

- unrelated repositories
- general-purpose metadata hosting
- a mandatory hosted control plane

## Why this exists

Gate already needs stronger truth around:

- provider identity
- model and offer aliases
- modality and capability metadata
- pricing provenance
- freshness and review state

Those same concerns can later matter for other fusionAIze products. The shared
metadata line should therefore be designed once as a reusable fusionAIze
capability instead of re-invented inside each product.

## Working model

Recommended first model:

1. a dedicated Git repo for fusionAIze product metadata
2. versioned JSON documents
3. static-hostable snapshots
4. optional scheduled refresh jobs outside product runtimes
5. product-side refresh or import hooks

This gives us:

- reviewability in Git
- easy local mirroring
- no database requirement
- no forced fusionAIze-operated hosting

## Repository split (2026-04-26)

The metadata line is hosted across **two repos**:

- **Public** — [fusionAIze/fusionaize-metadata-public](https://github.com/fusionAIze/fusionaize-metadata-public)
  Anonymous-readable. Provider/model/offering catalogs and schemas. The
  source of truth for pricing and capability data.
- **Private** — [fusionAIze/fusionaize-metadata](https://github.com/fusionAIze/fusionaize-metadata)
  Auth-only (fine-grained PAT). Routing overlays, operator quota packages,
  evaluations. Anything that would leak IP if public.

Rationale: pricing and capability data is reproducible from vendor docs and
benefits from public eyeballs and contributions. Routing heuristics, scoring,
and operator quota state are competitive surface and stay private.

## Proposed repo shape

**Public repo** (`fusionaize-metadata-public`):

```text
fusionaize-metadata-public/
  README.md
  schemas/
    provider-catalog.v1.schema.json
    model-catalog.v1.schema.json
    offering-catalog.v1.schema.json
  providers/
    catalog.v1.json
    sources.v1.json
  models/
    catalog.v1.json
  offerings/
    catalog.v1.json
```

**Private repo** (`fusionaize-metadata`):

```text
fusionaize-metadata/
  README.md
  schemas/
    package-catalog.v1.schema.json
  packages/
    catalog.v1.json            # Operator quota packages
  products/
    gate/
      overlays.v1.json
    grid/
      overlays.v1.json
    lens/
      overlays.v1.json
    fabric/
      overlays.v1.json
```

## Provider catalog snapshot shape

Recommended top-level form:

```json
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "generated_at": "2026-03-31T18:00:00Z",
  "source_repo": "fusionaize-metadata",
  "providers": {
    "deepseek-chat": {
      "recommended_model": "deepseek-chat",
      "aliases": ["deepseek-chat", "ds-v3"],
      "track": "stable",
      "offer_track": "direct",
      "provider_type": "direct",
      "auth_modes": ["api_key"],
      "volatility": "low",
      "evidence_level": "official",
      "official_source_url": "https://api-docs.deepseek.com/",
      "signup_url": "https://platform.deepseek.com/",
      "watch_sources": [],
      "notes": "Balanced DeepSeek direct route",
      "last_reviewed": "2026-03-31",
      "pricing": {
        "source_type": "provider-docs",
        "source_url": "https://api-docs.deepseek.com/pricing",
        "refreshed_at": "2026-03-31T17:45:00Z",
        "freshness_status": "fresh"
      }
    }
  }
}
```

## Required metadata principles

Every price or offer-oriented field should be able to answer:

- where did this value come from?
- when was it refreshed?
- how fresh is it?
- is it official, mixed, manual, or observed?

Recommended provenance fields:

- `source_type`
- `source_url`
- `refreshed_at`
- `freshness_status`

## Gate integration path

The first Gate slice should stay intentionally small:

- Gate keeps its embedded curated catalog as a fallback baseline
- Gate can optionally load an external JSON snapshot
- the external snapshot can add new providers or override embedded fields

That gives us a clean migration path:

1. embedded Python catalog only
2. optional JSON snapshot overrides
3. JSON snapshot becomes preferred truth source
4. embedded catalog shrinks to bootstrap fallback only

## Current Gate hooks

Gate supports per-file and per-directory env vars; after the 2026-04-26
public/private split, the recommended dev configuration uses both:

```bash
# Private overlays + packages
export FAIGATE_PROVIDER_METADATA_DIR=/path/to/fusionaize-metadata
export FAIGATE_PROVIDER_METADATA_PRODUCT=gate

# Public catalog files (override the in-DIR fallback)
export FAIGATE_PROVIDER_METADATA_FILE=/path/to/fusionaize-metadata-public/providers/catalog.v1.json
export FAIGATE_OFFERINGS_METADATA_FILE=/path/to/fusionaize-metadata-public/offerings/catalog.v1.json
```

Resolution order per file (existing semantics, unchanged):

1. If `FAIGATE_*_METADATA_FILE` is set → load that path directly.
2. Otherwise, look under `FAIGATE_PROVIDER_METADATA_DIR/<relative-path>`.
3. If neither is found → empty catalog (faigate falls back to embedded
   `providers.py` definitions).

`MetadataCatalogSync` (`faigate/metadata_catalog_sync.py`) fetches the public
repo over HTTPS with ETag caching, and `CatalogResolver`
(`faigate/catalog_resolver.py`) runs the private-public-bundled chain over it.
The environment overrides above still take precedence over the synced catalog:
the resolution order is unchanged, with `FAIGATE_PROVIDER_METADATA_FILE` as its
first step.

For runtime use, Gate also ships a small helper that materializes a repo
checkout into one snapshot file:

```bash
./scripts/faigate-provider-metadata-sync \
  --repo /path/to/fusionaize-metadata \
  --product gate
```

The output snapshot can then be pointed to with
`FAIGATE_PROVIDER_METADATA_FILE` and refreshed alongside restart or
repo-update flows.

For the first tracked gaps in Gate, the example `products/gate/overlays.v1.json`
already includes:

- `anthropic-haiku`
- `anthropic-sonnet`
- `gemini-pro`
