# GitHub Actions Workflow Structure

## File location and naming

Workflows live in `.github/workflows/` at the repository root. Use descriptive names matching the workflow purpose: `tests.yml`, `build-and-publish.yml`, `security-scan.yml`.

A basic workflow skeleton:

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm test
```

## Triggers

`on` defines when the workflow runs:

- `push`: commits to matching branches
- `pull_request`: PRs against matching branches
- `pull_request_target`: PRs from untrusted sources (forks), with access to main-branch secrets; requires explicit job permissions
- `workflow_dispatch`: manual trigger via the GitHub UI
- `schedule`: cron-based automation
- `workflow_call`: reusable workflows invoked by other workflows

Avoid running expensive workflows on every push. Use branch filters or path filters to narrow triggers.

## Permissions

Set `permissions` at the workflow level to limit what all jobs can access:

```yaml
permissions:
  contents: read
  pull-requests: write
  checks: write
  deployments: read
```

Job-level `permissions` override workflow-level. Default is `write` for workflows on main-branch events, `read` for pull_request events from forks; be explicit regardless.

## Jobs and runners

Each job runs on a specified `runs-on` image:

- `ubuntu-latest`, `ubuntu-22.04`, `ubuntu-20.04` for Linux
- `macos-latest`, `macos-13`, `macos-12` for macOS
- `windows-latest`, `windows-2022`, `windows-2019` for Windows

Jobs run in parallel unless linked by `needs`:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
    steps:
      - run: npm run build
      - id: version
        run: echo "version=$(cat VERSION)" >> $GITHUB_OUTPUT

  publish:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ needs.build.outputs.version }}
```

## Steps

Steps run sequentially in a job. Use `id` for referencing outputs, `if` for conditional execution, and `uses` for actions:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-node@v4
    with:
      node-version: "20"
  - name: Run tests
    run: npm test
  - if: always()
    name: Upload coverage
    uses: actions/upload-artifact@v4
    with:
      name: coverage
      path: coverage/
      retention-days: 7
```

`if` conditions check `success()`, `failure()`, `always()`, or expressions like `github.event_name == 'push'`.

## Environment variables

Set at workflow, job, or step level:

```yaml
env:
  NODE_ENV: production
jobs:
  test:
    env:
      LOG_LEVEL: debug
    steps:
      - env:
          DEBUG: "true"
        run: npm test
```

Secrets are environment variables referenced via `${{ secrets.NAME }}` and are masked in logs.

## Outputs and artifacts

Steps can output values for later use:

```yaml
- id: test
  run: echo "result=$(npm test 2>&1)" >> $GITHUB_OUTPUT
- run: echo ${{ steps.test.outputs.result }}
```

Jobs can output for dependent jobs:

```yaml
jobs:
  build:
    outputs:
      artifact-url: ${{ steps.upload.outputs.artifact-url }}
    steps:
      - id: upload
        uses: actions/upload-artifact@v4
        with:
          name: build
          path: dist/
```

Artifacts are retained for a specified number of days and can be downloaded via the UI or API.

## Expressions and contexts

GitHub Actions evaluates `${{ ... }}` expressions:

- `github.ref` - the branch or tag
- `github.event_name` - the trigger type
- `github.repository` - owner/repo
- `secrets.NAME` - a repository secret
- `steps.id.outputs.name` - a step output
- `needs.job.outputs.name` - a job output

Expressions support if conditions and string interpolation.

## Concurrency

Prevent duplicate workflows from running in parallel:

```yaml
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: true
```

The `group` key controls which workflows are considered duplicates. Setting `cancel-in-progress: true` cancels older runs.

## Verification

Validate workflow files using `yamllint` or the GitHub Actions editor in the UI. Trigger a test run on a branch before merging to main. Review the run logs to ensure all steps complete with expected output.
