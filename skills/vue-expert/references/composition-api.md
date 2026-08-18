# Composition API (Vue 3.5+)

All new code is `<script setup lang="ts">`. Options API appears only in migration notes at the end.

## Component skeleton

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'

// Reactive props destructure (3.5+): defaults inline, no withDefaults
const { items, dense = false } = defineProps<{
  items: Item[]
  dense?: boolean
}>()

// Type-only emits (tuple syntax)
const emit = defineEmits<{
  select: [item: Item]
  clear: []
}>()

const query = ref('')
const filtered = computed(() =>
  items.filter((i) => i.name.includes(query.value)),
)
</script>

<template>
  <input v-model="query" />
  <ul :class="{ dense }">
    <li v-for="item in filtered" :key="item.id" @click="emit('select', item)">
      {{ item.name }}
    </li>
  </ul>
</template>
```

Rules:
- Destructured props are reactive **inside this `<script setup>` only**. When passing to `watch` or a composable, wrap in a getter: `watch(() => dense, ...)`, `useThing(() => items)`. Passing `dense` bare passes a snapshot.
- `withDefaults` + non-destructured `props` object still works but is legacy style; prefer destructure.
- Runtime `defineProps({ ... })` object syntax only when you need custom `validator`s.

## defineModel

`defineModel()` (stable since 3.4) replaces the manual `modelValue` prop + `update:modelValue` emit pair:

```vue
<script setup lang="ts">
// <MyInput v-model="name" v-model:age="age" />
const name = defineModel<string>({ required: true })
const age = defineModel<number>('age', { default: 0 })

// With modifiers: <MyInput v-model.trim="name" />
const [value, modifiers] = defineModel<string>({
  set: (v) => (modifiers.trim ? v.trim() : v),
})
</script>
```

- It is a writable ref: `name.value = 'x'` emits the update; no manual emit.
- Do NOT also declare `modelValue` in `defineProps` - collision.
- Local mutation without a parent binding still works (Vue backs it with a local ref).

## ref vs reactive vs shallowRef vs shallowReactive

| Tool | Use for | Gotcha |
|------|---------|--------|
| `ref` | Default for ALL state, primitives and objects | `.value` in script; auto-unwrapped in template and when top-level in `reactive` |
| `computed` | Derived values | Never mutate inside; use writable computed (`get`/`set`) for v-model proxies |
| `reactive` | Fixed-shape local object never reassigned (e.g. form model) | Cannot reassign (`form = {...}` breaks reactivity), cannot destructure, `ref`s inside auto-unwrap |
| `shallowRef` | Large immutable data, class instances (editor, map, chart), perf-critical lists | Deep mutation is invisible; replace `.value` wholesale, or call `triggerRef(r)` after a known deep mutation |
| `shallowReactive` | Rare: top-level-only tracking | Same deep-blindness |
| `customRef` | Debounced/throttled refs | Must call `track()`/`trigger()` yourself |

```ts
// shallowRef: swap, don't mutate
const rows = shallowRef<Row[]>([])
rows.value = [...rows.value, newRow]   // triggers
rows.value.push(newRow)                 // does NOT trigger

// Non-reactive on purpose (third-party instances): markRaw
const map = shallowRef(markRaw(new maplibregl.Map({ ... })))
```

`toRef`/`toRefs` bridge `reactive` to refs: `const { email } = toRefs(form)`.
`toValue(x)` unwraps ref | getter | plain value - the normalizer every composable argument should pass through.

## Composables design

Contract for `useX()`:

1. **Return an object of plain refs** - callers can destructure safely. Returning `reactive({...})` breaks on destructure.
2. **Accept `MaybeRefOrGetter<T>` inputs**, normalize with `toValue()` inside effects so changes re-trigger.
3. **Register lifecycle/cleanup synchronously** - `onMounted`, `onScopeDispose` must run during setup, never after `await`.
4. **Side effects live in effects** (`watchEffect`/`watch`), state in refs; the composable body runs once.

```ts
import { ref, watchEffect, toValue, onScopeDispose, type MaybeRefOrGetter } from 'vue'

export function useFetchJson<T>(url: MaybeRefOrGetter<string>) {
  const data = ref<T | null>(null)
  const error = ref<Error | null>(null)
  const loading = ref(false)

  watchEffect(async (onCleanup) => {
    const u = toValue(url)          // read BEFORE await so it is tracked
    const ac = new AbortController()
    onCleanup(() => ac.abort())     // cancel stale request on re-run
    loading.value = true
    error.value = null
    try {
      const res = await fetch(u, { signal: ac.signal })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      data.value = await res.json()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') error.value = e as Error
    } finally {
      loading.value = false
    }
  })

  return { data, error, loading }
}
```

- Prefer `onScopeDispose` over `onUnmounted` in composables - it also works inside `effectScope()` and Pinia stores.
- Async composables: anything after the first `await` loses the active instance; call `onMounted` etc. before awaiting.

## Async setup after await

In `<script setup>`, `await` is allowed (compiles to async setup) but the component then **requires `<Suspense>`** (or Nuxt, which wraps pages in it). In plain Vite SPAs without Suspense, do async work in `onMounted` or a composable's effect instead.

## Template refs (3.5+)

```vue
<script setup lang="ts">
import { useTemplateRef, onMounted } from 'vue'
const input = useTemplateRef('input')          // typed from the template
onMounted(() => input.value?.focus())
</script>

<template>
  <input ref="input" />
</template>
```

`useTemplateRef('name')` replaces the old `const input = ref(null)` name-matching convention. For component refs, expose an API explicitly:

```ts
defineExpose({ focus: () => input.value?.focus() })
```

## provide/inject, typed

```ts
// keys.ts
import type { InjectionKey, Ref } from 'vue'
export const ThemeKey: InjectionKey<Ref<'light' | 'dark'>> = Symbol('theme')

// parent
provide(ThemeKey, theme)

// child - always give a default or handle undefined
const theme = inject(ThemeKey, ref('light'))
```

Use provide/inject for subtree-scoped context (form context, design-system config), Pinia for app state. Never inject with string keys in TS code.

## Other 3.4-3.6 APIs worth using

- `useId()` - SSR-stable unique IDs for `label for` / `aria-*`.
- `defineOptions({ inheritAttrs: false })` - options that have no macro.
- `defineSlots<{ default(props: { item: Item }): any }>()` - typed scoped slots.
- `v-bind` in `<style>`: `color: v-bind(accent)` for reactive CSS.
- `defineAsyncComponent(() => import('./Heavy.vue'))` + `hydrateOnVisible()` hydration strategy for lazy hydration.

## Options API migration notes (only when converting old code)

| Options API | Composition |
|-------------|-------------|
| `data()` fields | `ref()` per field |
| `computed:` | `computed(() => ...)` |
| `methods:` | plain functions |
| `watch:` option | `watch()` calls |
| `mounted()` etc. | `onMounted()` etc. (no `beforeCreate`/`created` - setup body IS that phase) |
| `this.$emit` | `defineEmits` + `emit()` |
| `this.$refs.x` | `useTemplateRef('x')` |
| mixins | composables |
| `$attrs`/`$slots` | `useAttrs()` / `useSlots()` |

Convert whole components at once; mixing `this.` access with setup state is the main source of migration bugs.
