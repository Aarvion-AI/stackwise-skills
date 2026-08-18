# Architecture: ViewModel, StateFlow, Hilt, Room

Lifecycle 2.9+, Hilt 2.5x (KSP, not kapt), Room 2.7+ (KSP), Kotlin 2.x coroutines.

## Screen state: one StateFlow, cold upstream, `stateIn`

```kotlin
@HiltViewModel
class OrdersViewModel @Inject constructor(
    private val repo: OrderRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val filter = MutableStateFlow(OrderFilter.ALL)

    val uiState: StateFlow<OrdersUiState> =
        filter.flatMapLatest { f -> repo.observeOrders(f) }
            .map { orders -> OrdersUiState(orders = orders.map { it.toUi() }.toImmutableList()) }
            .catch { emit(OrdersUiState(error = it.message)) }
            .stateIn(
                scope = viewModelScope,
                started = SharingStarted.WhileSubscribed(5_000),
                initialValue = OrdersUiState(isLoading = true),
            )

    fun setFilter(f: OrderFilter) { filter.value = f }

    fun retry() = viewModelScope.launch { repo.refresh() }   // survives rotation
}
```

Why each piece matters:

- `WhileSubscribed(5_000)` - upstream (Room observer, location, socket) stops 5s after the last collector leaves. 5s bridges configuration changes without restarting the pipeline; `Lazily`/`Eagerly` keep collecting forever in the background.
- `catch` on the pipeline, not per-collector - the StateFlow itself never fails.
- Mutable inputs (`filter`) are private `MutableStateFlow`s mutated by intent functions; the UI never gets a mutable handle.
- For imperative updates instead of a derived pipeline: `private val _uiState = MutableStateFlow(...)` + `val uiState = _uiState.asStateFlow()` and `_uiState.update { it.copy(...) }` (`update` is atomic; `_uiState.value = _uiState.value.copy(...)` races).

## Collecting in the UI - `collectAsStateWithLifecycle` only

```kotlin
// dependency: androidx.lifecycle:lifecycle-runtime-compose (in the BOM)
val state by viewModel.uiState.collectAsStateWithLifecycle()
```

- Collection pauses below `STARTED` (app backgrounded) and resumes on return - the pair with `WhileSubscribed` is what actually releases upstream resources.
- `collectAsState()` (plain, from compose-runtime) never pauses. Its only legitimate home is platform-agnostic/multiplatform code with no Android lifecycle. In an Android app, treat every `collectAsState()` in review as a bug.
- Collecting a non-state Flow for events inside composition: don't. See side-effects reference (one-shot events).

## One-shot events

Prefer modeling "events" as state the UI acknowledges:

```kotlin
data class CheckoutUiState(..., val orderPlaced: OrderConfirmation? = null)
fun consumeOrderPlaced() { _uiState.update { it.copy(orderPlaced = null) } }
// UI: LaunchedEffect(state.orderPlaced) { state.orderPlaced?.let { navigate; viewModel.consumeOrderPlaced() } }
```

State survives process death and cannot be dropped. A `Channel(BUFFERED)` + `receiveAsFlow()` collected in a `repeatOnLifecycle(STARTED)` block is acceptable for fire-and-forget UI effects (snackbar), but never for navigation or anything correctness-critical - events emitted while stopped race with re-subscription.

## Coroutine scoping: viewModelScope vs rememberCoroutineScope

| Work | Scope |
|---|---|
| Save/submit/refresh, anything touching repository | `viewModelScope` (survives recomposition and rotation) |
| Snackbar show, scroll/animate calls, drawer open | `rememberCoroutineScope` (dies with composition - correct for UI) |
| Composition-lifecycle work keyed on inputs | `LaunchedEffect` |

Never launch repository work from `rememberCoroutineScope` (cancelled mid-flight on rotation) and never hold a `rememberCoroutineScope` inside a ViewModel.

## Hilt setup (KSP)

```kotlin
// root build.gradle.kts
plugins { id("com.google.dagger.hilt.android") version "2.56" apply false
          id("com.google.devtools.ksp") version "2.1.20-2.0.1" apply false }
// app module
plugins { id("com.google.dagger.hilt.android"); id("com.google.devtools.ksp") }
dependencies { implementation("com.google.dagger:hilt-android:2.56")
               ksp("com.google.dagger:hilt-compiler:2.56")
               implementation("androidx.hilt:hilt-navigation-compose:1.2.0") }
```

```kotlin
@HiltAndroidApp class App : Application()

@AndroidEntryPoint class MainActivity : ComponentActivity() { /* setContent { ... } */ }

@Module @InstallIn(SingletonComponent::class)
abstract class DataModule {
    @Binds abstract fun orderRepo(impl: DefaultOrderRepository): OrderRepository
}

@Module @InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides @Singleton
    fun db(@ApplicationContext ctx: Context): AppDatabase =
        Room.databaseBuilder(ctx, AppDatabase::class.java, "app.db").build()
    @Provides fun orderDao(db: AppDatabase): OrderDao = db.orderDao()
}
```

In composables, `hiltViewModel()` (from `hilt-navigation-compose`) scopes the ViewModel to the current `NavBackStackEntry` - a fresh ViewModel per destination instance, cleared when the destination is popped. `viewModel()` without Hilt won't inject constructor dependencies. To share one ViewModel across a nested nav graph:

```kotlin
val parentEntry = remember(backStackEntry) { navController.getBackStackEntry<CheckoutGraph>() }
val shared: CheckoutViewModel = hiltViewModel(parentEntry)
```

## Room + Flow

```kotlin
@Entity data class OrderEntity(@PrimaryKey val id: String, val status: String, val updatedAt: Long)

@Dao interface OrderDao {
    @Query("SELECT * FROM OrderEntity WHERE status = :status ORDER BY updatedAt DESC")
    fun observeByStatus(status: String): Flow<List<OrderEntity>>   // cold, re-emits on table change

    @Upsert suspend fun upsertAll(orders: List<OrderEntity>)       // @Upsert > insert-with-REPLACE
    @Query("DELETE FROM OrderEntity") suspend fun clear()
}

@Database(entities = [OrderEntity::class], version = 1)
abstract class AppDatabase : RoomDatabase() { abstract fun orderDao(): AppDatabase.OrderDao }
```

- DAO `Flow` queries are main-safe (Room runs them on its own dispatcher) - no `flowOn` needed.
- A table `Flow` re-emits on **any** write to the table, even if the result set is identical - add `.distinctUntilChanged()` in the repository.
- Suspend DAO functions are also main-safe; never wrap them in `withContext(Dispatchers.IO)` reflexively.
- Repository pattern: Room as single source of truth, network refresh writes into Room, UI observes Room only.

```kotlin
class DefaultOrderRepository @Inject constructor(
    private val dao: OrderDao, private val api: OrderApi,
) : OrderRepository {
    override fun observeOrders(f: OrderFilter): Flow<List<Order>> =
        dao.observeByStatus(f.status).map { it.map(OrderEntity::toDomain) }.distinctUntilChanged()
    override suspend fun refresh() = dao.upsertAll(api.fetchOrders().map(OrderDto::toEntity))
}
```

## SavedStateHandle

- Nav arguments: `savedStateHandle.toRoute<OrderDetailRoute>()` (type-safe, see navigation reference).
- Process-death-surviving UI input: `savedStateHandle.getStateFlow("query", "")` + `savedStateHandle["query"] = value`. Keep it for small user input (query text, selection), not loaded data.

## Layering rules

- ViewModel exposes UI models (`ImmutableList<OrderUi>`), never Room entities or DTOs - this is also where stability is won (see state-recomposition reference).
- ViewModel has zero `android.*` imports beyond `androidx.lifecycle` - no Context (inject `@ApplicationContext` into repositories instead), no resources (expose resource IDs or use a string-provider abstraction).
- Composables never call repositories or DAOs directly.
