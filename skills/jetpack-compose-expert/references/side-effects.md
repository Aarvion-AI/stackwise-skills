# Side Effects

Effects run work that escapes the composition (coroutines, listeners, external systems) tied to a composable's lifecycle. Choosing the wrong API or the wrong keys is the top source of subtle Compose bugs.

## Decision table

| Need | API |
|---|---|
| Run suspend work when the composable enters composition / when inputs change | `LaunchedEffect(keys...)` |
| Use the latest lambda/value inside a long-lived effect without restarting it | `rememberUpdatedState` |
| Register something that needs cleanup (listener, broadcast receiver, sensor) | `DisposableEffect(keys...)` |
| Publish composed state to non-Compose code after every successful recomposition | `SideEffect` |
| Turn Compose `State` reads into a `Flow` | `snapshotFlow` |
| Turn async/subscription sources into `State` inside composition | `produceState` |
| Launch from a user event (click) with composition lifetime | `rememberCoroutineScope().launch` |

## LaunchedEffect: keys are cancel-and-restart triggers

```kotlin
// Restart the load when the id changes; cancel the old load automatically
LaunchedEffect(userId) { viewModel.load(userId) }

// Run exactly once per composition lifetime
LaunchedEffect(Unit) { analytics.screenView("orders") }
```

Key rules:

- A key change **cancels** the running block and starts a new one. Key on exactly the inputs whose change invalidates the running work.
- `LaunchedEffect(Unit)` + captured params = stale captures. If the effect must not restart but must see fresh values, combine with `rememberUpdatedState` (below).
- Keying on an unstable object recreated each recomposition restarts the effect every frame - the "my effect loops forever" bug. Key on the underlying stable value (`user.id`, not `user`-from-a-fresh-list).
- The block is a coroutine on the composition's context (main). Heavy work: call suspend repository functions that are themselves main-safe; don't `withContext(Dispatchers.IO)` around UI-state writes.

## rememberUpdatedState: fresh values in long-lived effects

```kotlin
@Composable
fun AutoDismissBanner(onDismiss: () -> Unit) {
    val currentOnDismiss by rememberUpdatedState(onDismiss)
    LaunchedEffect(Unit) {            // timer must NOT restart when the parent recomposes
        delay(5_000)
        currentOnDismiss()            // latest lambda, even if parent recomposed 100 times
    }
}
```

Use whenever an effect legitimately outlives the values it uses: timers, animations, callbacks in `DisposableEffect` observers. It's a `State` holder updated on every recomposition - reading it never restarts the effect.

## DisposableEffect: paired setup/teardown

```kotlin
@Composable
fun LifecycleObserver(onResume: () -> Unit) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val currentOnResume by rememberUpdatedState(onResume)
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) currentOnResume()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }   // mandatory, compile-enforced
    }
}
```

- `onDispose` runs when a key changes (before re-setup) and when the composable leaves composition. Everything registered must be unregistered there.
- Same key discipline as `LaunchedEffect`.
- Classic uses: lifecycle observers, `BroadcastReceiver`, sensor/location listeners, ExoPlayer attach/release, `OnBackPressedCallback` (though prefer the `BackHandler` composable).

## SideEffect: publish to non-Compose world

```kotlin
SideEffect { firebaseCrashlytics.setCustomKey("screen", state.screenName) }
```

Runs after every successful recomposition of its scope, on the main thread, in order. No keys, no cleanup - for anything conditional or needing teardown use the other APIs. Rare; if reaching for it to mutate Compose state, the design is wrong.

## snapshotFlow: State -> Flow

```kotlin
val listState = rememberLazyListState()
LaunchedEffect(listState) {
    snapshotFlow { listState.firstVisibleItemIndex }
        .map { it > 0 }
        .distinctUntilChanged()
        .collect { pastTop -> viewModel.onScrolledPastTop(pastTop) }
}
```

The block re-runs when any `State` read inside it changes; emissions are conflated and deduplicated (`distinctUntilChanged` semantics on the block result, still add explicit operators after `map`). This is the bridge for feeding scroll/gesture state into analytics, ViewModels, or debounced work - the inverse of `collectAsStateWithLifecycle`.

## produceState: async source -> State

```kotlin
@Composable
fun rememberNetworkStatus(monitor: ConnectivityMonitor): State<Boolean> =
    produceState(initialValue = true, monitor) {
        monitor.online.collect { value = it }
        // awaitDispose { } is available for callback-based sources
    }
```

Use for wrapping subscriptions into reusable `remember*` helpers. For ViewModel flows, `collectAsStateWithLifecycle` already does this correctly - don't reinvent it.

## One-shot events from ViewModel, correctly

Preferred: events as state, acknowledged by the UI (see architecture reference). When a transient-effect channel is unavoidable (snackbars):

```kotlin
// ViewModel
private val _messages = Channel<String>(Channel.BUFFERED)
val messages = _messages.receiveAsFlow()

// UI - collection tied to STARTED so backgrounded emissions buffer instead of dropping
val snackbarHostState = remember { SnackbarHostState() }
LaunchedEffect(Unit) {
    lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
        messages.collect { snackbarHostState.showSnackbar(it) }
    }
}
```

Never drive navigation from a `SharedFlow(replay = 0)` - an emission while the collector is stopped is lost forever. Navigation triggers belong in state.

## Anti-patterns checklist

- **Side effects directly in composition** - `viewModel.load()` called in a composable body runs on every recomposition. All escapes go through an effect API.
- **`LaunchedEffect` to initialize ViewModel data** - `LaunchedEffect(Unit) { viewModel.load() }` reloads on every return to the screen (new composition). Load in the ViewModel's `init`/cold-flow pipeline instead; the ViewModel outlives compositions.
- **Restart-by-accident**: lambda keys. `LaunchedEffect(onClick)` restarts whenever the parent passes a new lambda instance. Effects should key on data, and read lambdas via `rememberUpdatedState`.
- **Cleanup in `LaunchedEffect` via `try/finally`** for listeners - cancellation isn't guaranteed to run before re-setup ordering matters; `DisposableEffect` exists for exactly this.
- **`GlobalScope` / custom `CoroutineScope()` in composables** - leaks work past the screen. Every coroutine belongs to `viewModelScope`, `rememberCoroutineScope`, or an effect.
- **`delay()` polling loops** to watch state - use `snapshotFlow` on the state instead.
