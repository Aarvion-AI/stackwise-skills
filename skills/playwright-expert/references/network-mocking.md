# Network Mocking: page.route, route.fetch, HAR (Playwright 1.5x)

Mock the network to make E2E tests deterministic: force error paths, freeze third-party APIs, and test UI states the real backend won't produce on demand. Keep at least a smoke path unmocked so the real contract is still exercised somewhere.

## page.route basics

Register **before** the navigation/action that triggers the request. Patterns are glob (relative to `baseURL`) or regex; last-registered matching handler runs first.

```ts
// Stub a JSON API
await page.route("**/api/products", (route) =>
  route.fulfill({ json: [{ id: 1, name: "Widget", price: 40 }] })
);

// Force an error state
await page.route("**/api/orders", (route) =>
  route.fulfill({ status: 500, json: { error: "upstream timeout" } })
);

// Kill third-party noise (analytics, ads) - big flake reducer
await page.route(/(googletagmanager|analytics|sentry)\./, (route) => route.abort());

// Block images for speed on content-heavy suites
await page.route("**/*.{png,jpg,jpeg,webp}", (route) => route.abort());

await page.goto("/products");
await expect(page.getByRole("listitem")).toHaveCount(1);
```

`route.fulfill` accepts `status`, `headers`, `contentType`, `body` (string/Buffer), `json`, or `path` (serve a file from disk). `route.continue()` passes through, optionally overriding `url`, `method`, `headers`, `postData`:

```ts
await page.route("**/api/**", (route) =>
  route.continue({ headers: { ...route.request().headers(), "x-e2e": "1" } })
);
```

`route.fallback()` defers to the next (earlier-registered) handler - use it in handlers that only modify headers so more specific mocks still apply.

## Modify real responses with route.fetch

Let the real backend answer, then patch the payload - ideal for "what if this field were huge/null/missing" cases without stubbing the whole shape:

```ts
await page.route("**/api/profile", async (route) => {
  const response = await route.fetch();
  const json = await response.json();
  json.subscription = { tier: "enterprise", seats: 5000 };
  await route.fulfill({ response, json });
});
```

## Context-wide routing and unrouting

```ts
// Applies to every page in the context (popups included)
await context.route("**/api/flags", (route) =>
  route.fulfill({ json: { newCheckout: true } })
);

await page.unroute("**/api/flags");     // remove a specific handler
await page.unrouteAll({ behavior: "wait" }); // teardown: wait for in-flight handlers
```

In fixtures, register routes in setup and call `unrouteAll` in teardown so handlers never leak across tests.

## HAR record and replay

Record real traffic once, replay it for hermetic runs.

```ts
// Replay (mocks matching requests from the HAR file)
await page.routeFromHAR("e2e/hars/products.har", {
  url: "**/api/**",     // only mock API calls; let assets hit the network
  update: false,
});
```

Re-record by flipping `update: true` (performs real requests and rewrites the HAR), or via CLI: `npx playwright open --save-har=e2e/hars/products.har --save-har-glob="**/api/**" https://app.example.com`. Options: `updateMode: "minimal"` (default; strips volatile headers) vs `"full"`; `notFound: "abort"` (default) vs `"fallback"` to pass unmatched requests through. Review recorded HARs for tokens/PII before committing.

## Waiting for and asserting requests

Start waiting **before** the triggering action to avoid a race - the promise-first pattern:

```ts
const responsePromise = page.waitForResponse(
  (res) => res.url().includes("/api/orders") && res.request().method() === "POST"
);
await page.getByRole("button", { name: "Place order" }).click();
const response = await responsePromise;
expect(response.status()).toBe(201);
expect(await response.json()).toMatchObject({ status: "pending" });
```

Prefer asserting the resulting UI (`await expect(page.getByRole("status")).toHaveText("Order placed")`) when possible; assert the wire only when the UI can't distinguish the behavior (e.g., correct payload fields, retry counts).

```ts
// Capture the outgoing payload
const [request] = await Promise.all([
  page.waitForRequest("**/api/track"),
  page.getByRole("button", { name: "Export" }).click(),
]);
expect(request.postDataJSON()).toMatchObject({ event: "export_clicked" });
```

## WebSocket routing

`routeWebSocket` intercepts socket connections; by default the server is never contacted - you mock it.

```ts
await page.routeWebSocket("**/ws/notifications", (ws) => {
  ws.onMessage((message) => {
    if (message === "subscribe:orders") {
      ws.send(JSON.stringify({ type: "order_update", id: 42, status: "shipped" }));
    }
  });
});
await page.goto("/dashboard");
await expect(page.getByRole("status")).toContainText("Order 42 shipped");
```

To proxy-and-tamper instead, call `ws.connectToServer()` and forward selectively.

## Backend-direct calls with APIRequestContext

The `request` fixture makes real HTTP calls with the browser context's cookies - use it to *arrange* state fast (seed/cleanup via API) rather than clicking through the UI, and for pure API contract tests:

```ts
test("cart badge reflects API-seeded cart", async ({ page, request }) => {
  await request.post("/api/cart/items", { data: { sku: "W-1", qty: 3 } });
  await page.goto("/");
  await expect(page.getByTestId("cart-badge")).toHaveText("3");
});
```

## Rules of thumb

- Mock at the **network boundary**, not inside app code - no test-only branches in the app bundle.
- Stub shapes must match the real API (copy from a HAR or the OpenAPI spec); a drifted mock tests a UI against a backend that no longer exists.
- Routes registered on `page` do not apply to requests made by service workers; set `serviceWorkers: "block"` in `use` if a SW swallows your mocks.
- One deliberate unmocked E2E happy path per critical flow keeps mocks honest.
