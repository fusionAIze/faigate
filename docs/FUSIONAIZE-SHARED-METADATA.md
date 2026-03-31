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

## Proposed repo shape

```text
fusionaize-metadata/
  README.md
  schemas/
    provider-catalog.v1.schema.json
  providers/
    catalog.v1.json
    sources.v1.json
  snapshots/
    providers/
      2026-03-31T18-00-00Z.catalog.v1.json
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

Gate now supports two operator-side import hooks:

- `FAIGATE_PROVIDER_METADATA_FILE=/path/to/provider-catalog.snapshot.v1.json`
- `FAIGATE_PROVIDER_METADATA_DIR=/path/to/fusionaize-metadata`

If `FAIGATE_PROVIDER_METADATA_FILE` is set, Gate loads that JSON snapshot
directly and merges it into the embedded provider catalog.

If `FAIGATE_PROVIDER_METADATA_DIR` is set, Gate loads:

- `providers/catalog.v1.json`
- `products/gate/overlays.v1.json`

and materializes an effective Gate catalog in memory before merging it into the
embedded provider catalog.

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
