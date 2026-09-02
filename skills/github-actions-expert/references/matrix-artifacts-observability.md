# GitHub Actions Matrix, Artifacts, and Observability

## Matrix strategies

Matrix strategies run a job multiple times with different variable combinations:

```yaml
jobs:
  test:
    strategy:
      matrix:
        node-version: ["18", "20", "22"]
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm test
```

This creates 6 jobs (3 node versions × 2 OSes), all in parallel.

Use `include` to add custom combinations or `exclude` to skip some:

```yaml
strategy:
  matrix:
    node-version: ["18", "20", "22"]
    os: [ubuntu-latest, macos-latest, windows-latest]
    exclude:
      - node-version: "18"
        os: windows-latest
```

Matrix variables are accessible as `${{ matrix.variable-name }}`.

## Artifacts

Upload build outputs, test results, or coverage reports as artifacts:

```yaml
- name: Run tests
  run: npm test
- name: Upload coverage
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: coverage-${{ matrix.os }}-node-${{ matrix.node-version }}
    path: coverage/
    retention-days: 7
```

Artifacts are downloadable from the workflow run page and from dependent jobs:

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    steps:
      - run: npm test
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ matrix.os }}
          path: coverage/

  report:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: coverage-ubuntu-latest
      - run: npm run coverage-report
```

Set `retention-days` to control storage costs. Default is 90 days.

## Test result publishing

Use GitHub's built-in test reporting:

```yaml
- name: Run tests
  run: npm test -- --reporter=json --outputFile=results.json || true
- if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: results.json
- if: always()
  uses: EnricoMi/publish-unit-test-result-action@v2
  with:
    files: results.json
```

Test reports appear in PR checks and in the workflow run summary.

## Coverage collection

Collect and track test coverage:

```yaml
- name: Run tests with coverage
  run: npm test -- --coverage
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage/coverage-final.json
    flags: unittests
    fail_ci_if_error: false
```

Coverage reports are visible in PRs and on third-party platforms like Codecov or Code Climate.

## Logs and debugging

Job and step logs are retained for the workflow run retention period (default 90 days). Access logs from the Actions tab in the GitHub UI.

For local debugging, enable debug logging with `ACTIONS_STEP_DEBUG=true`:

```yaml
- name: Debug step
  env:
    ACTIONS_STEP_DEBUG: true
  run: npm test
```

This prints full environment and command details; use only for troubleshooting, never in production.

## Status badges and workflow runs

Add a status badge to the repository README:

```markdown
[![Tests](https://github.com/owner/repo/actions/workflows/tests.yml/badge.svg)](https://github.com/owner/repo/actions)
```

Link to recent workflow runs via the Actions tab. Share specific run URLs for troubleshooting.

## Observability best practices

- Use clear, descriptive step names and job names so logs are easy to navigate.
- Print diagnostics early: `node --version`, `npm --version`, environment checks.
- Save artifacts for all important outputs: coverage, test results, build logs.
- Use `if: always()` on cleanup and reporting steps so they run even if earlier steps fail.
- Monitor workflow duration and identify slow jobs for optimization (matrix parallelization, caching).

## Verification

Inspect logs from a test workflow run. Confirm all steps produce expected output, secrets are masked, and artifacts are uploaded successfully. Use `github.run_id` and `github.run_number` to create unique artifact names across runs if needed.
