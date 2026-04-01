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
    model-catalog.v1.schema.json
    offering-catalog.v1.schema.json
    package-catalog.v1.schema.json
  providers/
    catalog.v1.json
    sources.v1.json
  models/
    catalog.v1.json
  offerings/
    catalog.v1.json
  packages/
    catalog.v1.json
  products/
    gate/
      overlays.v1.json
```

## Gate integration

Gate supports environment-driven metadata loading:

### Provider catalog
- `FAIGATE_PROVIDER_METADATA_FILE`: override path to provider catalog JSON
- `FAIGATE_PROVIDER_METADATA_DIR`: root directory of metadata repository
- `FAIGATE_PROVIDER_METADATA_PRODUCT`: product name for overlays (default "gate")

### Offerings catalog (v1.16+)
- `FAIGATE_OFFERINGS_METADATA_FILE`: override path to offerings catalog JSON

### Packages catalog (v1.16+)
- `FAIGATE_PACKAGES_METADATA_FILE`: override path to packages catalog JSON

To materialize a snapshot from a repo checkout for runtime use:

```bash
./scripts/faigate-provider-metadata-sync \
  --repo /path/to/fusionaize-metadata \
  --product gate

Restart and managed update flows can call the same helper automatically when
`FAIGATE_PROVIDER_METADATA_DIR` is set in the runtime environment.

Automated metadata synchronization is available via systemd timer or cron:
- Systemd: `faigate-metadata-sync.service` + `faigate-metadata-sync.timer`
- Cron: See `faigate-metadata-sync.cron` example
```
