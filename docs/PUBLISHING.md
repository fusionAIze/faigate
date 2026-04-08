# fusionAIze Gate Publishing

## Goal

Keep release publishing boring and repeatable.

fusionAIze Gate currently ships through:

- Git tags and GitHub Releases
- Python distributions (`sdist` and `wheel`)
- a GHCR container image
- a separate npm CLI package in [packages/faigate-cli](../packages/faigate-cli)

PyPI remains opt-in and only publishes when trusted publishing is configured and `PYPI_PUBLISH=true` is set at the repository level.

## Dry-Run Path

Use the dry-run path whenever packaging, Docker, or release automation changes.

### GitHub

The repo includes [publish-dry-run](../.github/workflows/publish-dry-run.yml):

- builds the Python package
- runs `twine check dist/*`
- builds the container image through `docker/build-push-action`
- exercises `scripts/faigate-release --dry-run`
- does not push to GHCR
- does not publish to PyPI

### Local

```bash
python scripts/faigate-release --dry-run --version 1.11.3
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
docker build -t faigate:dry-run .
```

## Real Release Path

The real publish flow stays tag-driven through [release-artifacts](../.github/workflows/release-artifacts.yml):

1. cut the release PR and merge it to `main`
2. run `python scripts/faigate-release --version x.y.z`
3. tag the release from `main`
4. push the tag
   - this is the release-bot trigger; `.github/workflows/release-artifacts.yml` runs automatically for `v*` tags
5. let `release-artifacts` validate the tag/version match, build Python distributions, and push the GHCR image
6. publish the GitHub Release
   - this is the separate tap trigger; `.github/workflows/notify-tap.yml` runs when the release is published
7. let `notify-tap` dispatch the Homebrew update to [`fusionAIze/homebrew-tap`](https://github.com/fusionAIze/homebrew-tap)
8. optionally allow PyPI publication through trusted publishing
9. publish the separate npm CLI package only when you are ready to version the Node-facing surface independently

The local release helper now updates:

- `pyproject.toml`
- `faigate/__init__.py`
- `CHANGELOG.md`

It no longer rewrites a Homebrew formula inside this repo because the tap lives in the separate [`fusionAIze/homebrew-tap`](https://github.com/fusionAIze/homebrew-tap) repository.

## Trust Boundaries

- Dry-run workflows should never require production credentials.
- Real release publication should use GitHub environments and trusted publishing instead of long-lived secrets where possible.
- PyPI publication should remain opt-in until the package workflow is stable across several releases.

## Controlled Update Scheduling

Release publishing and deployment updates should stay separate concerns.

Publishing creates a tagged release. Applying that release on a host should remain a deliberate operator action or a tightly controlled scheduled helper.

If you want scheduled update application:

- keep `auto_update.enabled: true` explicit in `config.yaml`
- keep `update_check.release_channel` on `stable` unless you intentionally want preview releases in the check path
- keep `auto_update.rollout_ring` on `stable` or `early` for normal environments; use `canary` only for faster adopters
- keep `allow_major: false` unless you are ready to absorb breaking changes automatically
- keep `require_healthy_providers: true` unless you are intentionally allowing rollouts while the gateway is degraded
- set `min_release_age_hours` above `0` if you want scheduled rollouts to wait before applying newly published releases
- use `provider_scope.allow_providers` / `deny_providers` if rollout health should only consider a subset of providers
- enable `verification` if helper-driven updates must pass a post-update health or smoke check before the rollout is considered clean
- add `maintenance_window` if scheduled updates should only run in explicit local maintenance hours
- prefer the reviewed examples in [examples/faigate-auto-update.service](./examples/faigate-auto-update.service) and [examples/faigate-auto-update.timer](./examples/faigate-auto-update.timer)
- use the cron example in [examples/faigate-auto-update.cron](./examples/faigate-auto-update.cron) only when `systemd` timers are not practical

The helper still calls the normal update command. It does not bypass your service restart, health checks, or update guardrails.
