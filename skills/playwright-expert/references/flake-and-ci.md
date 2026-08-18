# Flake Diagnosis & CI Configuration (Playwright 1.5x)

## Retries are a smoke detector, not a fix

Configure `retries` in CI so flake is *detected and labeled* (the HTML report marks tests "flaky" when they pass on retry). A flaky-but-green build is a failing build you haven't debugged yet. Never raise retries or timeouts to make a red test green - pull the trace and fix the race.

```ts
// playwright.config.ts
export default defineConfig({
  retries: process.env.CI ? 2 : 0,   // 0 locally: see failures immediately
  forbidOnly: !!process.env.CI,      // fail CI if test.only leaked in
  use: { trace: "on-first-retry", screenshot: "only-on-failure", video: "retain-on-failure" },
});
```

`test.info().retry` tells a test which attempt it is (occasionally useful for extra cleanup on retry). `test.fail()` / `test.fixme()` mark known-broken tests explicitly instead of letting them burn retries.

## Diagnosis workflow

1. **Get the trace.** CI: `trace: "on-first-retry"` produces a trace for the failed first attempt; download the report artifact and run `npx playwright show-report` (traces open from the report) or `npx playwright show-trace trace.zip`. Local: reproduce with `npx playwright test <spec> --trace on`, or watch live in `--ui`.
2. **Read the failure line in the trace timeline.** Every action shows before/after DOM snapshots, the resolved locator, console, and network. The racing state is visible - you see exactly what the page looked like when the action fired.
3. **Reproduce the race locally.** `--repeat-each=10 --workers=4` amplifies ordering races; `--last-failed` re-runs only what failed last run.
4. **Fix the root cause** (table below), then prove it: repeat step 3 until 0 failures - fix all reported issues and re-run until clean.

## Root causes and their real fixes

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| Passes alone, fails in the suite | Shared server state between tests | Isolate data per test/worker (API seeding fixture, `parallelIndex`-keyed accounts) |
| Click has no effect sometimes | Element re-rendered/animated during click | Assert the settled state first (`await expect(btn).toBeEnabled()`); disable app animations in test env |
| "Element not found" intermittently | Assertion raced data loading | Web-first assertion on the loaded content, not a one-shot check after `goto` |
| Fails only on CI | CI is slower; timeouts tuned to laptop | Remove hard waits; rely on auto-retrying assertions; raise `expect.timeout` only if the app is legitimately slow |
| Fails at specific times / dates | Real clock in test | `await page.clock.install({ time: new Date("2026-08-18T10:00:00") })`, drive time with `page.clock.fastForward()` / `runFor()` |
| Random third-party timeouts | Analytics/ads/CDN on the critical path | `page.route` abort for third parties (see network-mocking reference) |
| `networkidle` waits hang or pass early | Polling/websockets never idle | Delete the wait; assert on visible landmarks instead |
| First test in a worker is slow/flaky | Cold dev server | `webServer` block with a real readiness `url`, not a fixed sleep |

## Timeouts: the hierarchy

- `timeout` (per test, default 30s) > `expect.timeout` (per assertion, default 5s) > action timeout (default: no limit below test timeout).
- Prefer fixing the wait to raising a timeout. When something is legitimately slow (report generation), scope it: `test.slow()` (triples the test timeout) or a per-assertion `{ timeout: 30_000 }` - not a global bump.

## Parallelism

Playwright parallelizes across **worker processes**; each worker gets fresh browser contexts per test.

```ts
export default defineConfig({
  fullyParallel: true,               // parallelize tests inside each file too
  workers: process.env.CI ? "50%" : undefined,
});
```

- Default without `fullyParallel`: files run in parallel, tests within a file run in order.
- `test.describe.configure({ mode: "serial" })` chains dependent tests (a failure skips the rest) - use sparingly; serial groups are a flake-and-runtime smell. `mode: "default"` opts a file back into in-order execution when the suite is `fullyParallel`.
- Anything shared across tests (accounts, seeded rows, files on disk) must be worker-scoped or unique per test. This is the #1 source of parallel-only flake.

## Sharding + merged report (GitHub Actions)

Shards split the suite across machines; the blob reporter lets you merge one HTML report afterwards.

```yaml
jobs:
  test:
    strategy:
      fail-fast: false
      matrix: { shard: [1, 2, 3, 4] }
    container: mcr.microsoft.com/playwright:v1.55.0-noble   # pin to installed @playwright/test version
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx playwright test --shard=${{ matrix.shard }}/4
        env: { CI: true }
      - uses: actions/upload-artifact@v4
        if: ${{ !cancelled() }}
        with: { name: blob-report-${{ matrix.shard }}, path: blob-report, retention-days: 7 }

  merge-report:
    if: ${{ !cancelled() }}
    needs: [test]
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - uses: actions/download-artifact@v4
        with: { path: all-blob-reports, pattern: blob-report-*, merge-multiple: true }
      - run: npx playwright merge-reports --reporter html ./all-blob-reports
      - uses: actions/upload-artifact@v4
        with: { name: html-report, path: playwright-report }
```

```ts
reporter: process.env.CI ? [["blob"], ["github"]] : [["html", { open: "never" }], ["list"]],
```

Notes:

- Run in the official Playwright Docker image (or `npx playwright install --with-deps`) - matching image tag to package version avoids browser/host skew, and matters for screenshot tests.
- `--only-changed=origin/main` runs tests affected by the diff - good for PR gates on big suites; keep the full run on main.
- `maxFailures: 10` (or `-x` locally) stops runaway broken builds early.
- Flaky-tracking: `merge-reports` + the JSON reporter feed dashboards; quarantine via `test.fixme` with a ticket, never by deleting the assertion.

## webServer: let Playwright own the app lifecycle

```ts
webServer: {
  command: "npm run start:test",
  url: "http://localhost:3000/healthz",   // polled until 2xx - no sleep loops
  reuseExistingServer: !process.env.CI,
  timeout: 120_000,
},
use: { baseURL: "http://localhost:3000" },
```

Multiple entries (array) start frontend + backend together. `reuseExistingServer` keeps local iteration fast while CI always gets a fresh server.
