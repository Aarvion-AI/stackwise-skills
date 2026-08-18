# Widget Rebuild & Render Performance

Flutter perf work is 90% "rebuild less, repaint less, lay out less". Measure
first: DevTools > Performance (frame chart) and the Widget Rebuild Stats in the
IDE, plus `flutter run --profile` on a real device - debug-mode jank is not evidence.

## 1. const: the cheapest win

A `const` widget is canonicalized - Flutter short-circuits its rebuild when the
parent rebuilds. Enable the lints and fix every hit:

```yaml
# analysis_options.yaml
linter:
  rules:
    prefer_const_constructors: true
    prefer_const_constructors_in_immutables: true
    prefer_const_literals_to_create_immutables: true
```

```dart
// Bad: rebuilt (and re-instantiated) every parent build
Padding(padding: EdgeInsets.all(8), child: Icon(Icons.star))
// Good:
const Padding(padding: EdgeInsets.all(8), child: Icon(Icons.star))
```

Give every public widget a `const` constructor with `super.key` so callers *can*
use const. If a subtree can't be const because one leaf takes runtime data, pass
that leaf in as a `child` parameter so the rest stays const (the classic
`AnimatedBuilder`/`ListenableBuilder` `child:` pattern):

```dart
ListenableBuilder(
  listenable: controller,
  // `child` is built ONCE, not per tick:
  child: const ExpensiveStaticSubtree(),
  builder: (context, child) =>
      Transform.rotate(angle: controller.value, child: child),
)
```

## 2. Narrow what you watch

```dart
// Riverpod: rebuild only when .name changes, not on any user change
final name = ref.watch(userProvider.select((u) => u.name));

// Bloc: same idea
final name = context.select((UserCubit c) => c.state.name);
// or BlocBuilder(buildWhen: (p, n) => p.name != n.name, ...)

// InheritedWidget lookups - use the scoped aspects (3.10+):
final size = MediaQuery.sizeOf(context);      // not MediaQuery.of(context).size
final padding = MediaQuery.paddingOf(context);
final scheme = Theme.of(context).colorScheme; // Theme is fine; MediaQuery.of is the trap
```

`MediaQuery.of(context)` subscribes to **every** media-query change - keyboard
inset changes will rebuild your whole screen. The `sizeOf`/`paddingOf`/
`viewInsetsOf` variants subscribe per-aspect.

Push state down: a `StatefulWidget` (or `Consumer`) wrapping only the text that
changes beats `setState` on the whole screen. `setState` marks the entire
widget's subtree dirty - the framework can't skip children that "didn't use" the
state.

## 3. Keys - when and which

Keys matter when **stateful** children of the same runtime type are reordered,
inserted, or removed. Without keys, Flutter matches old/new children by index and
type, so state (text field contents, animation, scroll) sticks to the *position*,
not the item.

```dart
ListView.builder(
  itemCount: todos.length,
  itemBuilder: (context, i) => TodoTile(
    key: ValueKey(todos[i].id),   // stable identity across reorders
    todo: todos[i],
  ),
)
```

- `ValueKey(id)` - default choice for list items with stable ids.
- `ObjectKey(obj)` - identity by object instance.
- `UniqueKey()` - forces state loss every build; almost always a bug unless you
  *want* to reset state.
- `GlobalKey` - expensive, allows moving state across the tree and accessing
  `State`; use only for `Form`/`Navigator`-style access, never for list items.
- Don't add keys "for performance" to stateless children - they change matching,
  not speed.

## 4. Lists and slivers

- `ListView.builder`/`.separated`, never `ListView(children: hugeList)`.
- Uniform rows: set `itemExtent:` (or `prototypeItem:`) - skips per-child layout
  and makes scrollbar/jump math O(1).
- `shrinkWrap: true` + `NeverScrollableScrollPhysics` inside a `Column` forces
  full layout of all children - replace the outer scroll view with a
  `CustomScrollView` + `SliverList`/`SliverGrid` instead.
- `cacheExtent:` tunes how much off-screen content builds ahead.
- Images in lists: give `Image.network(..., cacheWidth:)`/`cacheHeight:` or use a
  caching package; decoding full-size images per cell is a top jank source.
- `AutomaticKeepAliveClientMixin` keeps item state alive off-screen - costs
  memory; prefer lifting state out of the item instead.

## 5. Repaint and layout isolation

```dart
// Animation repaints 60/120fps - fence it off so it doesn't repaint the page:
RepaintBoundary(child: SpinningLogo())
```

- Check with DevTools "Highlight repaints" (or
  `debugRepaintRainbowEnabled = true`): anything flashing that shouldn't be
  painting is a candidate for `RepaintBoundary` or restructuring.
- `Opacity(opacity: x, child: big)` forces an offscreen buffer; for animations
  use `FadeTransition`/`AnimatedOpacity`; for a single color/image just use a
  translucent color. Same for `ClipRRect` everywhere - prefer
  `Container(decoration: BoxDecoration(borderRadius: ...))` when clipping isn't
  really needed.
- Avoid `saveLayer` triggers in hot paths (Opacity, some blend modes, shadows on
  huge shapes) - they show up as raster-thread jank in the frame chart.
- `LayoutBuilder`/intrinsic-size widgets (`IntrinsicHeight`, `IntrinsicWidth`)
  cause extra layout passes - fine occasionally, expensive per-row in lists.

## 6. Build-method hygiene

- `build()` must be side-effect free and cheap; it can run every frame during
  animations. No allocation-heavy parsing, sorting, or filtering in `build` -
  memoize in state/provider (`select` a derived provider) and pass results in.
- Don't create controllers, futures, or streams in `build`:
  `FutureBuilder(future: fetch())` refetches on every rebuild. Create the future
  in `initState`/a provider and pass the same instance.
- Split large `build` methods into **widget classes**, not helper methods.
  `Widget _buildHeader()` re-executes with every parent build; a
  `const Header()` class can be skipped entirely and gets its own element.

## 7. Measuring - trust the tools

```bash
flutter run --profile            # perf numbers are only valid here / release
```

- DevTools Performance page: red frames = over budget (16.7ms @60Hz); check which
  thread - UI thread = Dart/build/layout cost, Raster thread = paint/shader cost.
- First-run shader jank on iOS/older Android is mostly solved by Impeller
  (default renderer on iOS and Android in current Flutter); if you still see it,
  confirm Impeller isn't disabled in the manifest/Info.plist.
- `flutter run --trace-skia`, `Timeline.startSync('label')` for custom spans.
- Widget rebuild counts: DevTools > Performance > "Track widget builds", or the
  Flutter IDE plugins' rebuild stats. Fix the top offenders, re-measure, repeat.
