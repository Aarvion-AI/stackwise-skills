# Testing React 19 / Next.js 15 (Testing Library 16)

## Stack and setup

- **Vitest** (or Jest 29+) + `@testing-library/react` 16 + `@testing-library/user-event` 14 + `@testing-library/jest-dom` for unit/component tests.
- **Playwright** for anything that needs the real RSC pipeline: streaming, nested async Server Components, middleware, cookies.
- React 19 requires Testing Library 16+ and, for Jest, `jest-environment-jsdom` with `globalThis.IS_REACT_ACT_ENVIRONMENT` handled by the library - do not set `ReactDOMTestUtils.act` anywhere; import `act` from `react` if ever needed directly (almost never; prefer `user-event` and `findBy*`).

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
  },
});

// vitest.setup.ts
import "@testing-library/jest-dom/vitest";
```

## The layered strategy for RSC apps

jsdom cannot run the RSC protocol. Split by layer instead of fighting it:

| Layer | How to test |
|---|---|
| Client Components | `render()` + user-event in jsdom - normal Testing Library |
| Sync Server Components | `render(<Comp {...props} />)` works as a plain function of props |
| **Async** Server Components | `render(await Comp({ params: Promise.resolve({...}) }))` for shallow cases; Playwright for nested/streaming |
| Data functions (`lib/queries.ts`) | Plain unit tests, no React at all |
| Server actions | Call as functions with a constructed `FormData`; mock `next/cache`, auth |
| Full flows (form → action → revalidate → UI) | Playwright against `next dev`/`next build` |

## Testing a client component

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Counter } from "./counter";

test("increments", async () => {
  const user = userEvent.setup();          // ALWAYS setup(); no bare fireEvent
  render(<Counter />);
  await user.click(screen.getByRole("button", { name: /increment/i }));
  expect(screen.getByText("Count: 1")).toBeInTheDocument();
});
```

- Query priority: `getByRole` > `getByLabelText` > `getByText` > `getByTestId` (last resort).
- Async appearance: `await screen.findByRole(...)`; disappearance: `await waitForElementToBeRemoved(...)`. Never `waitFor` around a `getBy*` you could `findBy*`.

## Testing an async Server Component

```tsx
// page renders once its awaits resolve - call it like the async function it is
import Page from "./page";

vi.mock("@/lib/queries", () => ({
  getProduct: vi.fn().mockResolvedValue({ id: "1", name: "Boots" }),
}));

test("renders product", async () => {
  const ui = await Page({ params: Promise.resolve({ id: "1" }) }); // Next 15: params is a Promise
  render(ui);
  expect(screen.getByRole("heading", { name: "Boots" })).toBeInTheDocument();
});
```

Limits of this trick: it bypasses Suspense/streaming and any nested async children suspend forever in jsdom. If the component tree has nested async components or `use()` of server promises, cover it with Playwright instead and unit-test the data functions.

## Testing server actions

Actions are async functions - test them directly, mocking the Next runtime pieces:

```ts
import { createPost } from "./actions";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn(), revalidateTag: vi.fn() }));
vi.mock("next/navigation", () => ({
  redirect: vi.fn(() => { throw new Error("NEXT_REDIRECT"); }), // redirect throws
}));
vi.mock("@/lib/auth", () => ({ getSession: vi.fn().mockResolvedValue({ userId: "u1" }) }));

function formData(entries: Record<string, string>) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(entries)) fd.append(k, v);
  return fd;
}

test("returns field errors on invalid input", async () => {
  const state = await createPost({}, formData({ title: "", body: "" }));
  expect(state.fieldErrors?.title).toBeDefined();
});

test("rejects unauthenticated calls", async () => {
  const { getSession } = await import("@/lib/auth");
  vi.mocked(getSession).mockResolvedValueOnce(null);
  const state = await createPost({}, formData({ title: "Hi", body: "..." }));
  expect(state.error).toMatch(/signed in/i);
});
```

Testing the form + action wiring in jsdom: pass a spy action into the component (`<PostForm action={spy} />`) or mock the actions module; assert the spy received the right `FormData`. `useActionState` and `<form action>` work in jsdom with React 19 + Testing Library 16 - submit with `user.click(screen.getByRole("button", { name: /publish/i }))` and `await screen.findByRole("alert")` for returned errors.

## Mocking next/navigation and headers

```ts
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  usePathname: () => "/products",
  useSearchParams: () => new URLSearchParams("page=1"),
  redirect: vi.fn(),
  notFound: vi.fn(),
}));
```

Modules importing `server-only` throw in jsdom by design - alias it to an empty module in test config only when the file under test legitimately spans the boundary; usually the throw is telling you to test a lower layer.

## Testing TanStack Query components

Fresh client per test, retries off (otherwise failing-query tests hit the retry backoff and time out):

```tsx
function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

test("shows products", async () => {
  server.use(http.get("/api/products", () => HttpResponse.json([{ id: "1", name: "Boots" }])));
  renderWithQuery(<Products page={1} />);
  expect(await screen.findByText("Boots")).toBeInTheDocument();
});
```

Mock the network with MSW, not the `queryFn` - you want the cache/status machine in the test.

## Zustand between tests

Module-level stores leak state across tests. Reset in setup:

```ts
// vitest.setup.ts
import { useCartStore } from "@/stores/cart";
const initialCart = useCartStore.getInitialState();
afterEach(() => useCartStore.setState(initialCart, true));
```

## Playwright for the RSC layer

```ts
test("create post end to end", async ({ page }) => {
  await page.goto("/posts/new");
  await page.getByLabel("Title").fill("Hello");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page).toHaveURL(/\/posts\/[\w-]+/);   // redirect() from the action
  await expect(page.getByRole("heading", { name: "Hello" })).toBeVisible();
});
```

Run against `next build && next start` in CI - dev mode hides streaming/caching behavior differences. Hand off deeper E2E patterns to the playwright-expert skill.

## What NOT to do

- No `ReactDOM.render`/enzyme/shallow rendering - dead APIs.
- No asserting on implementation details (state values, internal function calls); assert what the user sees via roles and accessible names.
- No `fireEvent` when `user-event` works - `user-event` fires the full event sequence (pointer, focus, keyboard) real browsers produce.
- No snapshot tests of whole pages; they fail on every copy change and verify nothing.
- Do not test the React Compiler's memoization or `"use client"` placement in unit tests - the build (`next build`) is the verifier for boundaries.
