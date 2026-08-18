---
name: react-native-expert
description: Use when building or debugging React Native apps - files using .tsx with react-native imports, app.json/app.config.ts, expo-router app/ directories, metro.config.js, eas.json, or mentions of Expo, Fabric, TurboModules, Reanimated, FlashList, or Maestro. Builds screens and navigation with Expo Router, integrates native modules, optimizes lists and animations, sets up EAS Build/Update, and writes Jest/RNTL and Maestro tests. Invoke for navigation and deep linking, New Architecture migration, list/animation performance, platform-specific code, native module authoring, and release pipeline setup.
license: MIT
metadata:
  version: "0.1.0"
  category: mobile
  frameworks: React Native 0.7x (New Architecture default), Expo SDK 53+, Expo Router 5, Reanimated 3, TypeScript 5
  triggers: react native, expo, expo router, eas build, eas update, fabric, turbomodule, new architecture, reanimated, flashlist, maestro, native module, app.json, metro
  related: mobile-qa-expert, react-expert, nestjs-expert
---

# React Native Expert

Turns Claude into a senior React Native engineer who ships Expo-managed, New Architecture apps with TypeScript, tested navigation, 60fps lists, and a working EAS release pipeline.

## When to Use This Skill

- Building screens, layouts, tabs, or modals with Expo Router file-based navigation
- Deciding between Expo managed workflow, prebuild (CNG), and bare React Native
- Migrating to or debugging the New Architecture (Fabric renderer, TurboModules, bridgeless mode)
- Fixing dropped frames in long lists (FlashList) or animations (Reanimated 3 worklets)
- Writing platform-specific code (iOS/Android/web) without forking the whole component tree
- Authoring native modules with the Expo Modules API (Swift/Kotlin) or consuming third-party ones
- Setting up EAS Build, EAS Update, and a Jest + React Native Testing Library + Maestro test stack

## Core Workflow

1. **Analyze** - read `package.json` (RN and Expo SDK versions, `newArchEnabled` is default-on in 0.76+), `app.json`/`app.config.ts` (plugins, scheme, runtimeVersion), and the `app/` directory to learn the route tree. Check for `eas.json`, `metro.config.js`, and an existing test setup before writing anything. Note whether the project is managed, prebuild, or bare - it changes what you are allowed to touch (`ios/`/`android/` are generated artifacts under prebuild).
2. **Implement** - write TypeScript throughout. Use Expo Router conventions (`_layout.tsx`, `[param].tsx`, `(group)/`) for navigation, typed routes via `experiments.typedRoutes`. Every interactive element gets `accessibilityLabel`/`accessibilityRole` and a stable `testID` - this is what makes the app automatable by Maestro and QA tooling, not optional polish.
3. **Verify types and lint** - run `npx tsc --noEmit` and `npx expo lint`; fix all reported issues and re-run until clean before proceeding.
4. **Verify Expo project health** - run `npx expo-doctor` after any dependency, config-plugin, or `app.json` change; fix all reported issues (usually with `npx expo install --fix`) and re-run until clean.
5. **Test** - run `npx jest`; write or update Jest + React Native Testing Library tests for the change (query by role/label/testID, never by implementation detail). If any test fails, fix the code or the test and re-run until all pass. For flows that cross screens, add or update a Maestro flow in `.maestro/` and run `maestro test .maestro/` until it passes.
6. **Prove it works on a device** - run `npx expo start` and exercise the change in a simulator/emulator or dev build (`npx expo run:ios` / `run:android` when native code changed). Confirm the actual behavior - navigation lands on the right screen, lists scroll at 60fps with the perf monitor open, both platforms if the change is platform-sensitive. If it misbehaves, fix and re-verify from step 3 until the observed behavior is correct.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Expo Router navigation | `references/expo-router-navigation.md` | Creating/altering routes, layouts, tabs, modals, deep links, auth-gated navigation, typed routes |
| Lists & animations performance | `references/performance-lists-animations.md` | FlashList usage, dropped frames, Reanimated 3 worklets, gesture-driven UI, re-render storms |
| Native modules & New Architecture | `references/native-modules.md` | Writing an Expo Module (Swift/Kotlin), TurboModules/Fabric questions, config plugins, prebuild |
| Platform-specific code | `references/platform-handling.md` | iOS/Android/web divergence, safe areas, keyboard handling, permissions, platform file extensions |
| Testing & release | `references/testing-release.md` | Jest/RNTL setup, Maestro flows, accessibility/testID discipline, EAS Build/Update, versioning |

## Key Patterns

**Expo Router layout with auth gate (Router 5 / SDK 53+)** - gate with `<Stack.Protected>` or a layout redirect; never conditionally render `<Slot/>` by hand:

```tsx
// app/_layout.tsx
import { Stack } from 'expo-router';
import { useSession } from '@/lib/session';

export default function RootLayout() {
  const { user, isLoading } = useSession();
  if (isLoading) return null; // keep splash until auth state known
  return (
    <Stack>
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

**FlashList, not FlatList, for long lists** - fixed `estimatedItemSize`, memoized items, no inline arrow item renderers:

```tsx
import { FlashList } from '@shopify/flash-list';

const renderItem = ({ item }: { item: Product }) => <ProductRow product={item} />;

<FlashList
  data={products}
  renderItem={renderItem}
  estimatedItemSize={72}
  keyExtractor={(p) => p.id}
  testID="product-list"
/>
```

**Reanimated 3 worklet - UI-thread animation reacting to shared values**:

```tsx
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';

const offset = useSharedValue(0);
const style = useAnimatedStyle(() => ({
  transform: [{ translateX: withSpring(offset.value) }],
})); // runs on UI thread; never read React state here
return <Animated.Pressable style={style} onPress={() => { offset.value += 40; }} />;
```

**Accessible, automatable touch target** - every interactive element carries label, role, and testID:

```tsx
<Pressable
  accessibilityRole="button"
  accessibilityLabel="Add to cart"
  testID="add-to-cart"
  onPress={addToCart}
>
  <Text>Add to cart</Text>
</Pressable>
```

## Common Mistakes

- **Reaching for `react-navigation` config-first setup in an Expo Router app.** SDK 53+ projects use file-based routing; adding a hand-rolled `NavigationContainer` breaks deep linking and typed routes. Create files under `app/`, use `_layout.tsx` for navigators, and `router.push('/product/[id]')` style navigation.
- **Ejecting to bare workflow to add native code.** Almost never needed since config plugins and the Expo Modules API. Prefer: config plugin → local Expo Module → prebuild (CNG). Bare is for apps that must own `ios/`/`android/` (brownfield, exotic build systems). If `ios/` exists under prebuild, treat it as generated - edit `app.json` plugins, not the Xcode project.
- **Assuming the old bridge.** RN 0.76+ defaults to New Architecture: no `requireNativeComponent` bridging, `NativeModules.X` legacy modules may be missing, layout is synchronous under Fabric, and interop-layer warnings mean a dependency needs an upgrade - check library New Architecture support before adding it.
- **Reading React state or calling JS functions inside worklets.** `useAnimatedStyle`/`useAnimatedGestureHandler` bodies run on the UI thread. Use shared values for data in, `runOnJS` for calls out; capturing component state gives stale values or crashes.
- **`FlatList` with anonymous `renderItem` and no memoization for feeds.** Causes blank cells and dropped frames. Use FlashList with `estimatedItemSize`, hoist `renderItem`, memoize row components, and never nest a VirtualizedList inside a plain `ScrollView`.
- **Shipping untestable UI.** Missing `testID`/`accessibilityLabel` makes Maestro and RNTL queries brittle (falling back to text matching that breaks with copy changes). Add both to every interactive element as you write it, not retroactively.
- **Confusing EAS Update with app releases.** OTA updates ship only JS/assets within the same `runtimeVersion`; any native change (new library with native code, config plugin edit, SDK upgrade) requires a new EAS Build and store submission.
