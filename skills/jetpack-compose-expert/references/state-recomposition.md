# State, Stability, and Recomposition

Compose BOM 2026.x / Kotlin 2.x. Strong skipping mode is ON by default (Compose compiler ships with Kotlin since 2.0; enabled by default since 2.0.20). Rules below assume it.

## State hoisting

Hoist state to the lowest common ancestor that reads or writes it. A composable owns state only when it is purely UI-local (text field focus animation, expanded flag nobody else needs).

```kotlin
// Stateful wrapper - thin, owns nothing but the ViewModel handle
@Composable
fun SearchScreen(viewModel: SearchViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    SearchContent(state, onQueryChange = viewModel::onQueryChange, onSubmit = viewModel::submit)
}

// Stateless - all data in, all events out. Previewable, testable.
@Composable
fun SearchContent(state: SearchUiState, onQueryChange: (String) -> Unit, onSubmit: () -> Unit) { ... }
```

For UI-local state that must survive rotation/process death, use `rememberSaveable`:

```kotlin
var query by rememberSaveable { mutableStateOf("") }
// Custom types: rememberSaveable(stateSaver = MySaver) { mutableStateOf(...) }
```

`remember` alone survives recomposition only; it is lost on configuration change.

## How skipping works (strong skipping mode)

On recomposition, Compose skips a composable call if every argument is unchanged:

- **Stable types** compare with `equals`.
- **Unstable types** (pre-2.0.20 behavior: never skipped) now compare with **instance equality** - same instance ⇒ still skips.
- **Lambdas** in composable calls are **auto-remembered** - you no longer need `remember { { ... } }` or method-reference workarounds for skipping. A lambda capturing unstable values is keyed on those captures.

Implications:

- Don't hand-`remember` lambdas for performance anymore; it's noise.
- Unstable params only break skipping when a **new instance** is created per recomposition/emission. `List` returned fresh from a `map {}` in the ViewModel every emission ⇒ new instance ⇒ no skip. Fix the model, not the call site.
- ViewModels, `Context`, listener objects passed down are unstable but usually the *same instance* - fine under strong skipping.

## Making UI models stable

```kotlin
// Preferred: immutable data class + immutable collections
@Immutable
data class FeedUiState(
    val items: ImmutableList<FeedItemUi> = persistentListOf(),
    val refreshing: Boolean = false,
)
```

- `kotlinx.collections.immutable` (`ImmutableList`, `PersistentList`) is inferred stable; `List`/`Map`/`Set` interfaces are not (a `MutableList` could hide behind them).
- `@Immutable`: promise that no property ever changes after construction. `@Stable`: values may change but the class notifies Compose (e.g. properties backed by `mutableStateOf`) and `equals` is consistent. Annotating a plain mutable class `@Immutable` to silence the compiler causes *missed* recompositions - never do it.
- Types from modules that don't apply the Compose compiler (pure-Kotlin domain modules) are inferred unstable. Options: apply `org.jetbrains.kotlin.plugin.compose` to the module, map to UI models in the ViewModel (preferred), or use a **stability configuration file**:

```kotlin
// build.gradle.kts (app module)
composeCompiler {
    stabilityConfigurationFiles.add(layout.projectDirectory.file("compose_stability.conf"))
}
// compose_stability.conf
com.example.domain.Order
com.example.domain.*   // wildcard for a package
kotlinx.datetime.Instant
```

## Reading state at the right scope

A composable recomposes when a `State` it *read* changes - reads should happen as low (late) as possible.

```kotlin
// BAD: scrolling recomposes the whole screen - offset read in composition
val offset = listState.firstVisibleItemScrollOffset
Header(Modifier.offset(y = offset.dp))

// GOOD: lambda-based modifier defers the read to the layout phase - zero recomposition
Header(Modifier.offset { IntOffset(0, listState.firstVisibleItemScrollOffset) })

// Same idea for draw-phase values:
Box(Modifier.drawBehind { drawRect(colorState.value) })   // read in draw, not composition
Box(Modifier.graphicsLayer { alpha = animatedAlpha.value })
```

## derivedStateOf

Use when a **frequently changing** input produces a **rarely changing** output:

```kotlin
val showFab by remember {
    derivedStateOf { listState.firstVisibleItemIndex > 0 }   // flips rarely; scroll changes constantly
}
```

- Wrong tool for combining ordinary inputs: `val fullName = remember(first, last) { "$first $last" }` - `derivedStateOf` there adds cost for nothing.
- If the calculation reads parameters that aren't `State`, key the remember: `remember(threshold) { derivedStateOf { listState.firstVisibleItemIndex > threshold } }` - otherwise the stale `threshold` is captured forever.

## Lazy list performance

```kotlin
LazyColumn(state = listState) {
    items(orders, key = { it.id }, contentType = { it.type }) { order ->
        OrderRow(order, Modifier.animateItem())   // animateItem needs keys
    }
}
```

- `key`: stable, unique per item, from data (never index). Without it, inserting at position 0 recomposes every row and resets their `remember`ed state.
- `contentType`: lets heterogeneous lists reuse compositions per type (feed with headers/cards/ads).
- Never nest a lazy container in a scrollable of the same direction; combine sections with multiple `item {}` / `items()` blocks in one `LazyColumn`.
- Heavy per-item computation belongs in the ViewModel at emission time, not in item composables.

## mutableStateOf granularity

```kotlin
// Prefer many small states over one big observable object
var name by remember { mutableStateOf("") }
var age by remember { mutableIntStateOf(0) }      // primitive variants avoid autoboxing:
var progress by remember { mutableFloatStateOf(0f) } // mutableIntStateOf/LongState/FloatState/DoubleState

// Lists that the UI mutates in place:
val selected = remember { mutableStateListOf<String>() }   // fine-grained change tracking
// NOT: mutableStateOf(mutableListOf()) - mutation is invisible to Compose
```

## Diagnosing recomposition

1. **Layout Inspector** (Android Studio) - live recomposition + skip counts per composable. First stop for "why is this janky".
2. **Compiler reports** - `./gradlew :app:compileReleaseKotlin -PcomposeCompilerReports=true` with:

```kotlin
composeCompiler {
    reportsDestination = layout.buildDirectory.dir("compose_reports")
    metricsDestination = layout.buildDirectory.dir("compose_metrics")
}
```

   `*-classes.txt` marks each class stable/unstable/runtime; `*-composables.txt` marks each function skippable/restartable and flags unstable params. Always inspect the **release** variant - debug stability differs.
3. **Recomposition highlighting is a debug-build signal only** - always confirm perf conclusions on a release (R8, baseline-profile) build via Macrobenchmark.

## Baseline profiles

JIT-free startup and first-scroll: generate with the `androidx.baselineprofile` Gradle plugin + a Macrobenchmark module.

```kotlin
@RunWith(AndroidJUnit4::class)
class BaselineProfileGenerator {
    @get:Rule val rule = BaselineProfileRule()
    @Test fun generate() = rule.collect("com.example.app") {
        pressHome(); startActivityAndWait()
        device.findObject(By.res("feed_list")).fling(Direction.DOWN)
    }
}
```

`./gradlew :app:generateBaselineProfile` writes `baseline-prof.txt` into `src/main/generated`; verify wins with a `startupProfile`/`frameTimeline` Macrobenchmark before/after. Libraries (Compose itself ships profiles) already cover framework paths - your profile earns its keep on app startup + hottest screens only.
