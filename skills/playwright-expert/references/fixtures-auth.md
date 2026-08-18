# Fixtures, storageState Auth & Page Objects (Playwright 1.5x)

## storageState auth: login once per run

The canonical setup - a `setup` project logs in and saves cookies + localStorage; browser projects depend on it and load the saved state. Specs never see the login form.

```ts
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  projects: [
    { name: "setup", testMatch: /.*\.setup\.ts/ },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },
    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },
  ],
});
```

```ts
// e2e/auth.setup.ts
import { test as setup, expect } from "@playwright/test";

const authFile = "playwright/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.E2E_USER!);
  await page.getByLabel("Password").fill(process.env.E2E_PASS!);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Wait until auth actually completed - cookies are set after redirect
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.context().storageState({ path: authFile });
});
```

Add `playwright/.auth/` to `.gitignore`. If login is API-based, do it faster without a page:

```ts
setup("authenticate", async ({ request }) => {
  await request.post("/api/login", {
    data: { email: process.env.E2E_USER, password: process.env.E2E_PASS },
  });
  await request.storageState({ path: authFile });
});
```

### Multiple roles

One setup test per role, one state file per role. Whole files pick a role with `test.use`:

```ts
// admin.spec.ts
import { test, expect } from "@playwright/test";
test.use({ storageState: "playwright/.auth/admin.json" });
```

For mixing roles inside one test, open a second context:

```ts
const adminContext = await browser.newContext({
  storageState: "playwright/.auth/admin.json",
});
const adminPage = await adminContext.newPage();
```

An unauthenticated test opts out with `test.use({ storageState: { cookies: [], origins: [] } })`.

### Per-worker accounts (parallel-safe mutations)

When tests mutate account-scoped data, share nothing: give each parallel worker its own user via a worker-scoped fixture keyed on `parallelIndex`.

```ts
// fixtures.ts
import { test as base, expect } from "@playwright/test";

export const test = base.extend<{}, { workerStorageState: string }>({
  storageState: ({ workerStorageState }, use) => use(workerStorageState),
  workerStorageState: [
    async ({ browser }, use) => {
      const id = test.info().parallelIndex;
      const fileName = `playwright/.auth/worker-${id}.json`;
      const page = await browser.newPage({ storageState: { cookies: [], origins: [] } });
      await page.goto("/login");
      await page.getByLabel("Email").fill(`e2e-worker-${id}@example.com`);
      await page.getByLabel("Password").fill(process.env.E2E_PASS!);
      await page.getByRole("button", { name: "Sign in" }).click();
      await expect(page.getByRole("navigation")).toBeVisible();
      await page.context().storageState({ path: fileName });
      await page.close();
      await use(fileName);
    },
    { scope: "worker" },
  ],
});
```

Session expiry note: storageState is captured once per run; if tokens are short-lived, refresh in the setup project (it re-runs each invocation) - do not re-login per test.

## Custom fixtures with test.extend

Fixtures are the composition mechanism: setup + teardown + typed injection, only instantiated when a test uses them.

```ts
// fixtures.ts
import { test as base } from "@playwright/test";
import { CheckoutPage } from "./pages/checkout-page";

type Fixtures = {
  checkoutPage: CheckoutPage;
  seededOrder: { id: string };
};

export const test = base.extend<Fixtures>({
  checkoutPage: async ({ page }, use) => {
    await use(new CheckoutPage(page)); // POMs are built BY fixtures
  },
  seededOrder: async ({ request }, use) => {
    const res = await request.post("/api/test/orders", { data: { items: 2 } });
    const order = await res.json();
    await use(order);                                  // test runs here
    await request.delete(`/api/test/orders/${order.id}`); // teardown always runs
  },
});
export { expect } from "@playwright/test";
```

```ts
// checkout.spec.ts
import { test, expect } from "./fixtures";

test("pays for a seeded order", async ({ checkoutPage, seededOrder }) => {
  await checkoutPage.goto(seededOrder.id);
  await checkoutPage.payWithCard("4242 4242 4242 4242");
  await expect(checkoutPage.confirmation).toContainText(seededOrder.id);
});
```

Fixture options:

- `{ scope: "worker" }` - created once per worker process (DB pools, seeded tenants, auth above).
- `{ auto: true }` - runs for every test without being requested (e.g., fail test on console errors).
- Option fixtures (`[value, { option: true }]`) become configurable via `test.use` / project `use`.

```ts
// auto fixture: fail any test that logs a browser error
errorWatcher: [async ({ page }, use) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await use();
  expect(errors, "uncaught page errors").toEqual([]);
}, { auto: true }],
```

## POM vs fixture composition

- **Page Object Model**: a class per page/component holding locators and action methods. Good for large apps with many screens; keeps locators in one place.
- **Fixtures**: own lifecycle (setup/teardown), typing, and injection. They *deliver* POMs and test data; they do not replace them.
- Rule of thumb: locators and user actions → POM methods; environment state (auth, seeded data, mocked routes) → fixtures; a fixture constructs each POM so specs import only `test`/`expect`.
- Keep POM methods action-shaped (`addToCart(sku)`), and expose locators as public readonly properties for assertions - assert in specs, not inside the POM, so failures read at the right level.

```ts
export class CheckoutPage {
  readonly confirmation;
  constructor(private page: Page) {
    this.confirmation = page.getByRole("status");
  }
  async goto(orderId: string) {
    await this.page.goto(`/checkout/${orderId}`);
  }
  async payWithCard(number: string) {
    await this.page.getByLabel("Card number").fill(number);
    await this.page.getByRole("button", { name: "Pay now" }).click();
  }
}
```
