# Lists & Animations Performance (FlashList, Reanimated 3)

Two frame budgets: JS thread (business logic, React renders) and UI thread (layout, gestures, Reanimated worklets). Jank comes from blowing either one. Diagnose before fixing: dev menu → Perf Monitor, watch both FPS numbers while reproducing.

## Lists: FlashList by default

`FlatList` recreates cells; `@shopify/flash-list` recycles them. For any list that can exceed ~1 screen of items, use FlashList.

```tsx
import { FlashList, ListRenderItem } from '@shopify/flash-list';

type Product = { id: string; title: string; price: number };

const ProductRow = React.memo(function ProductRow({ product }: { product: Product }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Open ${product.title}`}
      testID={`product-${product.id}`}
      onPress={() => router.push({ pathname: '/product/[id]', params: { id: product.id } })}
    >
      <Text>{product.title}</Text>
    </Pressable>
  );
});

const renderItem: ListRenderItem<Product> = ({ item }) => <ProductRow product={item} />;

export function ProductList({ products }: { products: Product[] }) {
  return (
    <FlashList
      data={products}
      renderItem={renderItem}
      keyExtractor={(p) => p.id}
      estimatedItemSize={72}          // measured, not guessed - see below
      getItemType={(p) => (p.price > 0 ? 'paid' : 'free')} // heterogeneous rows recycle per type
      testID="product-list"
    />
  );
}
```

Rules:
- `estimatedItemSize`: measure a real row once (FlashList warns with the ideal value in dev) and hard-code it. Wildly wrong estimates cause blank areas while scrolling.
- Hoist `renderItem` and memoize row components. An inline arrow + non-memoized row re-renders every cell on every parent render.
- `getItemType` for mixed row kinds (headers, ads, messages-by-sender) so recycling pools don't thrash.
- Recycled cells keep component **state**. Derive everything from `item` props; never store per-row state (e.g. "expanded") inside the row - lift it to a map keyed by id.
- Never put a virtualized list inside a plain `ScrollView` with the same scroll axis. Use `ListHeaderComponent`/`ListFooterComponent` instead.
- Images in rows: fixed dimensions + `expo-image` with `recyclingKey={item.id}`, so recycled cells don't flash stale images.

## Re-render storms

Before touching the list, kill parent-driven re-renders:

- Context that changes per keystroke (search text) must not wrap the list - split contexts or pass the query only to the header.
- `useCallback`/`useMemo` for every prop passed into the list (`onEndReached`, `ItemSeparatorComponent`, style objects).
- With React 19 / React Compiler enabled, manual memoization matters less - but FlashList's `renderItem` identity and row memoization still matter because recycling is not React reconciliation.

## Reanimated 3: worklets

Reanimated animations run as **worklets on the UI thread**. The JS thread can be fully blocked and the animation still runs at 60fps.

```tsx
import Animated, {
  useSharedValue, useAnimatedStyle, withTiming, withSpring,
  interpolate, runOnJS,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';

export function SwipeCard({ onDismiss }: { onDismiss: () => void }) {
  const x = useSharedValue(0);

  const pan = Gesture.Pan()
    .onChange((e) => { x.value += e.changeX; })                 // worklet
    .onEnd(() => {
      if (Math.abs(x.value) > 120) {
        x.value = withTiming(Math.sign(x.value) * 500, { duration: 150 }, (finished) => {
          if (finished) runOnJS(onDismiss)();                    // JS calls need runOnJS
        });
      } else {
        x.value = withSpring(0);
      }
    });

  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: x.value }],
    opacity: interpolate(Math.abs(x.value), [0, 300], [1, 0.4]),
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={style} testID="swipe-card" />
    </GestureDetector>
  );
}
```

Worklet rules:
- **In**: data crosses into a worklet via shared values (`useSharedValue`) or captured constants. Reading React state inside a worklet captures a stale snapshot.
- **Out**: calling a JS function from a worklet requires `runOnJS(fn)(args)`. Calling it directly crashes ("tried to synchronously call a non-worklet function").
- Assign `sv.value = x`; never mutate nested objects in place (reassign the whole `.value`).
- `useAnimatedStyle` must be pure over shared values - no `setState`, no navigation, no fetch.
- `useDerivedValue` for computed shared values; `useAnimatedReaction` to respond to changes with side effects.
- Animate `transform` and `opacity` (GPU-composited). Animating `width`/`height`/`top`/`left` forces layout every frame - use transforms or Reanimated Layout Animations (`entering={FadeIn}`, `layout={LinearTransition}`) instead.

## Gesture Handler pairing

- Root layout must be wrapped in `<GestureHandlerRootView style={{ flex: 1 }}>` (once, in `app/_layout.tsx`).
- Use the `Gesture.*` builder API + `GestureDetector`; the old `useAnimatedGestureHandler` + `PanGestureHandler` component API is legacy.
- Compose with `Gesture.Simultaneous`, `Gesture.Race`, `Gesture.Exclusive`; inside lists use `.activeOffsetX(...)` so horizontal swipes don't hijack vertical scroll.

## Startup and general performance

- New Architecture (0.76+) is bridgeless: JS↔native calls are synchronous JSI, so chatty modules are cheaper, but a slow synchronous native call now *blocks* JS - keep heavy native work async.
- Hermes is the default engine; check `global.HermesInternal` if unsure. Enable `expo-dev-client` + release-mode profiling before believing any perf number: dev mode is 2-5x slower.
- Defer non-critical work post-interaction: `InteractionManager.runAfterInteractions`, or lazy-load heavy screens.
- Big JSON parses and image processing belong off the JS thread (native module, or `react-native-worklets` runtimes) - not in a `useEffect` during navigation.
