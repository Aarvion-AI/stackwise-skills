---
name: jetpack-compose-expert
description: Use when working in a native Android Jetpack Compose project - build.gradle.kts with androidx.compose BOM or org.jetbrains.kotlin.plugin.compose, *.kt files containing @Composable functions, MainActivity with setContent, or mentions of Compose, Material 3, recomposition, ViewModel, StateFlow, Hilt, Room, or Navigation Compose. Builds screens, state management, navigation, DI, and tests for Kotlin 2.x / Compose BOM 2026 apps. Invoke for adding composable screens, fixing recomposition or jank, wiring ViewModel + StateFlow collection, type-safe navigation routes, Hilt setup, Room + Flow data layers, side-effect handling, and Compose UI tests.
license: MIT
metadata:
  version: "0.1.0"
  category: mobile
  frameworks: "Jetpack Compose (BOM 2026.x), Kotlin 2.x (K2 compiler), Material 3, Navigation Compose 2.9+, Lifecycle 2.9+, Hilt 2.5x, Room 2.7+"
  triggers: jetpack compose, composable, recomposition, material 3, compose-bom, remember, mutableStateOf, state hoisting, StateFlow, collectAsStateWithLifecycle, viewModelScope, LaunchedEffect, DisposableEffect, rememberUpdatedState, navigation compose, type-safe routes, hilt, hiltViewModel, room, LazyColumn, derivedStateOf, strong skipping, baseline profile, composeTestRule, testTag, edge-to-edge
  related: flutter-expert, react-native-expert, mobile-qa-expert
---

# Jetpack Compose Expert

Turns Claude into a senior Android engineer shipping idiomatic Kotlin 2.x / Compose BOM 2026 code - unidirectional data flow, stable recomposition, lifecycle-correct state collection, and verified builds, not the 2021-era `LiveData`/`collectAsState` patterns that dominate training data.

## When to Use This Skill

- Building screens or components with Compose + Material 3 in an existing Android app
- Fixing recomposition storms, unstable parameters, or laggy lazy lists
- Wiring ViewModel + `StateFlow` state exposed to composables the lifecycle-correct way
- Adding Navigation Compose routes (type-safe, `@Serializable` route classes)
- Setting up or extending Hilt DI and Room + Flow data layers
- Handling side effects: `LaunchedEffect`, `DisposableEffect`, `rememberUpdatedState`, `snapshotFlow`
- Writing Compose UI tests (`composeTestRule`, semantics) and Robolectric-hosted tests
- Edge-to-edge/insets work and performance passes (baseline profiles, `derivedStateOf`)

## Core Workflow

1. **Analyze** - Read `gradle/libs.versions.toml` and module `build.gradle.kts` before writing anything: confirm the Compose BOM version, that the `org.jetbrains.kotlin.plugin.compose` Gradle plugin is applied (required with Kotlin 2.x - `composeOptions.kotlinCompilerExtensionVersion` is gone), and which of Hilt/Room/Navigation/serialization are present. Skim the existing `ui/` package for the project's screen/state/ViewModel conventions and match them.
2. **Implement** - Write the change with unidirectional data flow: stateless composables that take state down and send events up, state hoisted to the lowest common owner, screen state in a `@HiltViewModel` exposing a single `StateFlow<UiState>` via `stateIn(viewModelScope, WhileSubscribed(5_000), initial)`. Collect in UI only with `collectAsStateWithLifecycle()`. Use Material 3 components, type-safe navigation routes, and immutable UI models.
3. **Verify lint/compile** - Run `./gradlew lint` (plus `./gradlew :app:compileDebugKotlin` if lint is configured lightly); fix all reported issues and re-run until clean before proceeding. Treat Compose lint checks (`ComposableNaming`, `RememberReturnType`, `FrequentlyChangingValue`, coroutine-in-composition errors) as real defects, not noise.
4. **Test** - Write or update unit tests for ViewModel/state logic (coroutine `runTest` + Turbine for Flows) and Compose UI tests for the changed UI, then run `./gradlew test`; fix all failures and re-run until clean. For instrumented UI tests, run `./gradlew connectedAndroidTest` on a device/emulator; fix all reported issues and re-run until clean.
5. **Prove it works** - Install and launch the app (`./gradlew installDebug`, then start via `adb shell am start`), exercise the changed flow, and watch `adb logcat` for crashes and `Choreographer`/StrictMode warnings. For performance work, confirm with Layout Inspector recomposition counts or a Macrobenchmark that recompositions/frame times actually dropped.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| State hoisting, stability, strong skipping, `@Stable`/`@Immutable`, immutable collections, `derivedStateOf`, lazy list performance | `references/state-recomposition.md` | Any recomposition/performance question, unstable-parameter warnings, jank in lists, or designing where state lives |
| ViewModel + StateFlow, `stateIn`, `collectAsStateWithLifecycle`, Hilt setup, Room + Flow, coroutine scoping | `references/architecture-viewmodel.md` | Creating/refactoring a screen's state layer, wiring DI, adding a Room-backed feature, or viewModelScope vs rememberCoroutineScope decisions |
| Navigation Compose: `@Serializable` routes, `toRoute()`, nested graphs, bottom bar back-stack behavior, deep links | `references/navigation.md` | Adding or restructuring routes, passing arguments, tab navigation state loss, or deep-link work |
| Side effects: `LaunchedEffect` keys, `rememberUpdatedState`, `DisposableEffect`, `snapshotFlow`, one-shot events | `references/side-effects.md` | Any effect API usage, "effect restarts too often / never restarts" bugs, or bridging snapshot state to Flows |
| Testing: `composeTestRule`, semantics/testTag, synchronization, Robolectric Compose tests, Turbine ViewModel tests | `references/testing.md` | Writing or fixing any Compose or ViewModel test, flaky waits, or choosing JVM vs device-hosted tests |

## Key Patterns

**Screen wiring - lifecycle-aware collection, stateless content composable:**

```kotlin
@Composable
fun OrdersScreen(
    onOrderClick: (String) -> Unit,
    viewModel: OrdersViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle() // NOT collectAsState()
    OrdersContent(state = state, onOrderClick = onOrderClick, onRetry = viewModel::retry)
}

@Composable
private fun OrdersContent(          // stateless: previewable and testable
    state: OrdersUiState,
    onOrderClick: (String) -> Unit,
    onRetry: () -> Unit,
) { /* Material 3 UI driven only by `state` */ }
```

**Type-safe navigation (Navigation 2.8+, kotlinx.serialization - no string routes):**

```kotlin
@Serializable data object OrdersRoute
@Serializable data class OrderDetailRoute(val orderId: String)

NavHost(navController, startDestination = OrdersRoute) {
    composable<OrdersRoute> {
        OrdersScreen(onOrderClick = { id -> navController.navigate(OrderDetailRoute(id)) })
    }
    composable<OrderDetailRoute> { backStackEntry ->
        val route = backStackEntry.toRoute<OrderDetailRoute>()
        OrderDetailScreen(orderId = route.orderId)
    }
}
```

**Stable UI state - immutable models so skipping works:**

```kotlin
@Immutable
data class OrdersUiState(
    val orders: ImmutableList<OrderUi> = persistentListOf(), // kotlinx.collections.immutable
    val isLoading: Boolean = false,
    val error: String? = null,
)
```

**Effect keyed correctly, latest callback without restart:**

```kotlin
@Composable
fun SessionTimeout(onTimeout: () -> Unit) {
    val currentOnTimeout by rememberUpdatedState(onTimeout)
    LaunchedEffect(Unit) {           // effect must run once for the composable's lifetime
        delay(SESSION_MS)
        currentOnTimeout()           // always calls the latest lambda
    }
}
```

## Common Mistakes

- **`collectAsState()` instead of `collectAsStateWithLifecycle()`** - `collectAsState()` keeps collecting while the app is backgrounded, wasting work and keeping upstream flows (location, DB observers) alive. Always use `collectAsStateWithLifecycle()` from `lifecycle-runtime-compose`; pair it with `stateIn(..., WhileSubscribed(5_000), ...)` in the ViewModel so upstream stops too.
- **Assuming pre-strong-skipping rules.** With Kotlin 2.0.20+ the Compose compiler enables strong skipping by default: composables with unstable params still skip on `equals`-same values, and lambdas are auto-remembered. Do not blanket-wrap every lambda in `remember`; do still fix genuinely churning values - a `List` rebuilt every emission fails `equals` and defeats skipping. Prefer `ImmutableList`/`@Immutable` UI models over sprinkling `@Stable` on mutable classes.
- **Wrong `LaunchedEffect` keys.** `LaunchedEffect(Unit)` with a captured callback runs stale code (use `rememberUpdatedState`); keying on an object that changes identity every recomposition restarts the effect every frame. Key on the values whose change should cancel-and-restart the work - nothing more, nothing less.
- **`rememberCoroutineScope` for business logic.** That scope dies when the composable leaves composition - a save/upload launched there is cancelled by rotation. Business work belongs in `viewModelScope`; `rememberCoroutineScope` is only for UI-lifetime calls like `snackbarHostState.showSnackbar()`, `LazyListState.animateScrollToItem()`, or drawer/sheet animations.
- **`LazyColumn` without `key` (or with index keys)** - inserts/removals recompose every following item and break `animateItem()` and scroll position. Provide a stable id: `items(orders, key = { it.id }) { ... }`. Also never put a `LazyColumn` with `fillMaxHeight` semantics inside a scrollable `Column` - use one lazy container with multiple `item`/`items` blocks.
- **String routes and manual argument parsing** - `navigate("detail/$id")` plus `NavType` boilerplate is the deprecated idiom. Use `@Serializable` route classes with `composable<Route>` and `toRoute()`; pass ids, not full objects, and reload data in the destination's ViewModel via `SavedStateHandle.toRoute()`.
- **Computing derived values without `derivedStateOf`** - e.g. `val showButton = listState.firstVisibleItemIndex > 0` directly in composition recomposes on every scroll frame. Wrap frequently-changing reads whose *result* changes rarely: `val showButton by remember { derivedStateOf { listState.firstVisibleItemIndex > 0 } }`. Conversely, don't use `derivedStateOf` for plain combinations of infrequently-changing state - that's just `remember(a, b)`.
- **Ignoring edge-to-edge.** Targeting SDK 35+ the app is edge-to-edge whether you opt in or not. Call `enableEdgeToEdge()` in the Activity, let Material 3 `Scaffold` pass `innerPadding` to content (and actually apply it), and use `WindowInsets.safeDrawing`/`imePadding()` for custom layouts - hardcoded status-bar heights and `systemUiVisibility` flags are dead APIs.
