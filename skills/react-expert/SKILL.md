---
name: react-expert
description: Use when working in a React 19 / Next.js 15 codebase - .tsx/.jsx files, next.config.ts, app/ router directories, "use client"/"use server" directives, package.json with react or next dependencies. Builds and refactors Server/Client Components, server actions and forms, Suspense/streaming UIs, and TanStack Query or Zustand data layers; debugs hydration and boundary errors. Invoke for adding routes or components, wiring mutations with useActionState, choosing state management, fixing "Cannot use hooks in Server Component" class errors, memoization cleanup under React Compiler, and testing RSC apps.
license: MIT
metadata:
  version: "0.1.0"
  category: frontend
  frameworks: "React 19, Next.js 15 (App Router), TanStack Query v5, Zustand 5, Testing Library 16"
  triggers: react, nextjs, next.js, app router, server components, rsc, use client, use server, server actions, useActionState, suspense, streaming, hydration, tanstack query, react query, zustand, tsx, react compiler
  related: playwright-expert, nestjs-expert, fastapi-expert
---

# React Expert

Turns Claude into a senior React 19 + Next.js 15 App Router engineer who defaults to Server Components, keeps client boundaries minimal, and never ships legacy patterns.

## When to Use This Skill

- Add or modify routes, layouts, and components in a Next.js 15 App Router project
- Implement mutations with server actions, `useActionState`, and progressive-enhancement forms
- Decide where the Server/Client Component boundary goes and fix boundary/hydration errors
- Wire client-side data fetching with TanStack Query v5 (including SSR hydration)
- Choose and implement state management (server state vs Zustand vs Context vs URL state)
- Add Suspense boundaries and streaming to slow pages; fix waterfalls
- Write or fix tests for components, hooks, and server actions in an RSC codebase

## Core Workflow

1. **Analyze** - Read `package.json` (confirm React 19 / Next 15, check for `babel-plugin-react-compiler`, `@tanstack/react-query`, `zustand`), `next.config.ts`, and the nearest `layout.tsx`/existing components to learn conventions. Identify whether the code you will touch runs on the server, the client, or both - this decides every pattern below.
2. **Design the boundary** - Default to Server Components. Push `"use client"` to the smallest leaf that needs interactivity; pass Server Component output through as `children`/props rather than importing server code into client files. Fetch data on the server where possible; mutations go through server actions.
3. **Implement** - TypeScript only, function components only, current APIs only: `use()` for promises/context in render, `useActionState` for action state, ref as a normal prop (no `forwardRef`), no manual `useMemo`/`useCallback`/`memo` when React Compiler is enabled. Load the matching reference file (table below) before writing unfamiliar patterns.
4. **Verify types/lint** - run `npx tsc --noEmit` and `npx next lint` (or `npx eslint .` if the project migrated to the ESLint CLI); fix all reported issues and re-run until clean before proceeding.
5. **Test** - run the project's test command (`npx vitest run` or `npx jest`); write or update tests for the change following `references/testing.md`; fix all failures and re-run until clean.
6. **Prove it works** - run `npx next build` (catches server/client boundary violations, missing Suspense around `useSearchParams`, and dynamic API misuse that dev mode tolerates); fix all reported issues and re-run until clean. For behavior changes, start `npx next dev` and exercise the route.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Server vs Client Components, composition, async APIs, caching | `references/server-components.md` | Creating/moving components, `"use client"` decisions, boundary or hydration errors, `params`/`cookies` usage |
| TanStack Query v5, Zustand vs Context, `use()` hook | `references/state-and-data-fetching.md` | Client-side fetching, choosing state management, migrating Query v4→v5, sharing state across components |
| Server actions, `useActionState`, `useOptimistic`, validation | `references/forms-and-actions.md` | Building forms, mutations, `"use server"` files, optimistic UI, revalidation after writes |
| React Compiler, memoization, Suspense/streaming, bundle size | `references/performance.md` | Perf work, deciding whether to memoize, adding `loading.tsx`/Suspense, fixing waterfalls or large bundles |
| Testing Library 16 with RSC, async components, action testing | `references/testing.md` | Writing/fixing tests, testing async Server Components, mocking server actions or `next/navigation` |

## Key Patterns

**Server Component page fetching data, client leaf for interactivity:**

```tsx
// app/products/[id]/page.tsx - Server Component (no directive)
import { AddToCart } from "./add-to-cart";

export default async function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>; // params is a Promise in Next 15
}) {
  const { id } = await params;
  const product = await getProduct(id); // direct server fetch, no API route
  return (
    <article>
      <h1>{product.name}</h1>
      <AddToCart productId={product.id} /> {/* only this ships JS */}
    </article>
  );
}
```

**Server action + `useActionState` (React 19 form pattern):**

```tsx
// app/products/actions.ts
"use server";
import { revalidatePath } from "next/cache";

export async function addToCart(prev: { error?: string }, formData: FormData) {
  const parsed = cartSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { error: "Invalid quantity" };
  await db.cart.add(parsed.data); // re-check auth here: actions are public endpoints
  revalidatePath("/cart");
  return {};
}

// add-to-cart.tsx
"use client";
import { useActionState } from "react"; // from react, NOT react-dom
import { addToCart } from "./actions";

export function AddToCart({ productId }: { productId: string }) {
  const [state, formAction, isPending] = useActionState(addToCart, {});
  return (
    <form action={formAction}>
      <input type="hidden" name="productId" value={productId} />
      <input name="quantity" type="number" defaultValue={1} />
      <button disabled={isPending}>{isPending ? "Adding…" : "Add to cart"}</button>
      {state.error && <p role="alert">{state.error}</p>}
    </form>
  );
}
```

**`use()` to unwrap a server-started promise in a client component (no awaited waterfall):**

```tsx
// page.tsx (server): start the fetch, don't await it
export default function Page() {
  const reviewsPromise = getReviews(); // NOT awaited
  return (
    <Suspense fallback={<ReviewsSkeleton />}>
      <Reviews reviewsPromise={reviewsPromise} />
    </Suspense>
  );
}

// reviews.tsx
"use client";
import { use } from "react";

export function Reviews({ reviewsPromise }: { reviewsPromise: Promise<Review[]> }) {
  const reviews = use(reviewsPromise); // suspends until resolved
  return <ul>{reviews.map((r) => <li key={r.id}>{r.body}</li>)}</ul>;
}
```

**Ref as a prop - `forwardRef` is legacy in React 19:**

```tsx
function TextInput({ ref, ...props }: React.ComponentProps<"input">) {
  return <input ref={ref} {...props} />;
}
```

## Common Mistakes

- **Marking whole pages `"use client"` to use one hook.** The directive marks a boundary, not a single file's needs - everything it imports becomes client code. Extract the interactive part into a leaf component instead, and pass server-rendered content through `children`.
- **Awaiting `params`/`searchParams`/`cookies()`/`headers()` incorrectly in Next 15.** These are now async (`params: Promise<...>`). Synchronous access is a deprecation error; type them as promises and `await` them (or `use()` them in client components).
- **Assuming `fetch` is cached by default.** Next 15 reversed this: `fetch` is uncached and route handlers/client navigations are dynamic unless you opt in with `cache: "force-cache"`, `revalidate`, or `"use cache"`. Don't add cache-busting hacks; add explicit caching.
- **Sprinkling `useMemo`/`useCallback`/`memo` when React Compiler is enabled.** The compiler memoizes automatically; manual wrappers are dead weight and can defeat compiler analysis. Only keep them for genuinely expensive computations the compiler cannot prove, and verify with the React DevTools "Memo ✨" badge.
- **Using TanStack Query v4 idioms in v5.** `isLoading` (initial) is now `isPending`; callbacks (`onSuccess`/`onError`) were removed from `useQuery`; only the object signature `useQuery({ queryKey, queryFn })` exists; `cacheTime` is `gcTime`. Handle side effects in `useEffect` on the returned data or in mutation callbacks.
- **Treating server actions as private functions.** Every exported `"use server"` function is a public POST endpoint. Validate input with a schema and re-check authentication/authorization inside the action, even if the UI already gated it.
- **Testing async Server Components with plain `render()`.** `render(<AsyncComp />)` throws on a promise-returning component. Await the component first: `render(await AsyncComp({ params }))`, or cover it with Playwright; unit-test the data functions separately.
- **Reaching for Context to share client state.** Context re-renders every consumer on any change (React Compiler does not fix this - it cannot memoize past a changed context value). Use Zustand with selectors for shared mutable state; keep Context for dependency-injection-style rarely-changing values (theme, session).
