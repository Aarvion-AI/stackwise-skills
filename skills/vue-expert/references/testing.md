# Testing - Vitest 3 + Vue Testing Library

Stack: `vitest` + `@testing-library/vue` + `@testing-library/user-event` + `@testing-library/jest-dom` matchers, jsdom (or happy-dom) environment. For Nuxt code, add `@nuxt/test-utils`. Avoid `@vue/test-utils` `wrapper.vm` poking in new tests; Testing Library's user-facing queries are the default.

## Setup (plain Vite app)

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
})
```

```ts
// vitest.setup.ts
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/vue'
import { afterEach } from 'vitest'
afterEach(() => cleanup())
```

## Component test - the canonical shape

```ts
import { render, screen } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SearchBox from '@/components/SearchBox.vue'

describe('SearchBox', () => {
  it('emits submit with the trimmed query', async () => {
    const user = userEvent.setup()
    const { emitted } = render(SearchBox, {
      props: { label: 'Search products' },
    })

    await user.type(screen.getByRole('textbox', { name: 'Search products' }), '  shoes  ')
    await user.keyboard('{Enter}')

    expect(emitted('submit')).toEqual([['shoes']])
  })

  it('shows results as the user types', async () => {
    const user = userEvent.setup()
    render(SearchBox, { props: { items: [{ id: '1', name: 'Shoes' }] } })

    await user.type(screen.getByRole('textbox'), 'sho')

    expect(await screen.findByRole('listitem')).toHaveTextContent('Shoes')
    expect(screen.queryByText('No results')).not.toBeInTheDocument()
  })
})
```

Non-negotiables:
- **Always `await` interactions** (`user.type`, `user.click`, `fireEvent.*`) - they flush Vue's async DOM updates. A missing `await` is the #1 flaky-Vue-test cause.
- Query priority: `getByRole` (with `name`) > `getByLabelText` > `getByText` > `getByTestId` (last resort).
- `getBy*` throws now; `findBy*` awaits appearance; `queryBy*` for asserting absence.
- Testing `v-model` from a parent's perspective: render with `props: { modelValue, 'onUpdate:modelValue': fn }` and assert the handler, or wrap in a tiny host component using real `v-model`.

## Props update and slots

```ts
const { rerender } = render(Badge, { props: { status: 'draft' } })
await rerender({ status: 'published' })
expect(screen.getByText('Published')).toBeInTheDocument()

render(Card, {
  slots: { default: '<p>Body</p>', title: 'Hello' },
})
```

## Stores in component tests

```ts
import { createTestingPinia } from '@pinia/testing'
import { useCartStore } from '@/stores/cart'

const { } = render(CartWidget, {
  global: {
    plugins: [createTestingPinia({ createSpy: vi.fn, stubActions: true })],
  },
})
const cart = useCartStore()      // same instance the component got
cart.items = [{ id: '1', price: 5, qty: 1 } as CartItem]
await nextTick()
expect(screen.getByText('1 item')).toBeInTheDocument()
expect(cart.add).not.toHaveBeenCalled()
```

`createSpy: vi.fn` is required under Vitest. For setup stores, mutate state after obtaining the store (the `initialState` option targets options-store state shape).

## Testing composables

Composables using lifecycle/inject must run inside a component; pure-reactivity ones can run bare:

```ts
// bare: no lifecycle hooks used
import { effectScope } from 'vue'
it('debounces', () => {
  const scope = effectScope()
  scope.run(() => {
    const { value } = useDebouncedRef(ref('a'), 100)
    // ... advance fake timers, assert
  })
  scope.stop()
})

// with lifecycle: mount a host
import { defineComponent } from 'vue'
function withSetup<T>(composable: () => T) {
  let result!: T
  const app = render(defineComponent({
    setup() { result = composable(); return () => null },
  }))
  return { result, unmount: app.unmount }
}

it('cleans up listener on unmount', () => {
  const { result, unmount } = withSetup(() => useWindowSize())
  expect(result.width.value).toBeGreaterThan(0)
  unmount()   // assert removeEventListener via spy
})
```

Fake timers with user-event need wiring: `vi.useFakeTimers()` then `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`.

## Mocking network

Prefer MSW (`msw/node`) over mocking `$fetch`/`axios` - tests survive refactors of the fetch layer:

```ts
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

const server = setupServer(
  http.get('/api/products/:id', ({ params }) =>
    HttpResponse.json({ id: params.id, name: 'Shoes' })),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

## Nuxt-specific tests

`@nuxt/test-utils` gives a Nuxt runtime environment (auto-imports, `useRoute`, plugins) inside Vitest:

```ts
// vitest.config.ts for a Nuxt repo
import { defineVitestConfig } from '@nuxt/test-utils/config'
export default defineVitestConfig({ test: { environment: 'nuxt' } })
```

```ts
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import ProductPage from '@/pages/products/[id].vue'

it('renders SSR-fetched product', async () => {
  registerEndpoint('/api/products/1', () => ({ id: '1', name: 'Shoes' }))
  const wrapper = await mountSuspended(ProductPage, { route: '/products/1' })
  expect(wrapper.text()).toContain('Shoes')
})
```

- `mountSuspended` handles async setup/`<Suspense>` - plain `render` fails on pages that `await useFetch`.
- Per-file environment opt-in when mixing unit and Nuxt tests: `// @vitest-environment nuxt` at file top, or name files `*.nuxt.spec.ts` with `environmentMatchGlobs`.
- `mockNuxtImport('useUserSession', () => () => ({ loggedIn: ref(true) }))` stubs auto-imports; it is hoisted - define per-test behavior via a `vi.hoisted` holder.
- Nitro route handlers are plain functions: unit test them by calling `defineEventHandler`'s inner logic with a mocked `event`, or e2e via `setup()` + `$fetch` from `@nuxt/test-utils/e2e` (slower; reserve for critical paths).

## Common testing mistakes

- Asserting immediately after a store/ref mutation without `await nextTick()` (or after an un-awaited interaction) - DOM not flushed yet.
- `screen.getByText` for async content instead of `findByText` - throws before data arrives.
- Shallow-mounting everything and asserting child component props - brittle; render real children, stub only heavy leaf components (`global: { stubs: { HeavyChart: true } }`).
- Testing composable internals via returned refs' identity rather than observable behavior.
- Forgetting `cleanup()`/fresh Pinia per test - state leaks make order-dependent green/red.
- Snapshot-testing whole components - churny and reviews poorly; snapshot only small stable fragments if at all.
