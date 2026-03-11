# Contributing to FoundryGate

Thanks for your interest. Contributions are welcome.

## Development Setup

```bash
git clone https://github.com/typelicious/ClawGate.git
cd ClawGate
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
```

Compatibility note: the repo and runtime still use several `clawgate` identifiers during the transition. That is expected for now.

## Running Tests

```bash
python -m compileall .
pytest tests/ -v
```

Tests mocken `httpx` und brauchen keine API-Keys.

## Linting

```bash
ruff check .
ruff format .
```

## Repo Safety

```bash
git ls-files | egrep '(^\.ssh/|\.db($|-)|\.sqlite|\.log$)' && echo "forbidden tracked files"
git rev-list --objects --all | egrep '(^|/)(\.ssh/|.*\.db($|-)|.*\.sqlite|.*\.log$)' && echo "forbidden history artifacts"
```

## Adding a New Provider

1. Add provider config to `config.yaml` with `pricing` block
2. If the API isn't OpenAI-compatible, add a backend method in `providers.py`
3. Add routing rules in `config.yaml` (static or heuristic)
4. Add tests in `tests/test_routing.py`

## Adding Routing Rules

Heuristic rules in `config.yaml` support:
- `message_keywords` — keyword matching (user messages only!)
- `has_tools` — tool call detection
- `estimated_tokens` — token count thresholds
- `fallthrough` — catch-all default

Important: Never score the system prompt for keywords. See ClawRouter's insight on this.

## Submitting Changes

1. Fork the repo
2. Create a `feature/<topic>-<date>` branch
3. Add tests for new functionality
4. Ensure `pytest` and `ruff check` pass
5. Open a PR with a clear description

See [docs/process/git-workflow.md](./docs/process/git-workflow.md) for the full branch model.

## Skill Updates

The skill lives in `skills/clawgate/SKILL.md`. If you update slash commands or add new endpoints, update the skill too.
