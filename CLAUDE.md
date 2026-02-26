# Project Rules for Claude

## Collaboration
This project uses GitHub Flow. See ~/.claude/collaboration.yml for roles and workflow details.

**Key rule: NEVER push directly to main. Always use feature branch + PR.**

## EC2 Deployment
- Instance: i-0f86894d2231b1cd0
- Deploy via SSM after PR is merged:
  ```bash
  aws ssm send-command --instance-ids i-0f86894d2231b1cd0 --document-name "AWS-RunShellScript" --parameters '{"commands":["export HOME=/root && cd /home/ubuntu/languages && git pull origin main && sudo systemctl restart englearn"]}'
  ```

## Web App
- Server: http://172.16.134.84:5555
- Auth: username cc6776, password yjcsxd6
