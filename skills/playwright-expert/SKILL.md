---
name: playwright-expert
description: Use when writing or fixing E2E tests in a Playwright project - playwright.config.ts, *.spec.ts files under tests/ or e2e/, @playwright/test imports - or right after implementing a frontend/backend change that needs an end-to-end proof. Writes and extends TypeScript E2E suites as the QA gate for feature and bug-fix work, stabilizes flaky tests, sets up storageState auth, mocks the network with page.route/HAR, and wires parallel/sharded CI. Invoke for adding E2E coverage for a change, converting waitForTimeout/CSS-selector tests to web-first assertions and role locators, diagnosing flake with the trace viewer, adding toHaveScreenshot visual checks, and configuring sharded CI runs.
license: MIT
metadata:
  version: "0.1.0"
  category: qa
  frameworks: "Playwright 1.5x (@playwright/test, TypeScript)"
  triggers: playwright, e2e, end-to-end test, spec.ts, playwright.config, getByRole, locator, web-first assertions, toHaveScreenshot, storageState, page.route, HAR, trace viewer, flaky test, sharding, visual regression
  related: react-expert, vue-expert, nestjs-expert, fastapi-expert
---

# Playwright Expert

Turns Claude into a senior QA engineer who treats Playwright as the merge gate: every feature or bug fix ships with an E2E test that proves it, built on web-first assertions, user-facing locators, and fixtures - never sleeps, never brittle selectors.

## When to Use This Skill

- Write or extend the E2E test that proves a just-implemented feature or bug fix works end to end
- Convert brittle tests (CSS/XPath selectors, `waitForTimeout`, manual polling) to role locators and web-first assertions
- Set up authentication with `storageState` so the suite logs in once per project, not once per test
- Mock or record network traffic with `page.route`, `route.fetch`, or HAR replay to isolate the frontend
- Diagnose and fix flaky tests using traces - treat retries as a symptom, not a fix
- Configure parallelism, sharding, and blob-report merging for CI
- Add visual regression checks with `toHaveScreenshot` and masking for dynamic content

## Core Workflow

1. **Analyze** - Read `playwright.config.ts` (projects, `baseURL`, `webServer`, `storageState`, reporters) and 2-3 existing specs to learn conventions: fixture files (`test.extend` in a `fixtures.ts`), POM classes, `data-testid` naming, auth setup project. Identify which project/spec the new coverage belongs in. Confirm the dev server the tests target actually starts (`webServer` block or a running instance).
2. **Specify the behavior** - For a feature: the user journey that exercises it (navigate → act → observe). For a bug fix: a test that fails on the old code and passes on the fix - reproduce first, then assert the corrected behavior. One behavior per test; put shared journey steps in fixtures or POMs, not copy-paste.
3. **Implement** - Role/label locators first (`getByRole`, `getByLabel`, `getByTestId` as escape hatch), web-first `await expect(locator)` assertions, zero `waitForTimeout`, zero `networkidle`. Isolate external/slow dependencies with `page.route` or HAR. Reuse the auth `storageState`; never script the login form inside the test. Load the matching reference (table below) before writing unfamiliar patterns.
4. **Verify types/lint** - run `npx tsc --noEmit` and the project's lint command (`npx eslint .`); fix all reported issues and re-run until clean before proceeding.
5. **Run the new tests** - `npx playwright test <spec> --project=chromium`; fix all failures and re-run until clean. Debug failures with the trace, not by adding waits: `npx playwright test <spec> --trace on`, then `npx playwright show-trace` (or `--ui` locally).
6. **Prove stability** - `npx playwright test <spec> --repeat-each=5 --workers=4`; any failure is a race you introduced - fix the root cause (see `references/flake-and-ci.md`) and re-run until all repeats pass. Never "fix" this step with retries or timeouts.
7. **Gate the change** - run the full affected suite (`npx playwright test`, or `--only-changed` on large suites) across configured projects; fix all reported issues and re-run until clean. Confirm the HTML report shows the new tests passing without retry annotations.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Locator strategy, chaining/filtering, web-first assertions, `expect.poll`/`toPass`, aria snapshots | `references/locators-assertions.md` | Writing any new test, replacing CSS/XPath selectors, fixing "element not found"/strict-mode violations, asserting async state |
| Custom fixtures, `storageState` auth setup project, multi-role login, POM vs fixture composition | `references/fixtures-auth.md` | Suite needs login, tests repeat setup steps, adding a fixtures file, choosing between POM classes and fixtures |
| `page.route`, `route.fetch` modification, HAR record/replay, WebSocket routing, request assertions | `references/network-mocking.md` | Isolating the UI from a backend, testing error/edge responses, third-party APIs in tests, deterministic data |
| Flake diagnosis with traces, root-cause table, retries policy, CI workers/sharding/blob reports | `references/flake-and-ci.md` | A test fails intermittently, configuring CI, slow pipeline, `--shard`/merge-reports, choosing retry counts |
| `toHaveScreenshot` options, masking, snapshot updates, cross-platform snapshots in Docker, aria vs pixel checks | `references/visual-regression.md` | Adding/updating screenshot tests, snapshot diffs on CI only, masking dynamic regions, visual review of a UI change |

## Key Patterns

**Web-first assertion instead of wait-then-check (the #1 conversion):**

```ts
// BAD - checks once, races the UI, needs a sleep to "work"
await page.waitForTimeout(2000);
expect(await page.locator(".toast").textContent()).toBe("Saved");

// GOOD - auto-retries until pass or timeout; no sleep anywhere
await expect(page.getByRole("status")).toHaveText("Saved");
```

**Role locators scoped by filtering, not CSS paths:**

```ts
const row = page.getByRole("row").filter({ hasText: "invoice-2026-08" });
await row.getByRole("button", { name: "Approve" }).click();
await expect(row.getByRole("cell", { name: "Approved" })).toBeVisible();
```

**Login once per run via a setup project, reuse everywhere:**

```ts
// auth.setup.ts - runs once; specs never see the login form
setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.E2E_USER!);
  await page.getByLabel("Password").fill(process.env.E2E_PASS!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.context().storageState({ path: "playwright/.auth/user.json" });
});
// playwright.config.ts: chromium project has
//   { dependencies: ["setup"], use: { storageState: "playwright/.auth/user.json" } }
```

**Deterministic backend edge case via route interception:**

```ts
await page.route("**/api/orders", (route) =>
  route.fulfill({ status: 500, json: { error: "upstream timeout" } })
);
await page.goto("/orders");
await expect(page.getByRole("alert")).toContainText("try again");
```

## Common Mistakes

- **`waitForTimeout` anywhere.** It hides a race and sets a floor on suite time. Replace with a web-first assertion on the condition being waited for; for non-DOM conditions use `await expect.poll(() => fn()).toBe(x)` or `await expect(async () => {...}).toPass()`.
- **CSS/XPath selectors copied from DevTools** (`.MuiButton-root > span`, `div:nth-child(3)`). They break on every refactor and assert nothing about the user experience. Use `getByRole`/`getByLabel`; add `data-testid` to the app only when no accessible handle exists.
- **Logging in inside every test.** Multiplies runtime and flake surface. Use a `setup` project writing `storageState` once per role; per-test UI login is only for tests *about* the login flow.
- **Adding `retries` (or bumping timeouts) to "fix" flake.** Retries are detection - a test that passes on retry is still broken. Pull the trace from the failed attempt, find the race, fix the test or the app.
- **`waitForNavigation`/`networkidle` waits.** `waitForNavigation` is deprecated and `networkidle` is unreliable on apps with polling/websockets. Assert on the destination instead: `await expect(page).toHaveURL(/\/dashboard/)` plus a visible landmark.
- **Asserting non-existence with `toBeVisible()` negation done once** via `expect(await locator.isVisible()).toBe(false)` - passes even while the element is still rendering. Use `await expect(locator).toBeHidden()` or `toHaveCount(0)`.
- **Unawaited `expect`.** Web-first assertions return promises; a missing `await` makes the test pass vacuously. Enable `@typescript-eslint/no-floating-promises` (or `eslint-plugin-playwright`) so the linter catches it in step 4.
- **Sharing signed-in state across tests that mutate the same account data** with `fullyParallel` on. Give each worker its own account (worker-scoped fixture keyed on `test.info().parallelIndex`) or make tests idempotent.
