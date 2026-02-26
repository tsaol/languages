# Contributing

## Roles

| Account | Role | Responsibilities |
|---------|------|-----------------|
| **tsaol** | Product Manager | Create issues, review PRs, approve & merge |
| **leoc-76** | Developer | Pick up issues, write code, submit PRs |

## Workflow

```
tsaol creates issue (#21)
        ↓
leoc-76 picks up issue
        ↓
git checkout -b feature/issue-21-description
        ↓
write code, commit, push
        ↓
gh pr create (references: Closes #21)
        ↓
CI runs (lint + test + security)
LLM auto-reviews the PR
        ↓
tsaol reviews & approves
        ↓
merge to main → deploy
```

## Branch Naming

- `feature/issue-<number>-<short-description>` — new features
- `fix/issue-<number>-<short-description>` — bug fixes

## For leoc-76 (Developer)

```bash
# Setup (one time)
git clone https://github.com/tsaol/languages.git
cd languages
pip install -e .

# Daily workflow
git checkout main && git pull
git checkout -b feature/issue-21-add-something

# ... write code ...

git add <files>
git commit -m "add something"
git push origin feature/issue-21-add-something
gh pr create --title "add something" --body "Closes #21"
```

## For tsaol (Product Manager)

```bash
# Create issue
gh issue create --repo tsaol/languages --title "add X feature" --body "description"

# Review PR
gh pr review <number> --approve
gh pr merge <number>
```

## Rules

- No direct push to main (branch protection enabled)
- Every PR requires 1 approval from the other person
- CI must pass (lint + test)
- LLM code review runs automatically on every PR
