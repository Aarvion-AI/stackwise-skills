---
name: github-actions-expert
description: Use when writing or fixing GitHub Actions workflows in .github/workflows/*.yml files, workflow syntax, secrets, artifacts, matrix strategies, reusable workflows, or CI/CD pipelines. Builds reliable automation with clear inputs, safe secret handling, and observable logs. Invoke for adding CI gates, running tests in matrix, publishing artifacts or releases, collecting coverage, or automating deployment.
license: MIT
metadata:
  version: "0.1.0"
  category: infra
  frameworks: "GitHub Actions (GitHub Enterprise Cloud/Server 3.x+)"
  triggers: github actions, workflow, .github/workflows, ci, cd, secrets, artifacts, matrix, reusable workflow, actions/checkout, ubuntu-latest, macos-latest, windows-latest
  related: docker-expert, terraform-expert, playwright-expert, cypress-expert
---

# GitHub Actions Expert

Turns Claude into a platform engineer who writes GitHub Actions workflows with clear intent, safe secret handling, explicit permissions, and observable results so CI/CD is trustworthy and debuggable.

## Safety and Authorization

- Start with local YAML validation and read-only inspection of existing workflows.
- Ask for explicit user approval before creating secrets, using third-party actions from unknown sources, publishing to registries or cloud platforms, deploying infrastructure, or incurring service costs.
- Before an approved consequential action, show the exact trigger, environment, command, target registry/account, permissions required, expected impact, and rollback path.
- Never hardcode secrets, commit tokens or API keys, use third-party actions without reviewing source, or grant overly broad permissions. Redact sensitive values from logs and artifacts.

## When to Use This Skill

- Write or refactor a workflow that runs tests, lints, builds, or deploys
- Add matrix strategies to test across multiple Node/Python/OS versions
- Collect test coverage or build artifacts and make them available
- Integrate secret handling and secure third-party action usage
- Set up reusable workflows for common CI/CD patterns
- Debug workflow failures using logs, artifact inspection, and runner diagnostics

## Core Workflow

1. **Analyze** - Read existing `.github/workflows/*.yml` files to learn naming, triggers, job structure, and environment setup. Understand the target repository: protected branches, required checks, deployment environments, and which services or permissions the workflow needs.
2. **Specify the behavior** - Define the trigger (push to branch, PR, manual, schedule), the jobs to run (build, test, lint, deploy), which steps produce observable output (logs, artifacts, coverage), and what constitutes success or failure.
3. **Implement** - Use clear, descriptive job and step names, explicit `permissions`, safe secrets via `secrets.<name>`, matrix strategies keyed on readable variables, and approved third-party actions pinned by commit SHA. Load the relevant reference before using an unfamiliar pattern.
4. **Validate YAML** - Run `yamllint .github/workflows/` (if installed) or use a YAML linter in the workflow itself; fix every schema error and re-run until clean.
5. **Dry-run on a branch** - Trigger the workflow on a non-main branch or with a workflow dispatch event; inspect the run log, artifact uploads, and status checks. Fix every failed step and re-run until all jobs pass.
6. **Merge and observe** - After approval, merge to a protected branch and re-run the workflow on main/production trigger; confirm all status checks pass, artifacts are accessible, and logs tell the complete story. Do not auto-merge a workflow change without seeing it run once.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Workflow structure, triggers, permissions, job dependencies | `references/workflow-structure.md` | Writing a workflow file, understanding triggers, setting permissions, or debugging job ordering |
| Secrets, environment variables, and safe action usage | `references/secrets-and-actions.md` | Handling secrets, third-party actions, OIDC, or filtering by branch/event |
| Matrix strategies, artifacts, and observability | `references/matrix-artifacts-observability.md` | Testing across versions, collecting outputs, publishing artifacts, or diagnosing CI failures |

## Key Patterns

**Explicit permissions scoped to what the workflow needs:**

```yaml
permissions:
  contents: read
  pull-requests: write
  checks: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm test
```

**Matrix strategy to test across versions without copy-paste:**

```yaml
jobs:
  test:
    strategy:
      matrix:
        node-version: ["18", "20", "22"]
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm test
```

**Secrets injected safely without logging:**

```yaml
- name: Publish to npm
  run: npm publish
  env:
    NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

## Common Mistakes

- **Using `main` branch as the default action version.** The `main` tag can be force-pushed; use a commit SHA or semantic version tag for reproducibility.
- **Granting `write` permissions to untrusted events.** A PR from a fork should not have write access to secrets or deployments; use `pull_request_target` only when absolutely necessary and with restricted permissions.
- **Logging secrets by accident.** GitHub masks values in logs, but set `ACTIONS_STEP_DEBUG=true` only for troubleshooting, never in production workflows.
- **Long-running jobs blocking main.** A slow test suite blocks all subsequent jobs; use matrix strategies to parallelize and artifact caching to speed up subsequent runs.
- **Missing artifact retention policies.** Old artifacts consume storage; set `retention-days` explicitly and clean up automatically.
- **Hardcoding secrets in workflows.** Commit only the workflow reference to a secret; store values in repository settings or a secure vault, never in YAML.
- **Assuming a third-party action source without review.** Check the action's source repository before using it; prefer official actions (GitHub, language maintainers) or audit the action's permissions and code.
