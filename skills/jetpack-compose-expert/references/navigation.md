# Navigation Compose: Type-Safe Routes

Navigation Compose 2.8+ (type-safe API is the current idiom; string routes are legacy). Requires the `org.jetbrains.kotlin.plugin.serialization` Gradle plugin and `kotlinx-serialization-core`.

## Routes are @Serializable types

```kotlin
// Routes file - objects for argument-less screens, data classes for parameterized ones
@Serializable data object HomeRoute
@Serializable data object SettingsRoute
@Serializable data class ProductRoute(val productId: String, val fromDeepLink: Boolean = false)
@Serializable data class SearchRoute(val query: String? = null)   // optional args: defaults
```

```kotlin
val navController = rememberNavController()

NavHost(navController = navController, startDestination = HomeRoute) {
    composable<HomeRoute> {
        HomeScreen(onProductClick = { id -> navController.navigate(ProductRoute(id)) })
    }
    composable<ProductRoute> { entry ->
        val route = entry.toRoute<ProductRoute>()
        ProductScreen(productId = route.productId, onBack = navController::popBackStack)
    }
    composable<SearchRoute> { /* ... */ }
}
```

Rules:

- Pass **ids, not objects**. Destinations load their own data via ViewModel; args live in the saved state and must stay small and serializable. (Custom `NavType` for complex Parcelables exists but is a design smell.)
- Screens never receive the `NavController`. They take event lambdas (`onProductClick`, `onBack`); only the NavHost layer navigates. This keeps screens previewable/testable and navigation logic in one file.
- Reading args in the ViewModel - no manual key strings:

```kotlin
@HiltViewModel
class ProductViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle, repo: ProductRepository,
) : ViewModel() {
    private val route = savedStateHandle.toRoute<ProductRoute>()
    val product = repo.observe(route.productId)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)
}
```

## Nested graphs

```kotlin
@Serializable data object CheckoutGraph   // graph route
@Serializable data object CartRoute
@Serializable data object PaymentRoute

NavHost(navController, startDestination = HomeRoute) {
    composable<HomeRoute> { ... }
    navigation<CheckoutGraph>(startDestination = CartRoute) {
        composable<CartRoute> { entry ->
            // ViewModel shared across the whole checkout flow:
            val parent = remember(entry) { navController.getBackStackEntry<CheckoutGraph>() }
            val vm: CheckoutViewModel = hiltViewModel(parent)
            CartScreen(vm, onNext = { navController.navigate(PaymentRoute) })
        }
        composable<PaymentRoute> { entry ->
            val parent = remember(entry) { navController.getBackStackEntry<CheckoutGraph>() }
            PaymentScreen(hiltViewModel(parent))
        }
    }
}
```

Navigating to `CheckoutGraph` enters at `CartRoute`. The graph-scoped ViewModel is cleared when the whole graph pops - the correct pattern for multi-step flows sharing state.

## Bottom navigation that doesn't lose state

```kotlin
NavigationBar {
    topLevelRoutes.forEach { top ->
        val selected = currentDestination?.hierarchy?.any { it.hasRoute(top.route::class) } == true
        NavigationBarItem(
            selected = selected,
            onClick = {
                navController.navigate(top.route) {
                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }
            },
            icon = { Icon(top.icon, contentDescription = top.label) },
            label = { Text(top.label) },
        )
    }
}
val currentDestination = navController
    .currentBackStackEntryAsState().value?.destination
```

All three flags are required: `saveState`+`restoreState` preserve each tab's back stack and scroll position; `launchSingleTop` prevents stacking duplicates of the same tab. `hierarchy.any { it.hasRoute(...) }` (not equality on the current destination) keeps the tab highlighted while on nested screens within it.

## Back stack surgery

```kotlin
// Login -> Home, removing login from history
navController.navigate(HomeRoute) { popUpTo(LoginRoute) { inclusive = true } }

// Pop back to a known screen with a result-ish flag
navController.popBackStack<CartRoute>(inclusive = false)

// Guard against double-tap crashes ("navigate after onDestroy"):
// prefer launchSingleTop and lifecycle-aware click debouncing over checking currentBackStackEntry manually
```

Returning results to a previous screen: write to the previous entry's `SavedStateHandle`:

```kotlin
navController.previousBackStackEntry?.savedStateHandle?.set("picked_address_id", id)
navController.popBackStack()
// In the receiving screen (observe, then consume):
val picked = navController.currentBackStackEntry?.savedStateHandle
    ?.getStateFlow<String?>("picked_address_id", null)?.collectAsStateWithLifecycle()
```

For anything richer than a primitive, prefer a shared graph-scoped ViewModel instead.

## Deep links

```kotlin
composable<ProductRoute>(
    deepLinks = listOf(navDeepLink<ProductRoute>(basePath = "https://example.com/product")),
) { ... }
// Matches https://example.com/product/{productId}; query params map to optional fields.
```

`navDeepLink<Route>(basePath=...)` generates the URI pattern from the route's fields - do not hand-write `{placeholder}` patterns for typed routes. Add the matching `<intent-filter>` with `android:autoVerify="true"` and the `assetlinks.json` for App Links; test with `adb shell am start -a android.intent.action.VIEW -d "https://example.com/product/42"`.

## Animations

Per-NavHost defaults and per-destination overrides:

```kotlin
NavHost(
    navController, startDestination = HomeRoute,
    enterTransition = { slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.Start) },
    exitTransition = { fadeOut() },
    popEnterTransition = { fadeIn() },
    popExitTransition = { slideOutOfContainer(AnimatedContentTransitionScope.SlideDirection.End) },
) {
    composable<SettingsRoute>(enterTransition = { slideInVertically { it } }) { ... }
}
```

The `composable` content lambda is an `AnimatedContentScope` - use `Modifier.sharedElement`/`sharedBounds` with `SharedTransitionLayout` wrapping the NavHost for shared-element transitions between destinations.

## Migration and pitfalls

- Legacy string routes (`composable("product/{id}", arguments = listOf(navArgument...))`) still compile - migrate opportunistically; never mix styles for the same destination.
- Route classes must be `@Serializable` **and** their properties serializable primitives/strings/enums; a non-serializable field fails at runtime on first navigate, not at compile time.
- `data object` (not `object`) for argument-less routes so equality and `toString` behave.
- Don't navigate from composition (`if (state.loggedOut) navController.navigate(LoginRoute)` inline recomposes into a navigate-loop). Navigate from callbacks or a `LaunchedEffect(state.loggedOut)`.
- Navigation 3 (`androidx.navigation3`) is the newer alternative where the app owns the back stack as observable state; for established apps on Navigation Compose 2.x, the typed API above remains the supported, stable idiom - don't mix the two libraries in one graph.
