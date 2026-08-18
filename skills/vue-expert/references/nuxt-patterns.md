# Nuxt 4 Patterns

Nuxt 4 app code lives under **`app/`** (new default srcDir), server code under **`server/`**, shared isomorphic code under **`shared/`**. Do not generate the Nuxt 3 flat layout for new Nuxt 4 projects.

```
app/
  app.vue            # root; must contain <NuxtLayout><NuxtPage/></NuxtLayout> for pages to render
  pages/             # file-based routes: pages/products/[id].vue -> /products/:id
  layouts/default.vue
  components/        # auto-imported by name (nested dirs prefix the name)
  composables/       # auto-imported (top-level files only by default)
  middleware/        # route middleware: auth.ts -> definePageMeta({ middleware: 'auth' })
  plugins/
server/
  api/               # /api/* Nitro routes
  routes/            # non-/api server routes
  middleware/        # server middleware (runs on every request)
  utils/             # auto-imported into server code only
shared/
  utils/  types/     # auto-imported on BOTH app and server sides
nuxt.config.ts
```

Auto-imports cover Vue APIs (`ref`, `computed`...), Nuxt composables (`useFetch`, `useRoute`...), and your `composables/`/`utils/`. Do not add manual imports for these; DO import explicitly from other layers' aliases (`#imports` only in rare programmatic cases).

## Data fetching - the decision that matters

| Need | Use |
|------|-----|
| Fetch in a component/page during setup | `useFetch(url, opts)` |
| Custom async logic (multiple calls, SDK) in setup | `useAsyncData(key, fn)` |
| Fetch inside an event handler / action / server code | `$fetch` |
| Never `$fetch` bare in setup | it double-fetches (server + client, no payload transfer) |

```vue
<script setup lang="ts">
const route = useRoute()

// Reactive URL: pass a function/computed so it refetches when params change
const { data: product, status, error, refresh } = await useFetch(
  () => `/api/products/${route.params.id}`,
)

if (error.value) {
  throw createError({ statusCode: 404, statusMessage: 'Product not found', fatal: true })
}
</script>
```

Key `useFetch`/`useAsyncData` facts LLMs get wrong:
- Return `data` is a ref, possibly `null` - guard templates (`v-if="product"`); type is inferred from the server route return type.
- `status` is `'idle' | 'pending' | 'success' | 'error'`; **there is no `pending` boolean in Nuxt 4** (removed) - use `status === 'pending'`.
- Non-awaited `useFetch` (no top-level `await`) still SSRs by default; `await` controls whether setup blocks, not whether it runs on server.
- `lazy: true` → do not block navigation; `server: false` → client-only fetch (auth-dependent data); both mean data is initially null on client.
- Options: `pick: ['id','title']` trims payload; `transform` reshapes; `watch: [ref]` refetches; `immediate: false` + `execute()` for manual start; `dedupe: 'defer'` by default.
- `key` for `useAsyncData` must be unique app-wide; same key shares cached data - `useNuxtData(key)` reads that cache elsewhere.
- Refresh after a mutation: `await refresh()` or `refreshNuxtData('key')`.

## Nitro server routes

File name encodes method: `server/api/products/[id].get.ts`, `.post.ts`, `index.get.ts`; `[...slug].ts` catches all.

```ts
// server/api/products/index.post.ts
import { z } from 'zod'

const Body = z.object({ name: z.string().min(1), price: z.number().positive() })

export default defineEventHandler(async (event) => {
  const body = await readValidatedBody(event, Body.parse)   // 400s on invalid
  const user = await requireUserSession(event)              // your auth util
  return await db.product.create({ data: { ...body, ownerId: user.id } })
})
```

Handler toolbox (all auto-imported, from h3): `getRouterParam(event, 'id')`, `getQuery(event)`, `getValidatedQuery(event, schema.parse)`, `readBody`/`readValidatedBody`, `getHeader`, `setResponseStatus(event, 201)`, `getCookie`/`setCookie`, `sendRedirect`. Errors: `throw createError({ statusCode: 403, statusMessage: 'Forbidden' })` - never return an error-shaped object with a 200.

- Return value is JSON-serialized; returned types flow into `useFetch` inference automatically.
- Cache expensive handlers: `defineCachedEventHandler(handler, { maxAge: 60 })`; cache functions with `defineCachedFunction`.
- `server/middleware/*.ts` runs on every request - attach context (`event.context.user = ...`), never respond from it.

## Runtime config and env

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  runtimeConfig: {
    apiSecret: '',                       // server-only; overridden by NUXT_API_SECRET
    public: { apiBase: '/api' },         // exposed to client; NUXT_PUBLIC_API_BASE
  },
})
```

- `const config = useRuntimeConfig()` in app code (only `config.public.*` exists on client); `useRuntimeConfig(event)` in server routes.
- Env override naming is mechanical: `NUXT_` + SCREAMING_SNAKE path. Do not read `process.env` in app code.

## SSR-safe component code

- `window`/`document`/`localStorage` only in `onMounted`, client plugins (`.client.ts`), or `if (import.meta.client)` guards. `import.meta.server` for the inverse.
- `<ClientOnly fallback-tag="div">` wraps browser-only components (charts, maps); heavy ones also `.client.vue` suffix.
- Per-request shared state: `useState<T>('key', () => init)` - SSR-serialized, hydrated, shared across components. Module-level `const state = ref()` in a composable file leaks across users on the server; never do it in Nuxt.
- Cookies isomorphically: `const token = useCookie<string | null>('token', { sameSite: 'lax' })` - readable/writable on both sides.
- `useRequestHeaders(['cookie'])` to forward auth when `$fetch`-ing internal APIs during SSR from utility code (`useFetch` forwards automatically).

## Routing, middleware, meta

```vue
<script setup lang="ts">
definePageMeta({ layout: 'admin', middleware: 'auth' })   // compile-time macro: literals only
useSeoMeta({ title: () => product.value?.name ?? 'Store' })
</script>
```

```ts
// app/middleware/auth.ts
export default defineNuxtRouteMiddleware((to) => {
  const { loggedIn } = useUserSession()
  if (!loggedIn.value) return navigateTo(`/login?next=${to.fullPath}`, { redirectCode: 302 })
})
```

- Navigate with `navigateTo('/x')` (return it from middleware), never `router.push` in middleware; `<NuxtLink>` not `<a>` for internal links.
- Global middleware: `auth.global.ts`. Server-aware redirects work because middleware runs during SSR too - do not gate on `import.meta.client` unless intentional.
- Route params via `useRoute().params`; validate with `definePageMeta({ validate: (route) => /^\d+$/.test(route.params.id as string) })`.

## Error handling

- `app/error.vue` at srcDir root renders fatal errors (receives `error` prop; `clearError({ redirect: '/' })` to recover).
- `<NuxtErrorBoundary>` for component-subtree errors; `showError()` to escalate.
- In setup, throwing `createError({ ..., fatal: true })` during SSR yields a proper status code; non-fatal errors from `useFetch` land in `error.value`.

## Common Nuxt mistakes

- Calling Nuxt composables (`useRoute`, `useRuntimeConfig`, `useFetch`) after `await` in a non-setup context or inside callbacks → "nuxt instance unavailable". Call them at setup top level, store the result.
- Putting pages in `pages/` at repo root instead of `app/pages/` in Nuxt 4 - routes silently missing.
- Registering `app.vue` without `<NuxtPage />` - every route renders the same content.
- Using `process.server`/`process.client` (deprecated) instead of `import.meta.server`/`import.meta.client`.
- Fetching in `onMounted` for SSR pages - data misses server render and SEO; only correct for client-only data.
