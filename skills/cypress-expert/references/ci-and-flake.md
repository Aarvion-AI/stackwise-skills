# Cypress CI, Flake, and Artifacts

## Headless baseline

Use a reproducible browser command in CI:

```bash
npx cypress run --browser chrome --headless --reporter junit --reporter-options "mochaFile=artifacts/cypress-[hash].xml"
```

Pin the Node and browser environment in CI. Cache the package manager cache, not an opaque Cypress binary across incompatible runners.

## Web server lifecycle

Start the application before Cypress and fail if it cannot bind. A typical package script uses a wait utility:

```json
{
  "scripts": {
    "test:e2e": "start-server-and-test start http://localhost:3000 cy:run"
  }
}
```

The health URL must prove the app is ready, not merely that a process exists. Use a dedicated test database and synthetic credentials.

## Evidence

Keep screenshots and videos for failures. Publish JUnit results, screenshots, videos, and the Cypress command log as CI artifacts. Redact tokens from environment variables and never upload a recording containing real customer data.

## Parallelization

Split by spec files only when tests are isolated and the CI plan can merge results. Cypress Cloud can balance specs across machines with a recorded run and a project record key. Recording or paid cloud usage requires explicit approval.

Do not reduce coverage to make parallel jobs faster. First measure slow specs, then split at stable boundaries.

## Flake diagnosis

1. Re-run the failed spec locally in the same browser and viewport.
2. Inspect the command log and failure screenshot.
3. Determine whether the race is app readiness, an ambiguous query, shared state, an uncontrolled network, or an environment difference.
4. Make the smallest root-cause fix.
5. Re-run the focused spec repeatedly until it passes consistently, then run the affected suite.

Retries may expose intermittent failures in CI, but they must not hide them. Track retry annotations and treat any retry as a defect to resolve.

## Common CI differences

- Headless rendering can expose viewport assumptions.
- Timezone and locale can alter date and number assertions.
- Parallel workers can collide through shared accounts or records.
- Missing OS dependencies can fail before the first test command.
- Secrets may be absent or intentionally unavailable on forked pull requests.

Prefer fixed test data, explicit viewport and locale settings, isolated records, and clear preflight errors.

## Verification

Run the exact CI command locally when possible; fix every reported failure and re-run until clean. Then confirm the CI artifact paths contain the failure evidence expected by reviewers.