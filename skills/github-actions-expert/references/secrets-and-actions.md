# GitHub Actions Secrets and Third-Party Actions

## Secret handling

Secrets are environment variables stored in repository settings and passed into workflows. Always use secrets for tokens, API keys, credentials, and signing keys.

In a workflow, reference a secret with `${{ secrets.NAME }}`. GitHub automatically masks the value in logs.

```yaml
- name: Publish to npm
  run: npm publish
  env:
    NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

Never hardcode secrets in YAML, commit them to the repository, or pass them as command arguments where they might appear in logs.

For pull requests from forks, secrets are not available by default. Use `pull_request_target` only when necessary and with explicit, minimal permissions:

```yaml
on:
  pull_request_target:
    branches: [main]

permissions:
  contents: read
  pull-requests: read
  checks: write

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: 'Workflow completed'
            })
```

## Third-party actions

Third-party actions from GitHub Marketplace should be pinned by commit SHA for reproducibility:

```yaml
- uses: actions/setup-node@e64de3d8b89b74b59303b8c47765681605f73add  # v4.0.0
```

Alternatively, use semantic version tags if the action author commits tags reliably:

```yaml
- uses: actions/setup-node@v4
```

Avoid `main` and `latest` tags; they can be force-pushed and change behavior unexpectedly.

Review the action's source repository before using it. Understand what permissions it requests and what it does with repository data.

For security-critical workflows, fork and maintain your own copy of an action, or use GitHub's official actions (github.com/actions).

## Environment-specific secrets and variables

Use environment configurations to manage different settings per branch or deployment target:

```yaml
jobs:
  deploy:
    environment:
      name: production
      url: https://app.example.com
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run deploy
        env:
          API_KEY: ${{ secrets.PRODUCTION_API_KEY }}
```

Production environments can require reviewer approval before the workflow proceeds.

## OIDC and passwordless authentication

Use OpenID Connect (OIDC) to exchange GitHub tokens for cloud provider credentials without storing long-lived secrets:

```yaml
- uses: actions/checkout@v4
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/github-actions
    aws-region: us-east-1
- run: aws s3 cp app.zip s3://bucket/app.zip
```

OIDC is more secure than storing AWS access keys as secrets.

## Branch and event filtering

Use `if` conditions to run steps only on specific events or branches:

```yaml
- if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  name: Deploy to production
  run: npm run deploy
- if: github.event_name == 'pull_request'
  name: Run tests
  run: npm test
```

This prevents accidental deployments from PR branches or manual triggers.

## Verification

Validate secret references by running the workflow and checking the logs. Do not print secret values; confirm they are masked. Test fork workflows separately with reduced permissions to ensure they fail safely if secrets are unavailable.
