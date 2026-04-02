# GitHub Issue Workflow

## Overview
This workflow aligns Roadmap priorities with GitHub Issues and provides a lean, predictable process for implementing features from issue creation to merge and cleanup.

## Workflow Phases

```
Roadmap Priorities → GitHub Issues → Feature Branch → PR → Review → Merge → Cleanup
```

## 1. Issue Creation & Triage

### From Roadmap to Issues
Every roadmap item should be converted into one or more GitHub issues before implementation.

**Issue Creation Template:**
```bash
gh issue create --title "feat: [brief description] ([target release])" \
  --body-file - << 'EOF'
## Objective
[Clear, concise objective]

## Context
[Link to roadmap section, related issues, current status]

## Implementation Slices
1. [First deliverable slice]
2. [Second deliverable slice]
3. [Optional stretch goals]

## Success Criteria
- [Measurable success criterion 1]
- [Measurable success criterion 2]

## Related Issues
- #[number]: [Related issue title]

## Labels
- `roadmap:vX.Y` (target release)
- `priority:[high|medium|low]`
- `component:[bridge|dashboard|metadata|router|...]`
- `parity:[desktop|anthropic|...]` (if applicable)
EOF
```

### Labeling Guidelines
- **`roadmap:vX.Y`**: Target release version from roadmap (e.g., `roadmap:v1.19`, `roadmap:v1.20`)
- **`priority:`**: `high` (next release), `medium` (next 1-2 releases), `low` (backlog)
- **`component:`**: Primary component affected: `bridge`, `dashboard`, `metadata`, `router`, `cli`, `docs`
- **`parity:`**: For parity-focused work: `desktop`, `anthropic`, `claude-code`
- **Standard labels**: `bug`, `documentation`, `enhancement`, `question`

### Issue Triage Process
- **Weekly sync**: Review open issues against roadmap priorities
- **New roadmap items**: Convert to issues within 1 week of roadmap update
- **Stale issues**: Close or update issues older than 30 days without activity
- **Priority updates**: Adjust labels based on roadmap changes

## 2. Development Phase

### Branch Creation
Create feature branch directly from issue:
```bash
# Option 1: Using gh CLI (recommended)
gh issue develop [issue-number] --branch feature/[topic]-[date]

# Option 2: Manual branch naming
git checkout -b feature/[component]/[brief-description]-[date]
```

**Branch naming conventions:**
- `feature/claude-desktop-endpoints-2026-04-01`
- `feature/dashboard-route-explainability-2026-04-01`
- `feature/metadata-git-sync-2026-04-01`

### Commit Guidelines
- Reference issue number in commit message: `feat(bridge): exact token counting for Anthropic (#187)`
- Keep commits small and focused (1 logical change per commit)
- Write clear commit messages with "why" not just "what"
- Follow existing code style and conventions

### Development Checklist
- [ ] Read and understand the issue requirements
- [ ] Check for related issues and dependencies
- [ ] Write tests for new functionality
- [ ] Update documentation if needed
- [ ] Run linting and tests locally before pushing

## 3. Pull Request & Review

### PR Creation
```bash
gh pr create --title "feat: [descriptive title]" \
  --body "Closes #[issue-number]. Implements [brief description]..." \
  --reviewer @[reviewer] \
  --label "component:[component]" \
  --assignee @[assignee]
```

**PR Title Format:**
- `feat: [component] [description]`
- `fix: [component] [description]`
- `docs: [description]`
- `refactor: [component] [description]`

**PR Body Template:**
```
## Changes
- [Bullet list of key changes]

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed [describe]

## Documentation
- [ ] README/docs updated if needed
- [ ] Changelog entry added (for user-facing changes)

## Related Issues
Closes #[issue-number]

## Checklist
- [ ] Code follows project conventions
- [ ] Tests pass locally
- [ ] Linting passes (`ruff check --fix`)
- [ ] No new warnings introduced
```

### Review Process
**Reviewer Responsibilities:**
- Verify implementation matches issue requirements
- Check code quality and adherence to conventions
- Ensure tests are adequate and pass
- Confirm documentation is updated if needed
- Validate no breaking changes (unless intentional)

**Author Responsibilities:**
- Address review comments promptly
- Update PR based on feedback
- Keep PR focused on the issue scope
- Rebase if needed to resolve conflicts

**Review Labels:**
- `ready-for-review`: PR is ready for review
- `needs-changes`: PR requires updates before merge
- `approved`: PR approved for merge

## 4. Merge & Post-Merge

### Merge Criteria
- [ ] All tests pass (CI green)
- [ ] At least one approval
- [ ] No unresolved review comments
- [ ] Code coverage maintained or improved
- [ ] Documentation updated if needed

### Merge Strategy
- Prefer **squash and merge** for feature branches
- Keep commit history clean and logical
- Use descriptive merge commit message referencing issue

### Post-Merge Actions
1. **Close issue**: Automatically via PR closure ("Closes #[number]")
2. **Delete branch**: Immediately after merge (follow branch management guidelines)
3. **Update changelog**: Add entry to `CHANGELOG.md` for user-facing changes
4. **Verify deployment**: If applicable, verify changes work in target environment

## 5. Issue & Branch Cleanup

### Branch Management
- Delete feature branches immediately after merge
- Follow branch limits (max 15 active branches total)
- Clean up stale branches older than 30 days

### Issue Cleanup
- Close issues when implementation complete
- Move incomplete items to new issues if scope changed
- Archive resolved issues (keep for reference)

### Regular Maintenance
**Weekly:**
- Review open issues against roadmap
- Update priorities based on latest roadmap
- Close stale issues without activity

**Pre-release:**
- Verify all issues for target milestone are closed or moved
- Update roadmap with completed items
- Create issues for next release priorities

## Automation & Tools

### GitHub Actions
- Auto-label PRs based on branch name
- Auto-close issues on merge (via "Closes #[number]")
- Weekly issue triage reminder

### Local Scripts
Consider creating helper scripts:
- `scripts/issue-create-from-roadmap`: Convert roadmap items to issues
- `scripts/branch-cleanup`: Clean up merged/stale branches
- `scripts/pre-release-check`: Verify issue completion before release

## Related Documents
- [Git Workflow](./git-workflow.md) - Branch management and cleanup
- [Roadmap](../FAIGATE-ROADMAP.md) - Product direction and release sequence
- [RELEASES.md](../../RELEASES.md) - Release process and versioning