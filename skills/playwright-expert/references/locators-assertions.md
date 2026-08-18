# Locators & Web-First Assertions (Playwright 1.5x)

## Locator priority

Pick the first that applies. Each step down loses resilience and accessibility signal.

| Priority | Locator | Use for |
|----------|---------|---------|
| 1 | `getByRole(role, { name })` | Anything with an ARIA role: buttons, links, headings, textboxes, rows, tabs |
| 2 | `getByLabel(text)` | Form fields with a `<label>` / `aria-label` |
| 3 | `getByPlaceholder(text)` | Inputs without labels (and flag the a11y gap) |
| 4 | `getByText(text)` | Non-interactive text nodes |
| 5 | `getByAltText` / `getByTitle` | Images, title-attribute elements |
| 6 | `getByTestId(id)` | No accessible handle exists; add `data-testid` to the app |
| last | `locator("css=...")` | Only for structural containers you cannot tag |

```ts
await page.getByRole("button", { name: "Submit" }).click();       // name = accessible name
await page.getByRole("heading", { name: /order #\d+/i, level: 2 });
await page.getByLabel("Email address").fill("qa@example.com");
await page.getByRole("checkbox", { name: "Remember me" }).check();
```

`name` matches the accessible name (visible text, `aria-label`, or `aria-labelledby`), case-insensitively by substring for strings; use a regex or `exact: true` for strict matching.

## Chaining, filtering, and combining

Scope locators instead of writing long CSS paths:

```ts
// The row containing "Refund #881", then its Approve button
const row = page.getByRole("row").filter({ hasText: "Refund #881" });
await row.getByRole("button", { name: "Approve" }).click();

// filter by a child locator, or by absence
page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Buy" }) });
page.getByRole("listitem").filter({ hasNot: page.getByText("Out of stock") });
page.getByRole("listitem").filter({ hasNotText: "Sold" });

// combine conditions
const btn = page.getByRole("button").and(page.getByTitle("Save draft"));
const dialogOrToast = page.getByRole("dialog").or(page.getByRole("status"));

// index only as a last resort - prefer filter()
page.getByRole("listitem").first();
page.getByRole("listitem").nth(2);
```

`frameLocator("iframe#payments")` scopes into iframes; chain normal locators after it.

## Strict mode

Every action/assertion requires the locator to resolve to exactly one element; multiple matches throw a strict-mode violation. Fix by narrowing (`filter`, `exact: true`, scoping under a container), not by sprinkling `.first()` - `.first()` silently pins to DOM order and breaks when order changes. Count-style assertions (`toHaveCount`, `toHaveText([...])`) accept multi-element locators.

## Auto-waiting: what actions already do

`click`, `fill`, `check`, `selectOption`, etc. wait for the element to be attached, visible, stable (not animating), enabled, and to receive pointer events. So:

- Never `waitForSelector` before an action - the action waits itself.
- Never `waitForTimeout` - it is always either redundant or masking a race.
- If a click "misses", something intercepts pointer events (overlay, animation). Find it in the trace; assert the overlay is gone first (`await expect(overlay).toBeHidden()`), don't reach for `force: true`.

## Web-first assertions (auto-retrying)

`await expect(locator).*` re-evaluates until the condition holds or times out (default 5s, override per-call with `{ timeout }` or globally via `expect.timeout` in config).

```ts
await expect(page.getByRole("status")).toHaveText("Saved");
await expect(page.getByRole("alert")).toContainText("Invalid card");
await expect(page.getByLabel("Quantity")).toHaveValue("3");
await expect(page.getByRole("row")).toHaveCount(20);
await expect(page.getByRole("button", { name: "Pay" })).toBeEnabled();
await expect(page.getByTestId("spinner")).toBeHidden();       // hidden OR detached
await expect(page).toHaveURL(/\/checkout\/success/);
await expect(page).toHaveTitle(/Receipt/);
await expect(page.getByRole("switch")).toHaveAttribute("aria-checked", "true");
await expect(page.getByTestId("card")).toHaveCSS("opacity", "1");
```

Negations also retry: `await expect(locator).not.toBeVisible()`. For "never existed vs disappeared" semantics prefer `toBeHidden()` / `toHaveCount(0)`.

**One-shot (non-retrying) checks** - `expect(await locator.textContent())`, `expect(await locator.isVisible())` - evaluate once and race the UI. Only use for values you have already awaited to a settled state.

## Asserting non-DOM conditions

```ts
// Poll an arbitrary async function until the matcher passes
await expect.poll(async () => {
  const res = await request.get("/api/jobs/42");
  return (await res.json()).status;
}, { timeout: 15_000, intervals: [500, 1000] }).toBe("done");

// Retry a block of multiple assertions/actions as a unit
await expect(async () => {
  const res = await request.get("/api/health");
  expect(res.status()).toBe(200);
}).toPass({ timeout: 10_000 });
```

## Soft assertions and steps

```ts
await expect.soft(page.getByTestId("subtotal")).toHaveText("$40");
await expect.soft(page.getByTestId("tax")).toHaveText("$3.20");
// test continues, fails at the end if any soft assertion failed

await test.step("apply coupon", async () => {
  await page.getByLabel("Coupon").fill("SAVE10");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("status")).toHaveText("Coupon applied");
}); // steps structure the trace and report
```

## Aria snapshots - structural assertions

`toMatchAriaSnapshot` asserts the accessibility tree of a region - stronger than a pixel screenshot for structure, immune to styling churn:

```ts
await expect(page.getByRole("navigation")).toMatchAriaSnapshot(`
  - navigation:
    - link "Home"
    - link "Orders"
    - button "Account"
`);
```

Generate the expected block with `npx playwright codegen` (pick "Assert snapshot") or by running once with an empty template and `--update-snapshots`. Partial templates match subsets - list only what the test cares about.

## Debugging locators

- `npx playwright test --ui` - live locator picker, DOM snapshots per action.
- `npx playwright codegen <url>` - records role-based locators; good starting point, still review the output.
- In the trace viewer, hover an action to see the locator it resolved and the before/after DOM.
- `await locator.highlight()` outlines matches during headed debugging.
