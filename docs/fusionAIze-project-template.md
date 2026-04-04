# fusionAIze Project Template

This template defines the professional software‑development benchmark for fusionAIze projects (Lens, Fabric, Grid, Browser, OS). It captures the tooling, automation, and quality gates established in fusionAIze Gate.

## Core Architecture Principles

1. **Gateway‑first architecture** – Keep the core small, focused, and portable.
2. **Clear provider boundaries** – Use client adapters, not one‑off integrations.
3. **Standard API surfaces first** – Prefer OpenAI‑compatible endpoints before custom adapters.
4. **Operational simplicity** – Avoid platform sprawl; keep failure modes visible.
5. **Local‑first, cloud‑portable** – Design for local operation with optional cloud scaling.

## Required Tooling & Dependencies

### Development Dependencies (pyproject.toml)

```toml
[project.optional-dependencies]
dev = [
    "build>=1.2",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "pytest-benchmark>=4.0.0",
    "httpx",  # for TestClient
    "ruff>=0.8",
    "twine>=6.1",
    "pre-commit>=3.0",
    "bandit[toml]>=1.8.0",
    "jinja2>=3.1.0",
]
```

### Pre‑commit Configuration (.pre‑commit‑config.yaml)

Include hooks for:
- Ruff linting and formatting
- Bandit security scanning
- Conventional‑commit validation
- File hygiene (trailing whitespace, end‑of‑file fixer, etc.)

### Git‑cliff Configuration (.cliff.toml)

Configure conventional‑commit parsing and automated changelog generation.

### Coverage Configuration (.coveragerc)

Define coverage sources, exclusions, and reporting options.

### DevContainer Configuration (.devcontainer/devcontainer.json)

Provide a consistent development environment with VS Code extensions and post‑create commands.

## CI/CD Pipeline (GitHub Actions)

### Core Jobs

1. **Test** – Multi‑Python version testing with coverage reporting and Codecov upload.
2. **Lint** – Ruff checks, format validation, shell‑script linting, pre‑commit hooks, version‑consistency validation.
3. **Security** – Bandit scanning with HTML/JSON report artifacts.
4. **Package** – Python package build and Twine validation.
5. **Benchmarks** – Performance benchmark suite (runs on main pushes).
6. **Docs** – API documentation generation and validation.
7. **Changelog** – git‑cliff validation to ensure CHANGELOG.md is up‑to‑date.

### Additional Workflows

- **codeql.yml** – GitHub CodeQL security scanning.
- **repo‑safety.yml** – Repository‑hygiene enforcement (no secrets, forbidden files).
- **release‑artifacts.yml** – Release packaging for PyPI, Docker, and Homebrew.
- **publish‑dry‑run.yml** – Pre‑release validation.
- **notify‑tap.yml** – Homebrew tap integration.

## Development Workflow

### Onboarding

1. Clone the repository.
2. Open in VS Code with DevContainers (recommended) or set up a local Python 3.12+ environment.
3. Run `pip install -e .[dev]` to install development dependencies.
4. Run `pre‑commit install` to install git hooks.

### Daily Development

- Write tests for new features.
- Run `pytest` locally before pushing.
- Use `ruff check .` and `ruff format .` to maintain code style.
- Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).

### Pre‑Commit Hooks

The following hooks run automatically on `git commit`:

- **trailing‑whitespace** – Removes trailing whitespace.
- **end‑of‑file‑fixer** – Ensures files end with a newline.
- **check‑yaml** – Validates YAML files.
- **detect‑private‑key** – Prevents accidental commits of private keys.
- **ruff** – Lints and fixes Python code.
- **ruff‑format** – Formats Python code.
- **bandit** – Runs security scanning.
- **conventional‑commits** – Validates commit messages.

## Testing Strategy

### Unit Tests

- Place tests in `tests/` directory.
- Use `pytest‑asyncio` for async tests.
- Mock external dependencies (HTTP calls, file system, environment variables).

### Coverage Requirements

- Aim for ≥80% line coverage.
- Coverage reports are generated in CI and uploaded to Codecov.
- Exclude vendor files, assets, and test directories from coverage.

### Performance Benchmarks

- Place benchmark tests in `tests/benchmarks/`.
- Use `pytest‑benchmark` to track performance over time.
- Benchmarks run automatically on pushes to `main`.

## Documentation

### API Documentation

- Use FastAPI’s automatic OpenAPI generation.
- Maintain a `docs/API.md` file that is auto‑generated from the OpenAPI spec.
- The CI validates that `docs/API.md` matches the current API.

### Project Documentation

- `README.md` – Primary landing page with badges, quick start, and navigation.
- `docs/` – Detailed architecture, integration, onboarding, and troubleshooting guides.
- `CHANGELOG.md` – Auto‑generated from git history using git‑cliff.
- `ROADMAP.md` – Project roadmap and release planning.

## Release Process

### Versioning

- Use [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).
- Versions are tracked in `pyproject.toml` and `__init__.py`.
- CI validates that both files are in sync.

### Release Script

- Use `scripts/faigate‑release` (or equivalent) to prepare releases.
- The script:
  - Validates version consistency.
  - Updates version files.
  - Updates the changelog.
  - Outputs the next steps for tagging and pushing.

### Automated Changelog

- `git‑cliff` generates the changelog from conventional commits.
- The `changelog` CI job ensures the changelog is up‑to‑date.

## Security & Compliance

### Scanning Tools

- **Bandit** – Python‑specific security issues.
- **CodeQL** – GitHub’s advanced semantic code analysis.
- **Repository safety** – Blocks commits of secrets and forbidden files.

### Dependency Management

- Dependabot is configured for automatic dependency updates.
- Security vulnerabilities are automatically flagged and patched.

## Issue & PR Workflow

### Issue Creation

- Use GitHub Issues for all feature requests, bugs, and tasks.
- Apply labels: `roadmap:vX.Y`, `priority:high|medium|low`, `component:*`, `parity:*`.
- Reference the relevant roadmap milestone.

### Pull Requests

- Branch naming: `feature/<topic>‑<date>`, `review/<topic>‑<date>`, `hotfix/<topic>‑<date>`.
- PR description must include:
  - Summary of changes.
  - Link to related issue(s).
  - Testing performed.
  - Screenshots (if UI changes).
- All CI jobs must pass before merge.
- At least one review required for non‑trivial changes.

### Branch Management

- `main` is always stable and release‑ready.
- Feature branches are deleted after merge.
- Use `git worktree` for parallel development contexts.

## Monitoring & Observability

### Health Endpoints

- Expose a `/health` endpoint with service status, provider summary, and capability coverage.
- Include metrics for request counts, token usage, and error rates.

### Logging

- Use structured logging (JSON) for production deployments.
- Log levels: DEBUG (development), INFO (normal operation), WARNING (unexpected but handled), ERROR (failures).

### Metrics

- Expose Prometheus metrics (optional) for advanced monitoring.
- Track request latency, error rates, and provider health.

## Optimization Opportunities

### High Priority

1. Test coverage reporting with `pytest‑cov`.
2. Pre‑commit hooks for code quality.
3. Security scanning with Bandit.
4. Version‑bump automation.

### Medium Priority

5. DevContainer configuration.
6. Performance benchmark suite.
7. API documentation automation.
8. Changelog automation with git‑cliff.

### Low Priority

9. Advanced monitoring (Prometheus, structured logging).
10. Multi‑environment testing (macOS, Windows).
11. Dependency license compliance.
12. Code quality metrics dashboard.

## Template Adoption

To apply this template to a new fusionAIze project:

1. Copy the `.github/workflows/` directory.
2. Copy `.pre‑commit‑config.yaml`, `.cliff.toml`, `.coveragerc`, `.devcontainer/`.
3. Update `pyproject.toml` with project‑specific metadata.
4. Adjust the CI jobs as needed (e.g., remove Python multi‑version testing if not applicable).
5. Update this document with project‑specific details.

## License

fusionAIze projects are licensed under the Apache‑2.0 license unless otherwise specified.

---

*This template is derived from the fusionAIze Gate project and serves as the benchmark for all fusionAIze repositories.*
