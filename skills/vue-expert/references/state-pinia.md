# Pinia (v3) - Setup Stores

Pinia 3 is the only supported Vue store. Write **setup stores** (function syntax), not options stores - they compose with other composables, type better, and match `<script setup>` idioms. Vuex is legacy; migrate, never extend.

## Setup store anatomy

```ts
// stores/cart.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useCartStore = defineStore('cart', () => {
  // state = refs
  const items = ref<CartItem[]>([])
  const couponCode = ref<string | null>(null)

  // getters = computed
  const count = computed(() => items.value.length)
  const total = computed(() =>
    items.value.reduce((sum, i) => sum + i.price * i.qty, 0),
  )

  // actions = functions (sync or async, no mutations concept)
  async function add(productId: string, qty = 1) {
    const item = await $fetch<CartItem>('/api/cart', {
      method: 'POST',
      body: { productId, qty },
    })
    items.value.push(item)
  }

  function clear() {
    items.value = []
    couponCode.value = null
  }

  // EVERYTHING used outside must be returned
  return { items, couponCode, count, total, add, clear }
})
```

Rules:
- Store id (`'cart'`) must be unique app-wide; convention `use<Name>Store`.
- Every ref/computed/function referenced by components must be in the return object. Unreturned refs are private but break devtools/SSR serialization if they hold state you need hydrated - keep truly private state in module scope only if it is not per-request (SSR shares module scope across requests).
- No `this`. No mutations. Actions mutate refs directly.

## Consuming a store - the destructuring trap

```vue
<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useCartStore } from '@/stores/cart'

const cart = useCartStore()

// WRONG: state/getters destructured directly are dead snapshots
// const { items, total } = cart

// RIGHT: storeToRefs for state + getters, direct destructure for actions
const { items, total } = storeToRefs(cart)
const { add, clear } = cart
</script>

<template>
  <span>{{ total }} ({{ items.length }})</span>
  <button @click="add('sku-1')">Add</button>
</template>
```

- `storeToRefs` skips functions; destructuring actions from the store directly is fine (they are bound).
- Using `cart.total` without destructuring is always safe too.

## Calling a store from the right place

`useCartStore()` must run where an active Pinia exists:
- Component `<script setup>`: always fine.
- Other stores/composables: fine when called during their setup.
- **Module top level, router guards defined at import time, or utility files: NOT fine** - the store is called before `app.use(pinia)`. Call the store *inside* the guard/handler body:

```ts
router.beforeEach((to) => {
  const auth = useAuthStore()          // inside the callback, not above it
  if (to.meta.requiresAuth && !auth.isLoggedIn) return '/login'
})
```

In Nuxt, calling stores inside Nitro server routes is invalid - stores are app-side; server routes use their own logic/db.

## Stores composing stores

```ts
export const useCheckoutStore = defineStore('checkout', () => {
  const cart = useCartStore()          // call at setup top level - fine
  const auth = useAuthStore()

  const canCheckout = computed(() => auth.isLoggedIn && cart.count > 0)

  async function submit() {
    await $fetch('/api/orders', { method: 'POST', body: { items: cart.items } })
    cart.clear()
  }

  return { canCheckout, submit }
})
```

Avoid circular getter dependencies between stores (A's getter reads B's getter which reads A). Break cycles by moving the shared derivation into one store.

## Resetting and patching

- Options stores get `$reset()` for free; **setup stores do not** - write an explicit `reset()`/`clear()` action (as above) or Pinia throws.
- `store.$patch({ couponCode: 'X' })` batches multiple changes into one devtools entry; the function form `store.$patch((s) => { s.items.push(x) })` handles array mutations.
- `store.$subscribe((mutation, state) => ...)` for persistence; `{ detached: true }` keeps it alive past the component.

## SSR / Nuxt

With `@pinia/nuxt`, state populated during SSR is serialized into the payload and hydrated on the client automatically. Requirements:

- State must be POJO-serializable (no class instances, Maps, functions in state - or provide payload plugins).
- Never keep per-request state in module scope; a fresh Pinia is created per request, module scope is not.
- Populate state via `useAsyncData` + an action, so the fetch itself is deduped:

```vue
<script setup lang="ts">
const products = useProductsStore()
await useAsyncData('products', async () => {
  await products.fetchAll()
  return true                          // useAsyncData must return a value
})
</script>
```

- Outside components (Nuxt plugins/middleware) pass the pinia instance if needed: `useCartStore(nuxtApp.$pinia)`.

## Persistence (client-side)

Use `pinia-plugin-persistedstate`; gate to client in SSR apps. Persist only what you must (auth token, UI prefs), never server-derived caches:

```ts
export const usePrefsStore = defineStore(
  'prefs',
  () => {
    const theme = ref<'light' | 'dark'>('light')
    return { theme }
  },
  { persist: { pick: ['theme'] } },
)
```

## Testing stores

```ts
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useCartStore } from '@/stores/cart'

beforeEach(() => setActivePinia(createPinia()))

it('computes total', () => {
  const cart = useCartStore()
  cart.items = [{ id: '1', price: 10, qty: 2 } as CartItem]
  expect(cart.total).toBe(20)
})
```

For component tests, `createTestingPinia({ stubActions: true, initialState: { cart: { items: [...] } } })` from `@pinia/testing` - actions become spies; assert `expect(cart.add).toHaveBeenCalledWith('sku-1')`. Note `initialState` only overrides **options-store style state**; for setup stores set state after creation or pass `stubActions: false` and mock the network instead.

## When NOT to use Pinia

- Subtree-scoped context (form wizard, design-system config): `provide`/`inject`.
- Two components sharing one value: lift a ref to a shared composable with module-level state **only in SPA code** (module state leaks across SSR requests - in Nuxt use `useState('key', () => init)` instead).
- Server cache of fetched data in Nuxt: `useFetch`/`useAsyncData` keyed caches already handle it; do not mirror every API response into a store.
