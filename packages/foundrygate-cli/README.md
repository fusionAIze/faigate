# `@foundrygate/cli`

Small npm CLI for checking and previewing a FoundryGate gateway.

## Commands

```bash
foundrygate-cli health
foundrygate-cli models
foundrygate-cli update --force
foundrygate-cli route --message "Route this request" --client codex
```

## Base URL

Default:

```bash
http://127.0.0.1:8090
```

Override with:

```bash
FOUNDRYGATE_BASE_URL=http://127.0.0.1:8090
```

or:

```bash
foundrygate-cli health --base-url http://127.0.0.1:8090
```
