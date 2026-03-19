# `@faigate/cli`

Small npm CLI for checking and previewing a fusionAIze Gate gateway.

## Commands

```bash
faigate-cli health
faigate-cli models
faigate-cli update --force
faigate-cli route --message "Route this request" --client codex
```

## Base URL

Default:

```bash
http://127.0.0.1:8090
```

Override with:

```bash
FAIGATE_BASE_URL=http://127.0.0.1:8090
```

or:

```bash
faigate-cli health --base-url http://127.0.0.1:8090
```
