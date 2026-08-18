# Expo Router Navigation (Expo Router 5, SDK 53+)

File-based routing: the `app/` directory is the navigation tree. Every file is a route; every `_layout.tsx` is a navigator. No `NavigationContainer`, no manual linking config.

## Route file conventions

```
app/
  _layout.tsx          # root layout (Stack) - wraps everything
  index.tsx            # "/"
  sign-in.tsx          # "/sign-in"
  (tabs)/              # route group: no URL segment
    _layout.tsx        # Tabs navigator
    index.tsx          # "/" inside tabs
    search.tsx         # "/search"
  product/
    [id].tsx           # "/product/123"  (dynamic)
  [...unmatched].tsx   # catch-all / 404
  modal.tsx            # presented modally via Stack options
```

- `(group)/` groups routes without affecting the URL - used for tab sections, auth areas.
- `[id].tsx` dynamic segment; `[...rest].tsx` catch-all.
- `+not-found.tsx` renders for unmatched routes.
- `app/_layout.tsx` replaces `App.tsx`; put providers (theme, query client, gesture root) there.

## Layouts and navigators

```tsx
// app/(tabs)/_layout.tsx
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

export default function TabLayout() {
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: '#0a7ea4' }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => <Ionicons name="home" color={color} size={size} />,
          tabBarButtonTestID: 'tab-home',
        }}
      />
      <Tabs.Screen name="search" options={{ title: 'Search', tabBarButtonTestID: 'tab-search' }} />
    </Tabs>
  );
}
```

```tsx
// app/_layout.tsx - root stack with a modal
import { Stack } from 'expo-router';

export default function RootLayout() {
  return (
    <Stack>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="modal" options={{ presentation: 'modal', title: 'Filters' }} />
    </Stack>
  );
}
```

A nested `_layout.tsx` must list child screens by **file name** (`name="(tabs)"`, not a path). Options for a screen can also be set inside the screen file with `<Stack.Screen options={...} />` at the top of the component.

## Navigating

```tsx
import { Link, router, useLocalSearchParams } from 'expo-router';

// Declarative
<Link href="/product/42" asChild>
  <Pressable accessibilityRole="link" testID="product-42"><Text>Open</Text></Pressable>
</Link>

// Imperative
router.push({ pathname: '/product/[id]', params: { id: '42' } });
router.replace('/sign-in');   // no back entry
router.back();
router.dismissTo('/');        // pop until "/" (Router 5)

// Reading params in app/product/[id].tsx
const { id } = useLocalSearchParams<{ id: string }>();
```

- `push` stacks; `replace` swaps; `navigate` dedupes (goes back to an existing instance if present).
- Params are always strings (or string[]). Parse numbers yourself.
- `useLocalSearchParams` = params of this screen; `useGlobalSearchParams` re-renders on any URL change - avoid it in lists.

## Typed routes

Enable once; `href` strings and `router.push` become compile-checked:

```jsonc
// app.json
{ "expo": { "experiments": { "typedRoutes": true } } }
```

Generated types land in `.expo/types`. Invalid paths like `href="/producst/42"` become type errors - run `npx tsc --noEmit` to catch them.

## Auth gating (Protected routes, Router 5)

```tsx
// app/_layout.tsx
import { Stack } from 'expo-router';
import { useSession } from '@/lib/session';

export default function Root() {
  const { user, isLoading } = useSession();
  if (isLoading) return null; // don't flash the wrong stack
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={!user}>
        <Stack.Screen name="sign-in" />
      </Stack.Protected>
    </Stack>
  );
}
```

When `guard` flips to false, users on those screens are redirected to the first available route. Pre-Router-5 fallback: `<Redirect href="/sign-in" />` from a layout. Never return different navigator trees from the same layout based on state - it remounts the whole tree.

## Deep links and universal links

- Set `"scheme": "myapp"` in `app.json`; every route is automatically a deep link (`myapp://product/42`).
- Universal links need `associatedDomains` (iOS) + `intentFilters` (Android) in `app.json` and server-side AASA/assetlinks files.
- Test with `npx uri-scheme open "myapp://product/42" --ios` (or `--android`).
- A cold-start deep link mounts the target route directly; give inner screens a working back affordance via `router.dismissTo('/')` or `initialRouteName` on the group:

```tsx
export const unstable_settings = { initialRouteName: 'index' }; // in a _layout.tsx
```

## Common pitfalls

- **Files in `app/` that are not routes** (components, helpers) become routes. Keep shared code in `src/` or `components/` outside `app/`.
- **`router.push` in an effect on mount** fires before the root layout is ready → "navigate before mounting" error. Use `<Redirect>` for render-time redirects.
- **Modals**: `presentation: 'modal'` is a *screen option on the Stack*, not a separate navigator. Dismiss with `router.back()` / `router.dismiss()`.
- **Nested params shadowing**: a `[id].tsx` inside another `[id]` segment - rename one (`[productId]`) or params collide.
- **Headers**: default Stack header is native. Hide per-screen (`headerShown: false`), don't wrap screens in custom SafeAreaView + custom header unless design requires it.
