# Testing Compose Apps

Three layers, cheapest first: JVM unit tests for ViewModels/state (runTest + Turbine), JVM-hosted Compose UI tests (Robolectric), device/emulator instrumented tests (`connectedAndroidTest`). Same Compose test APIs work in the last two.

## Setup

```kotlin
// module build.gradle.kts
android { testOptions { unitTests { isIncludeAndroidResources = true } } }  // required for Robolectric UI tests
dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.+")
    testImplementation("app.cash.turbine:turbine:1.2.+")
    testImplementation("org.robolectric:robolectric:4.15.+")
    testImplementation(composeBom); testImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")   // hosts ComponentActivity for createComposeRule
}
```

## ViewModel unit tests: runTest + Turbine + main dispatcher rule

```kotlin
class MainDispatcherRule(val dispatcher: TestDispatcher = UnconfinedTestDispatcher()) : TestWatcher() {
    override fun starting(d: Description) = Dispatchers.setMain(dispatcher)
    override fun finished(d: Description) = Dispatchers.resetMain()
}

class OrdersViewModelTest {
    @get:Rule val mainDispatcherRule = MainDispatcherRule()

    @Test fun `filter change emits filtered orders`() = runTest {
        val vm = OrdersViewModel(FakeOrderRepository(orders), SavedStateHandle())
        vm.uiState.test {                                   // Turbine
            assertThat(awaitItem().isLoading).isTrue()      // stateIn initialValue
            assertThat(awaitItem().orders).hasSize(3)
            vm.setFilter(OrderFilter.SHIPPED)
            assertThat(awaitItem().orders).hasSize(1)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
```

- `viewModelScope` uses `Dispatchers.Main` - without the rule every test throws `Module with the Main dispatcher had failed to initialize`.
- `WhileSubscribed` StateFlows are cold until collected: asserting `vm.uiState.value` before any collector sees only `initialValue`. Turbine's `test {}` collector starts the pipeline correctly.
- Fake repositories over mocks: a `MutableStateFlow`-backed fake exercises the real operator chain.

## Compose UI tests: rules, semantics, testTag

```kotlin
class OrdersContentTest {
    @get:Rule val composeTestRule = createComposeRule()   // hosts content only; no real Activity needed

    @Test fun errorState_showsRetry_andRetryFires() {
        var retried = false
        composeTestRule.setContent {
            AppTheme { OrdersContent(OrdersUiState(error = "boom"), onOrderClick = {}, onRetry = { retried = true }) }
        }
        composeTestRule.onNodeWithText("boom").assertIsDisplayed()
        composeTestRule.onNodeWithTag("retry_button").performClick()
        assertThat(retried).isTrue()
    }
}
```

- `createComposeRule()` for testing composables in isolation; `createAndroidComposeRule<MainActivity>()` when the real Activity (Hilt graph, intents, edge-to-edge insets) matters.
- This exact test runs on device (`androidTest/`) or, annotated `@RunWith(RobolectricTestRunner::class)` + `@GraphicsMode(GraphicsMode.Mode.NATIVE)`, on the JVM (`test/`). Put fast feedback in `test/`, final confidence in `androidTest/`.
- Target the stateless `*Content` composable with hand-built `UiState`s - every branch (loading/error/empty/populated) becomes a trivial test, no ViewModel or DI involved.

### Finders and assertions cheat sheet

```kotlin
onNodeWithText("Checkout", substring = true, ignoreCase = true)
onNodeWithContentDescription("Add to cart")
onNodeWithTag("order_list")                    // Modifier.testTag("order_list")
onAllNodesWithTag("order_row").assertCountEquals(3)
onNodeWithTag("order_list").onChildren().onFirst().assert(hasText("Order #1"))
onNode(hasTestTag("submit") and isEnabled()).performClick()
onNodeWithTag("email_field").performTextInput("a@b.co")
onNodeWithTag("order_list").performScrollToNode(hasText("Order #40"))
onRoot().printToLog("TREE")                    // debug: dump the semantics tree
```

- Prefer user-visible semantics (text, content description) - they double as accessibility checks. Use `testTag` for containers and text-less nodes; tags are stripped-invisible to users and stable across copy changes.
- Nodes inside another node's semantics (merged): use `useUnmergedTree = true` when a child of a clickable row isn't found: `onNodeWithTag("price", useUnmergedTree = true)`.

### Synchronization

Compose tests auto-sync: assertions wait for recomposition and pending frames. They do NOT know about your coroutines/Flows on real dispatchers. For async UI driven by ViewModels in instrumented tests:

```kotlin
composeTestRule.waitUntil(timeoutMillis = 5_000) {
    composeTestRule.onAllNodesWithTag("order_row").fetchSemanticsNodes().isNotEmpty()
}
// Or, with test APIs >= 1.7: waitUntilExactlyOneExists(hasTestTag("order_row"))
```

Never `Thread.sleep`. Infinite animations stall the idle check - gate them on `LocalInspectionMode` or disable animations on the test device. For time control in pure-composable tests, `composeTestRule.mainClock.autoAdvance = false` + `mainClock.advanceTimeBy(...)`.

## Hilt instrumented tests

```kotlin
@HiltAndroidTest
class CheckoutFlowTest {
    @get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
    @get:Rule(order = 1) val composeTestRule = createAndroidComposeRule<MainActivity>()

    @BindValue @JvmField val repo: OrderRepository = FakeOrderRepository()

    @Test fun placeOrder_showsConfirmation() {
        composeTestRule.onNodeWithTag("place_order").performClick()
        composeTestRule.waitUntil { composeTestRule.onAllNodesWithText("Order placed")
            .fetchSemanticsNodes().isNotEmpty() }
    }
}
```

Needs a `CustomTestRunner : AndroidJUnitRunner` that swaps in `HiltTestApplication`, registered as `testInstrumentationRunner`. `@BindValue`/`@UninstallModules` replace production bindings per test.

## Navigation tests

```kotlin
composeTestRule.setContent {
    val navController = rememberNavController()
    navControllerRef = navController
    AppNavHost(navController)
}
composeTestRule.onNodeWithTag("order_row_1").performClick()
composeTestRule.runOnIdle {
    assertThat(navControllerRef.currentBackStackEntry?.destination?.hasRoute<OrderDetailRoute>()).isTrue()
}
```

Assert on `hasRoute<T>()`, not route strings. For unit-style graph tests use `TestNavHostController` with `setGraph`.

## Running and iterating

```bash
./gradlew test                                  # all JVM tests (unit + Robolectric UI)
./gradlew testDebugUnitTest --tests "*.OrdersViewModelTest"
./gradlew connectedAndroidTest                  # instrumented, needs device/emulator
./gradlew :app:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.example.CheckoutFlowTest
```

Fix all failures and re-run until clean; a flaky Compose test is almost always a missing synchronization point (waitUntil), a merged-semantics finder miss, or an infinite animation - not a candidate for `@Ignore`.
