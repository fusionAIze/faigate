# CI Safeguards

Three complementary mechanisms enforce code quality gates in this repo:

1. **Local pre-commit hooks** — catch issues before they reach GitHub
2. **CI Gate job** — single required check that cannot be bypassed
3. **Auto-merge bot** — merges automatically once the gate passes

Together they eliminate the "merge and fix later" cycle.

---

## 1. Local Pre-commit Hooks

### Setup (one-time, per clone)

```bash
pip install -e ".[dev]"
pre-commit install
```

### What it runs on every `git commit`

| Hook | Purpose |
|------|---------|
| `trailing-whitespace` | Strips trailing whitespace |
| `end-of-file-fixer` | Ensures files end with a newline |
| `check-yaml` | Validates YAML syntax (catches duplicate keys) |
| `check-merge-conflict` | Detects unresolved conflict markers |
| `detect-private-key` | Blocks accidental credential commits |
| `ruff` | Lints Python (auto-fixes where possible) |
| `ruff-format` | Formats Python |
| `bandit` | Security scan on `faigate/` package |

### Manual run (scan all files)

```bash
pre-commit run --all-files
```

### Validate hook config itself

```bash
pre-commit validate-config .pre-commit-config.yaml
```

CI runs this step before executing the hooks. It catches typos in hook IDs
(e.g. `check-merge-conflicts` vs. `check-merge-conflict`) before they silently
disable entire hook groups.

---

## 2. CI Gate Job

### How it works

`ci.yml` defines a `gate` job that depends on `test`, `lint`, and `package`:

```yaml
gate:
  name: CI Gate
  runs-on: ubuntu-latest
  needs: [test, lint, package]
  if: always()
  steps:
    - name: All required checks passed
      run: |
        if [[ "${{ needs.test.result }}"    != "success" ]] ||
           [[ "${{ needs.lint.result }}"    != "success" ]] ||
           [[ "${{ needs.package.result }}" != "success" ]]; then
          echo "::error::One or more required checks failed — merge blocked."
          exit 1
        fi
```

`if: always()` ensures the gate job runs even when upstream jobs fail — without
this, a failed `test` job would cause `gate` to be skipped, which would count
as "not run" rather than "failed" in branch protection.

### Branch protection setup (one-time, per repo)

In **Settings → Branches → Branch protection rules** for `main`:

1. Enable **"Require status checks to pass before merging"**
2. Add **`CI Gate`** as the required check (only this one — not individual jobs)
3. **Uncheck "Allow administrators to bypass branch protection rules"**

Step 3 is the critical one. With admin bypass disabled, `gh pr merge --admin`
no longer works. The only path to merge is through the gate.

> **If CI itself is broken** (e.g. a hook config typo): fix the CI config,
> push the fix as a PR, let the gate pass, and merge normally. Do not add
> temporary admin bypass — fix the root cause.

### Why a single gate check instead of multiple required checks?

Adding individual jobs (`test`, `lint`) as required checks means you have to
update branch protection settings every time you rename or add a job. The gate
job is a stable indirection layer: update `needs:` in the workflow, not GitHub
settings.

---

## 3. Auto-merge Bot

### How it works

`.github/workflows/automerge.yml` enables GitHub's native auto-merge on every
non-draft PR when it is opened or updated:

```yaml
- name: Enable auto-merge (squash)
  run: gh pr merge --auto --squash "${{ github.event.pull_request.number }}"
```

Once enabled, GitHub automatically merges the PR the moment all required status
checks pass. No manual merge step needed.

### Prerequisites

Enable **"Allow auto-merge"** in **Settings → General** (under Pull Requests).
This is a one-time repo setting.

### Workflow

```
PR opened/pushed
      │
      ├─► automerge.yml enables --auto on the PR
      │
      └─► CI runs: test + lint + package
                │
                ├─► gate passes → GitHub merges automatically
                │
                └─► gate fails → PR stays open, author fixes and pushes
```

No manual `gh pr merge` calls. No `--admin` overrides.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Gate job skipped (not run) | `if: always()` missing from gate job | Add `if: always()` |
| `--admin` merge still works | Admin bypass not disabled in branch protection | Uncheck it in Settings |
| Auto-merge not triggering | "Allow auto-merge" disabled in repo settings | Enable in Settings → General |
| `pre-commit validate-config` fails | Typo in hook ID or wrong `rev` | Fix `.pre-commit-config.yaml` |
| `check-merge-conflict` unknown | Hook name typo (trailing `s`) or wrong version | Use `check-merge-conflict` with `rev: v4.6.0` |
