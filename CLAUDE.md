# Project Rules for Claude

## MANDATORY: GitHub Flow — Never Push to Main Directly

This project uses GitHub Flow with two collaborators. You MUST follow this workflow for EVERY code change. No exceptions.

### Roles
- **tsaol** (admin): Creates issues, reviews PRs, approves & merges
- **leoc-76** (developer): Writes code, creates feature branches, submits PRs

### Workflow (MUST follow for every change)

1. **Create Issue** (as tsaol):
   ```bash
   gh issue create --repo tsaol/languages --title "..." --body "..."
   ```

2. **Create feature branch** (as leoc-76):
   ```bash
   git checkout main && git pull origin main
   git checkout -b feature/issue-<number>-<short-description>
   ```

3. **Write code, commit to feature branch**:
   ```bash
   git add <specific files>
   git commit -m "short description"
   git push origin feature/issue-<number>-<short-description>
   ```

4. **Create PR** (referencing the issue):
   ```bash
   gh pr create --title "short description" --body "Closes #<number>"
   ```

5. **Wait for CI** (lint + test + LLM review + security scan)

6. **Review & merge** (as tsaol, after user confirms):
   ```bash
   gh pr review <number> --approve
   gh pr merge <number> --squash
   ```

7. **Deploy** (after merge):
   ```bash
   aws ssm send-command --instance-ids i-0f86894d2231b1cd0 ...
   ```

### Rules
- **NEVER** push directly to main — always use feature branch + PR
- **NEVER** skip creating an issue first
- Branch naming: `feature/issue-<number>-<short>` or `fix/issue-<number>-<short>`
- Every PR must reference an issue with `Closes #<number>`
- Ask user to confirm before merging PR
- Ask user to confirm before deploying to EC2

## EC2 Deployment
- Instance: i-0f86894d2231b1cd0
- Deploy via SSM after PR is merged:
  ```bash
  aws ssm send-command --instance-ids i-0f86894d2231b1cd0 --document-name "AWS-RunShellScript" --parameters '{"commands":["export HOME=/root && cd /home/ubuntu/languages && git pull origin main && sudo systemctl restart englearn"]}'
  ```

## Web App
- Server: http://172.16.134.84:5555
- Auth: username cc6776, password yjcsxd6
