# Reactivity Pitfalls and Edge Cases

The bugs behind "it doesn't update", "it fires twice", and "hydration mismatch".

## Losing reactivity by destructuring

```ts
const state = reactive({ count: 0, user: { name: 'a' } })

const { count } = state          // DEAD: plain number snapshot
let { user } = state             // user is still a reactive proxy (object),
                                 // but reassigning `user = ...` won't touch state

const { count: c } = toRefs(state)   // LIVE: c is a ref linked to state.count
```

Same trap with Pinia (`storeToRefs`, see state-pinia.md) and with function arguments: passing `state.count` into a function passes a number. Pass the ref, a getter `() => state.count`, or accept `MaybeRefOrGetter` + `toValue`.

**Props (3.5+):** destructured `defineProps` bindings ARE reactive - the compiler rewrites `size` to `props.size` - but only in the same `<script setup>`. Crossing a function boundary needs a getter:

```ts
const { userId } = defineProps<{ userId: string }>()
watch(() => userId, load)        // RIGHT
watch(userId, load)              // WRONG: watches a frozen string, warns in dev
useUser(() => userId)            // RIGHT for composables
```

## watch: valid and invalid sources

Valid sources: a ref, a reactive object, a getter, or an array of those.

```ts
watch(count, cb)                       // ref: cb(new, old)
watch(() => props.id, cb)              // getter for a property
watch([count, () => props.id], cb)     // multiple
watch(state, cb)                       // reactive object: implicit deep, old === new (same proxy)
watch(() => state.items, cb, { deep: true })  // getter to object needs deep for mutations
watch(() => state.items, cb, { deep: 1 })     // 3.5+: bounded depth, cheaper
```

Invalid: `watch(count.value, ...)`, `watch(state.count, ...)` - a number is not a source.

Options that change behavior:
- `{ immediate: true }` - run on setup too (the "load now and on change" pattern).
- `{ once: true }` - auto-stop after first trigger (3.4+).
- `{ flush: 'post' }` - callback sees updated DOM; `watchPostEffect` shorthand. Default `'pre'` runs before render; `'sync'` fires per-mutation (rarely wanted - no batching).
- Cleanup: `watch(src, (v, old, onCleanup) => { onCleanup(() => ac.abort()) })` or `onWatcherCleanup()` (3.5+, sync-only, before `await`).
- Stop handle: `const stop = watch(...)`; automatic when created inside setup scope, manual (`stop()`) when created in async callbacks or outside components - those leak otherwise.

## watch vs watchEffect

- `watch`: explicit sources, lazy, gives old value, best for async work and "when X changes do Y".
- `watchEffect`: runs immediately, auto-tracks whatever it reads **synchronously before the first `await`**. Dependencies read after an `await` (or inside `setTimeout`/callbacks) are NOT tracked:

```ts
watchEffect(async () => {
  const id = route.params.id        // tracked
  const res = await fetchUser(id)
  if (filter.value) { ... }         // NOT tracked - after await
})
```

Rule: async effects with multiple dependencies → `watch` with an explicit array. `watchEffect` shines for short sync effects (syncing a ref to localStorage, DOM attribute mirroring).

## Effects run once per flush, not per mutation

```ts
items.value.push(a)
items.value.push(b)
count.value++
// one flush: watchers/render run once with the final state, next microtask
await nextTick()                    // DOM updated now
```

Never read the DOM right after a mutation without `await nextTick()`. Don't "fix" batching with `flush: 'sync'`.

## Reactive proxy identity traps

```ts
const raw = { id: 1 }
const proxy = reactive(raw)
proxy === raw                        // false
const set = new Set([raw])
set.has(proxy)                       // false - mixing raw and proxy breaks lookups
```

- Keep one world: store proxies, compare proxies. `toRaw(proxy)` escapes deliberately; `isReactive`/`isRef` to introspect.
- Arrays: `arr.value.find(x => x === someRaw)` fails if `someRaw` was stored reactively. Compare by id, not identity.
- Refs nested in `reactive` auto-unwrap: `state.someRef` is the value, no `.value`. But refs in arrays/Maps inside reactive do NOT unwrap.
- Template auto-unwrap only applies to **top-level** bindings: `{{ obj.someRef }}` renders the ref object; `{{ obj.someRef.value }}` or destructure to top level first. (`{{ count + 1 }}` works when `count` is top-level.)

## shallowRef pitfalls

```ts
const data = shallowRef({ list: [] as Item[] })
data.value.list.push(item)           // silent no-op for the UI
data.value = { list: [...data.value.list, item] }   // triggers
triggerRef(data)                     // or force after a known deep mutation
```

Vue's own APIs hand you shallow data sometimes (e.g. `useFetch` data is deep by default in Nuxt but can be `deep: false`); check before mutating nested fields.

## v-model edge cases

- `v-model` on a prop directly (`v-model="props.value"`) - mutating props, warns. Use `defineModel` in the child or a writable computed proxying to emit.
- Binding `v-model` to a nested store field from a component: fine (`v-model="form.email"` where `form` is store state), but consider actions if there is validation logic.
- `v-model` + `<input type="number">`: use `v-model.number`, and remember empty input gives `''` not `0`.

## Computed pitfalls

- A computed that **mutates** state or fires requests is a bug - move side effects to `watch`. Computed getters must be pure; Vue may call or skip them at any time (they are cached until deps change).
- Computed returning a new array/object each run is fine for templates but makes `watch(computedVal, cb)` fire on every dependency change even if contents are equal - compare in the callback or watch the underlying source.
- Previous-value access (3.4+): `computed((prev) => expensive ? recompute() : prev)`.

## SSR hydration mismatches

Symptoms: `Hydration node mismatch`/`Hydration text content mismatch` warnings, UI flicker, or event handlers attached to wrong nodes.

Causes and fixes:

| Cause | Fix |
|-------|-----|
| `Date.now()`, `Math.random()`, `new Date().toLocaleString()` in render | Compute once server-side and pass through payload, or render in `onMounted`, or `useId()` for unique ids |
| `window`/`localStorage`-derived initial state (theme, auth) | Initialize neutral, apply client value in `onMounted`; or cookie-based so server knows too |
| Invalid HTML nesting (`<div>` inside `<p>`, `<tr>` outside `<table>`) | Browser reparses server HTML differently than vnode tree - fix the markup |
| Timezone/locale differences server vs client | Format dates from an explicit locale + UTC, or client-only |
| Randomized order / non-deterministic v-for | Sort deterministically before render |
| Browser extensions mutating DOM | `data-allow-mismatch` attribute (3.5+) on the tolerated node, scoped: `data-allow-mismatch="text"` |
| Auth-dependent content | `<ClientOnly>` or `server: false` fetching with skeletons |

Debug: the warning logs the DOM node - find the component, then find the nondeterminism. In Nuxt, reproduce with `pnpm build && node .output/server/index.mjs` (dev SSR can mask timing).

## Memory leaks checklist

- Watchers/computeds created in `setTimeout`, event handlers, or after `await` in async setup are outside the scope - keep and call their stop handles, or create inside `effectScope()` and `scope.stop()`.
- Event listeners/intervals in composables: pair with `onScopeDispose`.
- `$subscribe`/`store.$onAction` with `{ detached: true }` never auto-unsubscribe.
