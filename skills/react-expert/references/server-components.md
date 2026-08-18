# Server vs Client Components (React 19 / Next.js 15)

## The mental model

- **Server Components (default).** Every component in `app/` is a Server Component unless a `"use client"` file boundary makes it client. They run only on the server, can be `async`, can touch the DB/filesystem/secrets, and ship **zero JS** to the browser.
- **Client Components.** Marked by `"use client"` at the top of a file. They render on the server too (SSR produces HTML) and then hydrate - "client" means "also runs in the browser", not "skips the server".
- The directive marks a **module-graph boundary**: everything a `"use client"` file imports becomes client code. You never need the directive on children of client components.

Decide per component:

| Needs | Kind |
|---|---|
| Data fetching, DB/ORM access, secrets, heavy deps (markdown, syntax highlight) | Server |
| `useState`/`useEffect`/`useReducer`, event handlers, browser APIs, refs to DOM | Client |
| Both | Split: server parent fetches, small client leaf interacts |

## Composition: server inside client via children

A client component cannot **import** a server component, but it can **receive** one:

```tsx
// sidebar-shell.tsx
"use client";
export function SidebarShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <aside data-open={open}>
      <button onClick={() => setOpen((o) => !o)}>toggle</button>
      {open && children} {/* server-rendered content passes through untouched */}
    </aside>
  );
}

// page.tsx (server)
export default function Page() {
  return (
    <SidebarShell>
      <ServerRenderedNav /> {/* stays a Server Component */}
    </SidebarShell>
  );
}
```

Wrong: `import { ServerRenderedNav } from "..."` inside `sidebar-shell.tsx` - that silently converts it to a client component (and errors if it's async or uses server-only APIs).

## Serialization rules at the boundary

Props from server → client must be serializable by React: plain objects, arrays, primitives, Date, Map/Set, FormData, **Promises** (for `use()`), and server-action references. Not allowed: functions (except `"use server"` actions), class instances (including ORM entities - spread to plain objects first), JSX component types.

```tsx
// WRONG: passing an event handler from a Server Component
<ClientButton onClick={() => save()} />        // build error: functions not serializable
// RIGHT: pass a server action
<ClientButton action={saveAction} />           // saveAction is a "use server" function
```

## Enforcing the boundary

```ts
import "server-only";   // top of a module: build error if it reaches the client bundle
import "client-only";   // inverse
```

Put `server-only` in every file that touches secrets or the DB (`lib/db.ts`, `lib/auth.ts`). This turns accidental client imports into build failures instead of leaked credentials.

## Async request APIs (breaking change in Next 15)

`params`, `searchParams`, `cookies()`, `headers()`, and `draftMode()` are **async**:

```tsx
// page / layout / route handler props
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { slug } = await params;
  const { q } = await searchParams;
  ...
}

import { cookies, headers } from "next/headers";
const cookieStore = await cookies();
const theme = cookieStore.get("theme")?.value;
```

In a client component, unwrap the promise with `use()`:

```tsx
"use client";
import { use } from "react";
export default function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
}
```

Old synchronous access (`params.slug` without await) logs a deprecation error and will break; `npx next build` and the `next-async-request-api` codemod catch it.

## Caching defaults (Next 15 reversed Next 14)

Uncached by default: `fetch()` requests, `GET` route handlers, and the client router cache (`staleTime: 0` for page segments). Opt in explicitly:

```tsx
await fetch(url, { cache: "force-cache" });                 // cache indefinitely
await fetch(url, { next: { revalidate: 3600, tags: ["products"] } }); // ISR + tag
// Route segment level:
export const revalidate = 3600;
export const dynamic = "force-static";
```

Invalidate after writes with `revalidatePath("/products")` or `revalidateTag("products")` inside a server action or route handler.

Direct DB calls are never cached by `fetch` semantics. Deduplicate per-request with `cache()`:

```tsx
import { cache } from "react";
export const getUser = cache(async (id: string) => db.user.findUnique({ where: { id } }));
```

Any call to `await cookies()`, `await headers()`, or reading `searchParams` makes the route dynamic (rendered per request). Check the `npx next build` output table (Static / Dynamic markers) to confirm what you expect.

## Hydration errors: causes and fixes

"Hydration failed because the server rendered HTML didn't match the client" - React 19 prints a diff. Usual causes:

1. **Non-deterministic render**: `Date.now()`, `Math.random()`, locale-dependent formatting. Fix: compute on the server and pass as a prop, or render after mount.
2. **Browser-only values in render**: `window.innerWidth`, `localStorage`. Fix: gate behind mounted state:

```tsx
"use client";
function useMounted() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
// render a stable placeholder until mounted, then the client-only value
```

3. **Invalid HTML nesting** (`<p><div>`, `<a>` inside `<a>`) - React 19 hydration is stricter about this; fix the markup.
4. **Browser extensions mutating HTML** - verify in an incognito window before chasing ghosts.

Escape hatch for a single deliberately different attribute (e.g. timestamps): `suppressHydrationWarning` on that element only. Never wrap whole trees with it.

## Where fetching belongs

- Page-level data: fetch in the Server Component (`await` in the page/layout), pass down. Parallelize independent fetches with `Promise.all`, or start promises un-awaited and stream (see `performance.md`).
- Mutations: server actions (see `forms-and-actions.md`), not hand-rolled API routes.
- Client-side live/interactive data (polling, infinite scroll, focus refetch): TanStack Query (see `state-and-data-fetching.md`).
- API route handlers (`app/api/*/route.ts`) are for external consumers (webhooks, mobile apps), not for your own components to fetch from - that is a self-inflicted network hop.
