# fusionAIze Gate Operations

This page keeps the deployment, helper-script, and update-control details out of the root README while staying copy/paste friendly for operators.

## Deployment Modes

### Local Python Run

Good for development and early validation:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m faigate
```

### `systemd` On Generic Linux

The repo ships a service file:

```text
/etc/systemd/system/faigate.service
```

Recommended persistent state path:

```text
/var/lib/faigate/faigate.db
```

That path is wired through `FAIGATE_DB_PATH`.

### Workstation Runtime Installs

For workstation usage, keep the runtime install separate from the development checkout.

Recommended baseline:

- Linux: `systemd` or `systemd --user`
- macOS: `launchd` via `~/Library/LaunchAgents`
- Windows: Task Scheduler plus direct venv Python invocation

See [WORKSTATIONS.md](./WORKSTATIONS.md) for the path layout and OS-specific runtime guidance.

### Homebrew On macOS

For macOS workstations, fusionAIze Gate now also ships a project-owned formula in [`fusionAIze/homebrew-tap`](https://github.com/fusionAIze/homebrew-tap/blob/main/Formula/faigate.rb).

Typical flow:

```bash
brew tap fusionAIze/homebrew-tap https://github.com/fusionAIze/homebrew-tap
brew install fusionAIze/homebrew-tap/faigate
brew services start fusionAIze/homebrew-tap/faigate
```

That path keeps config under `$(brew --prefix)/etc/faigate`, state under `$(brew --prefix)/var/lib/faigate`, and logs under `$(brew --prefix)/var/log/faigate`.

### Docker / GHCR

Tagged releases build container artifacts through the release workflow. For local validation you can build from the repo root:

```bash
docker build -t faigate:local .
docker run --rm -p 8090:8090 --env-file .env faigate:local
```

### Python Package And npm CLI

Release workflows build Python `sdist` and `wheel` artifacts.

For CLI-facing environments, the repo also includes a separate package:

```text
packages/faigate-cli
```

That package is intentionally separate from the Python gateway runtime.

## Helper Scripts

fusionAIze Gate ships optional wrappers around `systemd`, `journalctl`, `curl`, onboarding checks, and release-update flows.

The runtime-control helpers now auto-detect Linux vs macOS:

- on Linux they continue to use `systemd`
- on macOS they manage the shipped `launchd` LaunchAgent
- Windows remains documentation/example-driven for now

| Script | What it does |
| --- | --- |
| `faigate-install` | install service + helper links |
| `faigate-start` / `faigate-stop` / `faigate-restart` | service control with platform detection, plus restart verification |
| `faigate-status` / `faigate-logs` / `faigate-health` | operator visibility, service-manager context, and recent/tailing logs |
| `faigate-config-overview` | current config snapshot for bind, providers, modes, and profiles |
| `faigate-bootstrap` | local bootstrap convenience flow |
| `faigate-doctor` | validate env and config readiness |
| `faigate-onboarding-report` | summarize rollout readiness |
| `faigate-onboarding-validate` | fail fast on onboarding blockers |
| `faigate-update-check` | release-status and guardrail check |
| `faigate-auto-update` | helper-driven, opt-in update apply flow |
| `faigate-update` / `faigate-uninstall` | lifecycle helpers |

Examples:

```bash
./scripts/faigate-install
./scripts/faigate-config-overview
./scripts/faigate-status
./scripts/faigate-logs --lines 80
./scripts/faigate-restart --timeout 15
./scripts/faigate-health
./scripts/faigate-update-check
```

## Update Checks And Auto-Update

fusionAIze Gate supports explicit operator-side update control without turning the service into a self-mutating daemon.

API surfaces:

- `GET /api/update`
- `GET /api/operator-events`

Relevant config blocks:

- `update_check`
- `auto_update`

Guardrails available today:

- release channels
- rollout rings
- minimum release age
- maintenance windows
- provider scopes
- post-update verification

Major upgrades stay blockable through config, and helper-driven apply flows remain opt-in.

## Scheduled Examples

The repo ships example schedules under [`docs/examples`](./examples):

- `faigate-auto-update.service`
- `faigate-auto-update.timer`
- `faigate-auto-update.cron`
- `com.fusionaize.faigate.plist`
- `faigate-start.ps1`
- `faigate-task-scheduler.xml`

Use them only after the manual update path is already validated.

## Troubleshooting

Start with:

- [`docs/TROUBLESHOOTING.md`](./TROUBLESHOOTING.md)
- `./scripts/faigate-health`
- `./scripts/faigate-status`
- `./scripts/faigate-logs`

The most common rollout issues are:

- provider API keys missing or still templated
- DB path not writable
- port `8090` already in use
- a provider repeatedly failing into fallback
