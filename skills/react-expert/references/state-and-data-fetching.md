# State Management and Client Data Fetching

## Decision table

| State kind | Tool |
|---|---|
| Data from the server (lists, entities) | Server Components fetch; TanStack Query only if it must update client-side |
| Form/mutation state | `useActionState` + server actions (see `forms-and-actions.md`) |
| Local component state | `useState` / `useReducer` |
| Shareable UI state that belongs in the URL (filters, tabs, pagination) | `searchParams` via `useRouter`/`useSearchParams` (or the `nuqs` library) |
| Cross-component client state (cart, panels, multi-step wizard) | Zustand |
| Rarely-changing injected values (theme, session, locale) | Context |

Do not mirror server data into Zustand/Context "so it's global" - that creates a second source of truth that goes stale. Server data lives in RSC props or the Query cache.

## TanStack Query v5 - current API

v5 has **one signature** (single options object) and renamed the v4 names that dominate training data:

| v4 (wrong now) | v5 |
|---|---|
| `useQuery(key, fn, opts)` | `useQuery({ queryKey, queryFn, ...opts })` |
| `isLoading` (initial load) | `isPending` (`isLoading` = `isPending && isFetching`) |
| `cacheTime` | `gcTime` |
| `onSuccess`/`onError` on `useQuery` | **removed** - effects on data, or global `QueryCache` callbacks |
| `keepPreviousData: true` | `placeholderData: keepPreviousData` (import the helper) |
| `useQuery(...).remove()` | `queryClient.removeQueries()` |

```tsx
"use client";
import { useQuery, keepPreviousData } from "@tanstack/react-query";

function Products({ page }: { page: number }) {
  const { data, isPending, isError, error, isPlaceholderData } = useQuery({
    queryKey: ["products", { page }],   // include ALL inputs in the key
    queryFn: ({ signal }) => fetchProducts(page, signal), // forward AbortSignal
    staleTime: 60_000,
    placeholderData: keepPreviousData,  // keep old page while next loads
  });
  if (isPending) return <Skeleton />;
  if (isError) return <ErrorState error={error} />;
  return <List items={data.items} dimmed={isPlaceholderData} />;
}
```

Mutations still have callbacks; invalidate after success:

```tsx
const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: updateProduct,
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["products"] }),
});
```

`useSuspenseQuery` guarantees defined `data` and suspends to the nearest `<Suspense>` boundary - pairs well with RSC streaming shells:

```tsx
const { data } = useSuspenseQuery({ queryKey: ["cart"], queryFn: fetchCart });
// no isPending branch needed; wrap the component in <Suspense> + error boundary
```

## Query + App Router setup (SSR-safe)

The QueryClient must be created per-request on the server (never module-level - that leaks data between users):

```tsx
// app/providers.tsx
"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } }),
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```

Prefetch on the server and hydrate, so the client starts warm with no loading flash:

```tsx
// page.tsx (server)
import { QueryClient, dehydrate, HydrationBoundary } from "@tanstack/react-query";

export default async function Page() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({ queryKey: ["products", { page: 1 }], queryFn: () => fetchProducts(1) });
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <Products page={1} />
    </HydrationBoundary>
  );
}
```

## Zustand 5

```tsx
// stores/cart.ts - plain module, no Provider needed for client-only state
import { create } from "zustand";

type CartState = {
  items: CartItem[];
  add: (item: CartItem) => void;
  clear: () => void;
};

export const useCartStore = create<CartState>()((set) => ({
  items: [],
  add: (item) => set((s) => ({ items: [...s.items, item] })),
  clear: () => set({ items: [] }),
}));

// Component: subscribe with SELECTORS - only re-renders when the slice changes
const count = useCartStore((s) => s.items.length);
const add = useCartStore((s) => s.add);
```

Rules:

- **Always select a slice.** `const store = useCartStore()` subscribes to everything and re-renders on every change.
- A selector must return a **stable** value. Returning a fresh object/array each call (`(s) => ({ a: s.a, b: s.b })`) causes infinite re-renders in v5 - select twice, or use `useShallow`:

```tsx
import { useShallow } from "zustand/react/shallow";
const { a, b } = useStore(useShallow((s) => ({ a: s.a, b: s.b })));
```

- Stores are client-only. Never read a Zustand store in a Server Component. If a store needs **server-provided initial state**, module-level `create` leaks between SSR requests - use the vanilla-store + Context pattern: `createStore` in a factory, instantiate in a client provider (`useRef(createCartStore(initial))`), consume via `useStore(ctx, selector)`.
- Persistence: `persist` middleware with `createJSONStorage(() => localStorage)`; gate first render on `useMounted()` (hydration mismatch otherwise, see `server-components.md`).

## Context in React 19

Context is for values that change rarely. Every consumer re-renders when the value changes, and React Compiler cannot optimize past a changed context value.

React 19 changes:

```tsx
const ThemeContext = createContext<Theme>("light");

// Provider: render the context itself - <ThemeContext.Provider> is deprecated
<ThemeContext value={theme}>{children}</ThemeContext>

// Consumer: use() replaces useContext, and can be called conditionally
import { use } from "react";
function Button({ styled }: { styled: boolean }) {
  const theme = styled ? use(ThemeContext) : null; // legal: use() may sit in branches
  ...
}
```

If you keep Context, memoize the value object (`useState`/`useReducer` output is already stable) so consumers don't re-render on every parent render.

## The `use()` hook

`use(promise)` suspends the component; `use(Context)` reads context. Unlike hooks, `use` may be called in conditionals and loops.

Critical rule for promises: **do not create the promise during a client render** - every render would make a new promise and loop forever. The promise must come from a Server Component prop, a Query/cache layer, or memoized state:

```tsx
// WRONG (client): use(fetchThing()) - new promise per render
// RIGHT: server starts it, client unwraps it
// page.tsx (server)
const thingPromise = fetchThing();          // not awaited - no server blocking
return <Suspense fallback={<Sk />}><Thing thingPromise={thingPromise} /></Suspense>;

// thing.tsx
"use client";
function Thing({ thingPromise }: { thingPromise: Promise<Thing> }) {
  const thing = use(thingPromise);
  ...
}
```

Rejected promises propagate to the nearest error boundary; pending state shows the nearest `<Suspense>` fallback.
