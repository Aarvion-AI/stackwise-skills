# Performance: React Compiler, Suspense/Streaming, Bundles

## React Compiler - what changes about memoization

The React Compiler (stable since 2025) auto-memoizes components and hooks at build time. Check whether it's on: `babel-plugin-react-compiler` in `package.json` and in Next config:

```ts
// next.config.ts
const nextConfig = { reactCompiler: true } satisfies NextConfig;
```

When the compiler is enabled:

- **Do not write new `useMemo` / `useCallback` / `React.memo`.** The compiler produces equivalent or better memoization and handles dependency tracking exactly.
- **Do not bulk-delete existing ones** in a migration commit - remove them opportunistically when touching a file, and confirm behavior is unchanged. Some existing code accidentally depends on memoization for correctness (effect dep arrays firing); the compiler preserves semantics, hand-deletion may not.
- Verify a component is compiled: React DevTools shows a "Memo ✨" badge; the `eslint-plugin-react-hooks` `react-compiler` rules report code the compiler had to skip.
- The compiler only optimizes code that follows the Rules of React (pure render, no mutation of props/state, hooks at top level unless `use()`). Rule-breaking components are **skipped silently**, not broken - fix the lint errors so they get optimized.
- Still legitimate manual work: genuinely expensive **computations** (`useMemo` around an O(n²) transform is fine), stable refs for third-party non-React libs, and `key`-based state resets.

What the compiler does NOT fix:

- Context: a changed context value re-renders all consumers regardless. Split contexts or move to Zustand selectors (see `state-and-data-fetching.md`).
- Server work: RSC render time, data waterfalls, and payload size are unaffected - that's the rest of this file.

## Eliminating server waterfalls

Sequential awaits are the top RSC perf bug:

```tsx
// WATERFALL - each await blocks the next
const user = await getUser(id);
const posts = await getPosts(id);
const badges = await getBadges(id);

// PARALLEL
const [user, posts, badges] = await Promise.all([getUser(id), getPosts(id), getBadges(id)]);
```

Better still, don't block the page on slow data at all - stream it (next section). Component-level fetching with `cache()`-deduplicated functions (see `server-components.md`) avoids prop-drilling without duplicate queries.

## Suspense and streaming

`loading.tsx` wraps the whole route segment in a Suspense boundary - the shell (layout) flushes immediately, the page streams in:

```
app/dashboard/
  layout.tsx    // sent immediately
  loading.tsx   // instant fallback for page.tsx
  page.tsx      // streams when its awaits resolve
```

For finer control, keep the page fast and isolate each slow region in its own boundary:

```tsx
export default function Dashboard() {
  return (
    <>
      <Header />                             {/* fast, renders immediately */}
      <div className="grid">
        <Suspense fallback={<RevenueSkeleton />}>
          <Revenue />                        {/* async server component */}
        </Suspense>
        <Suspense fallback={<OrdersSkeleton />}>
          <RecentOrders />                   {/* streams independently */}
        </Suspense>
      </div>
    </>
  );
}

async function Revenue() {
  const data = await getRevenue();           // slow - only blocks THIS boundary
  return <RevenueChart data={data} />;
}
```

Rules of thumb:

- A Suspense boundary must wrap the **async component from outside**; an `await` above the boundary still blocks everything below it.
- Pass un-awaited promises to client components and `use()` them when the interactive leaf needs the data (pattern in `state-and-data-fetching.md`).
- Every `useSearchParams()` in a client component must sit under a Suspense boundary or `next build` fails the static render with a bailout error.
- Give fallbacks real dimensions (skeletons, not spinners) to avoid layout shift.
- Errors inside a boundary surface to the nearest `error.tsx` / error boundary, not the whole page.

## Transitions for responsive interactions

Keep urgent updates (typing) fast by marking expensive re-renders as non-urgent:

```tsx
const [isPending, startTransition] = useTransition();
function onChange(e: React.ChangeEvent<HTMLInputElement>) {
  setQuery(e.target.value);                       // urgent: input echoes now
  startTransition(() => setFilter(e.target.value)); // deferred: big list re-render
}
```

`useDeferredValue(value)` is the pull-based equivalent when you don't own the setter. Navigation (`router.push`) is already a transition in App Router.

## Bundle size

- Every `"use client"` boundary's import graph ships to the browser. Audit with `ANALYZE=true` + `@next/bundle-analyzer`.
- Move heavy render-only libraries (markdown, syntax highlighting, charts data-prep) into Server Components - they cost zero client JS there.
- Lazy-load below-the-fold or on-interaction client components:

```tsx
import dynamic from "next/dynamic";
const HeavyChart = dynamic(() => import("./heavy-chart"), {
  loading: () => <ChartSkeleton />,
  ssr: false, // only when the lib touches window at import time
});
```

- Import narrowly (`import { debounce } from "lodash-es"`, icon-per-file imports); Next's `optimizePackageImports` covers common libraries automatically.
- `next/image` for images (auto sizing/format/lazy), `next/font` for fonts (self-hosted, zero layout shift). Add `priority` to the LCP image only.

## Fixing re-render hotspots (when a profile shows one)

Order of operations:

1. Profile first - React DevTools Profiler or React Scan. Do not optimize blind.
2. Check the component compiles (Memo badge). If skipped, fix the Rules-of-React violation the linter reports.
3. Push state down: a `useState` high in the tree re-renders everything below; move it into the leaf that uses it.
4. Lift content out: pass expensive subtrees as `children` to the stateful wrapper - children props don't re-render when the wrapper's state changes.
5. For list-heavy pages, virtualize (`@tanstack/react-virtual`) past ~200 rows.
6. Only after 1-5: hand-memoization, and only where the compiler is provably skipping.

## Measuring

- `npx next build` output: route table shows Static/Dynamic and first-load JS per route; treat >150 kB first-load as a smell.
- Lighthouse / `npx unlighthouse` for LCP/INP/CLS on real routes.
- Server timing: wrap slow data functions with `console.time` in dev, or enable `experimental.serverComponentsHmrCache` logging; production tracing via `instrumentation.ts` + OpenTelemetry.
- After any perf change, re-run the same measurement; keep iterating until the metric actually moves - before/after numbers or it didn't happen.
