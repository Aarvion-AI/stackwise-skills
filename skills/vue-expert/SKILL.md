---
name: vue-expert
description: Use when working with .vue single-file components, nuxt.config.ts, vite.config.ts with @vitejs/plugin-vue, Pinia stores, or tasks mentioning Vue, Vue 3, Nuxt, Composition API, script setup, ref/reactive, composables, useFetch, or SSR hydration. Builds Vue 3.5+/Nuxt 4 features, designs composables and Pinia setup stores, debugs reactivity and hydration bugs, and writes Vitest + Vue Testing Library tests. Invoke for component implementation, state management, Nuxt server routes, reactivity debugging, SSR fixes, and component testing.
license: MIT
metadata:
  version: "0.1.0"
  category: frontend
  frameworks: Vue 3.5+, Nuxt 4, Pinia 3, Vitest 3, @testing-library/vue 8
  triggers: vue, nuxt, composition api, script setup, ref, reactive, defineModel, composable, pinia, useFetch, nitro, server route, hydration, watch, watchEffect, vitest, vue testing library
  related: playwright-expert, nestjs-expert, fastapi-expert
---

# Vue Expert

Turns Claude into a senior Vue 3.5+/Nuxt 4 engineer who writes idiomatic `<script setup lang="ts">` code, designs reactive state that survives SSR, and never ships Options API or Vue 2 idioms.

## When to Use This Skill

- Build or modify Vue single-file components (`.vue`) with Composition API and TypeScript
- Design composables (`useX`) with correct reactivity, cleanup, and SSR safety
- Create or refactor Pinia stores (setup-store style) and wire them into components
- Add Nuxt 4 pages, layouts, middleware, or Nitro server routes (`server/api/`)
- Debug reactivity bugs: lost reactivity from destructuring, stale watchers, `shallowRef` misuse
- Fix SSR/hydration mismatches and data-fetching duplication in Nuxt
- Write component and composable tests with Vitest + Vue Testing Library

## Core Workflow

1. **Analyze** - Inspect the project before writing anything: check `package.json` for Vue/Nuxt/Pinia versions, whether it is a Nuxt app (`nuxt.config.ts`) or plain Vite SPA, auto-import config, existing composable/store conventions, and the test runner setup (`vitest.config.ts`, existing `*.spec.ts`). Match existing directory conventions (`app/` vs `src/` in Nuxt 4).
2. **Implement** - Write `<script setup lang="ts">` only. Use `defineProps`/`defineEmits` with type-only declarations, `defineModel()` for two-way binding, `ref`/`computed` for state, composables for shared logic, Pinia setup stores for app state. In Nuxt, fetch data with `useFetch`/`useAsyncData` (never bare `$fetch` in setup) and put API logic in Nitro routes under `server/`. Load the matching reference file from the Reference Guide before writing unfamiliar patterns.
3. **Verify types and lint** - Run `pnpm vue-tsc --noEmit` (or `pnpm nuxi typecheck` in Nuxt) and `pnpm eslint .`; fix all reported issues and re-run until clean before proceeding.
4. **Test** - Write or update Vitest + Vue Testing Library tests for the change (render, interact via `@testing-library/user-event`, assert on the DOM). Run `pnpm vitest run`; fix all failures and re-run until clean before proceeding.
5. **Prove it works** - Run the dev server (`pnpm dev`) and exercise the changed flow, or for Nuxt SSR changes run `pnpm build && node .output/server/index.mjs` and confirm no hydration warnings in the console. If anything fails, fix it and re-verify (steps 3-4) until clean.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Script setup, props/emits/defineModel, ref vs reactive vs shallowRef, composables design | `references/composition-api.md` | Writing or reviewing any `.vue` component or `useX` composable |
| Pinia setup stores, storeToRefs, SSR state, testing stores | `references/state-pinia.md` | Task touches app-level state, a `stores/` directory, or `defineStore` |
| Nuxt 4 structure, useFetch/useAsyncData, Nitro server routes, middleware, runtime config | `references/nuxt-patterns.md` | Project has `nuxt.config.ts` or task mentions Nuxt, server routes, or data fetching |
| Reactivity edge cases: destructuring, watch vs watchEffect, hydration mismatches | `references/reactivity-pitfalls.md` | Debugging "not updating"/"fires twice"/hydration warnings, or writing watchers |
| Vitest + Vue Testing Library setup, component/composable/Nuxt testing | `references/testing.md` | Writing or fixing any test for Vue/Nuxt code |

## Key Patterns

**Typed props with defaults and defineModel (Vue 3.5+)** - no `withDefaults` needed; props can be destructured reactively:

```vue
<script setup lang="ts">
const { label, size = 'md' } = defineProps<{ label: string; size?: 'sm' | 'md' | 'lg' }>()
const modelValue = defineModel<string>({ required: true })
const emit = defineEmits<{ submit: [value: string] }>()
</script>

<template>
  <input v-model="modelValue" :placeholder="label" @keyup.enter="emit('submit', modelValue)" />
</template>
```

**Composable returning refs, with cleanup** - return plain refs (not a `reactive` bag), accept `MaybeRefOrGetter`, clean up with `onScopeDispose`:

```ts
import { ref, toValue, watchEffect, onScopeDispose, type MaybeRefOrGetter } from 'vue'

export function useEventSource(url: MaybeRefOrGetter<string>) {
  const data = ref<string | null>(null)
  const status = ref<'connecting' | 'open' | 'closed'>('connecting')
  let es: EventSource | undefined

  watchEffect(() => {
    es?.close()
    es = new EventSource(toValue(url))
    es.onmessage = (e) => (data.value = e.data)
    es.onopen = () => (status.value = 'open')
  })
  onScopeDispose(() => es?.close())

  return { data, status }
}
```

**Pinia setup store** - `ref` = state, `computed` = getters, functions = actions; always return everything used outside:

```ts
export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>([])
  const total = computed(() => items.value.reduce((s, i) => s + i.price * i.qty, 0))
  async function add(productId: string) {
    const item = await $fetch<CartItem>(`/api/cart/${productId}`, { method: 'POST' })
    items.value.push(item)
  }
  return { items, total, add }
})
```

**Nuxt data fetching + typed server route** - types flow from the Nitro handler to the client automatically:

```ts
// server/api/products/[id].get.ts
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const product = await db.product.findUnique({ where: { id } })
  if (!product) throw createError({ statusCode: 404, statusMessage: 'Not found' })
  return product
})
```

```vue
<script setup lang="ts">
const route = useRoute()
const { data: product, status, error } = await useFetch(`/api/products/${route.params.id}`)
</script>
```

## Common Mistakes

- **Destructuring `reactive()` or a store kills reactivity.** `const { count } = reactive(...)` or `const { items } = useCartStore()` yields dead plain values. Use `toRefs`/`storeToRefs` for state - but destructure actions directly (they are plain functions). Props destructured from `defineProps` ARE reactive in 3.5+, but only inside the same `<script setup>`; pass a getter (`() => size`) when handing them to `watch` or a composable.
- **`ref` vs `reactive` vs `shallowRef` chosen wrong.** Default to `ref` for everything, including objects (`.value` is uniform and survives reassignment). `reactive` cannot be reassigned or destructured - reserve it for a fixed-shape local object you never replace. Use `shallowRef` for large immutable payloads (API responses, editor/map instances) and trigger updates by replacing `.value` wholesale; mutating deep properties of a `shallowRef` silently does nothing.
- **`watch` given a `.value` or plain property watches nothing.** `watch(count.value, ...)` and `watch(props.id, ...)` pass a snapshot. Watch the ref itself (`watch(count, ...)`) or a getter (`watch(() => props.id, ...)`). Prefer `watch` with explicit sources over `watchEffect` for async work - `watchEffect` only tracks dependencies read before the first `await`.
- **Fetching in Nuxt with bare `$fetch` in setup double-fetches.** It runs on the server and again on the client with no payload transfer. Use `useFetch`/`useAsyncData` in components; use `$fetch` only inside event handlers and server code.
- **Options API, `Vue.observable`, mixins, `this.$emit`, filters** - Vue 2/Options idioms that dominate training data. Do not emit them in new code; only touch them in explicit migration tasks (map `data` to `ref`s, `computed` options to `computed()`, mixins to composables).
- **Hydration mismatch from browser-only or random values in render.** `Date.now()`, `Math.random()`, `window.*`, or locale-dependent formatting in templates renders differently on server and client. Gate with `<ClientOnly>`, `useId()` for stable IDs, or compute in `onMounted`.
- **Testing implementation details via `wrapper.vm` or shallow mounting.** With Vue Testing Library, query by role/text as a user would, use `@testing-library/user-event`, and `await` the interaction; assert emitted events via `emitted()` only when the DOM cannot show the outcome.
