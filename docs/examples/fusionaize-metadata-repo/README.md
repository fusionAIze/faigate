# fusionAIze Metadata Repo Skeleton

This directory is a starter skeleton for a future dedicated
`fusionaize-metadata` repository.

It is intentionally scoped to fusionAIze products only:

- Gate
- Grid
- Lens
- Fabric

It is not intended as a shared metadata platform for unrelated repositories.

## Layout

```text
fusionaize-metadata/
  README.md
  schemas/
    provider-catalog.v1.schema.json
  providers/
    catalog.v1.json
    sources.v1.json
  products/
    gate/
      overlays.v1.json
```

## Gate integration

Gate supports two input modes:

1. direct snapshot file
   - `FAIGATE_PROVIDER_METADATA_FILE=/path/to/provider-catalog.snapshot.v1.json`
2. metadata repo checkout with product overlay
   - `FAIGATE_PROVIDER_METADATA_DIR=/path/to/fusionaize-metadata`
   - optional `FAIGATE_PROVIDER_METADATA_PRODUCT=gate`

To materialize a snapshot from a repo checkout for runtime use:

```bash
./scripts/faigate-provider-metadata-sync \
  --repo /path/to/fusionaize-metadata \
  --product gate

Restart and managed update flows can call the same helper automatically when
`FAIGATE_PROVIDER_METADATA_DIR` is set in the runtime environment.
```
