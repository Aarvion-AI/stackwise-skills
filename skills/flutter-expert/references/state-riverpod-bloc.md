# State Management: Riverpod 2/3 and Bloc

Covers Riverpod 2.6+ / 3.x with code generation and bloc 9.x. Match whatever the
project already uses; only recommend a switch if asked.

## Choosing

| Situation | Pick |
|---|---|
| New app, general purpose, async-heavy data layer | Riverpod (code-gen) |
| Team wants strict event->state traceability, event transformers (debounce/throttle), or already standardized on it | Bloc |
| One widget's ephemeral UI state (text field focus, animation, tab index) | `StatefulWidget` / `setState` - no library |
| Legacy `provider` package app | Keep for small fixes; migrate feature-by-feature to Riverpod for larger work |

Do not use: `StateProvider`/`StateNotifierProvider`/`ChangeNotifierProvider` in new
code (Riverpod legacy, removed from Riverpod 3 core - 3.x keeps them only in
`package:flutter_riverpod/legacy.dart`), GetX, or raw `InheritedWidget` for app state.

## Riverpod with code generation (the default)

Setup in `pubspec.yaml`:

```yaml
dependencies:
  flutter_riverpod: ^3.0.0   # or ^2.6.x - API below works on both
  riverpod_annotation: ^3.0.0
dev_dependencies:
  riverpod_generator: ^3.0.0
  build_runner: ^2.4.0
  custom_lint: ^0.7.0
  riverpod_lint: ^3.0.0      # catches watch-in-callback etc.
```

Every provider file needs the `part` directive; regenerate after edits:

```dart
// lib/features/todos/todos_provider.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';
part 'todos_provider.g.dart';
```

```bash
dart run build_runner build --delete-conflicting-outputs
# or during development:
dart run build_runner watch --delete-conflicting-outputs
```

### Provider kinds - pick by shape of the state

```dart
// 1. Derived/read-only value (sync). Rebuilds when deps change.
@riverpod
String greeting(Ref ref) => 'Hello ${ref.watch(userProvider).name}';
// Riverpod 2 generator emits a typed ref (GreetingRef); 3.x uses plain `Ref`.

// 2. Async read-only data (fetch once, cache):
@riverpod
Future<List<Todo>> todos(Ref ref) async {
  final dio = ref.watch(dioProvider);
  final res = await dio.get('/todos');
  return (res.data as List).map(Todo.fromJson).toList();
}

// 3. Mutable sync state:
@riverpod
class Counter extends _$Counter {
  @override
  int build() => 0;
  void increment() => state = state + 1;
}

// 4. Mutable async state - the workhorse:
@riverpod
class TodoList extends _$TodoList {
  @override
  Future<List<Todo>> build() => ref.watch(todoRepoProvider).fetchAll();

  Future<void> add(String title) async {
    // Optimistic-safe pattern: guard captures errors into AsyncError.
    state = const AsyncLoading<List<Todo>>().copyWithPrevious(state);
    state = await AsyncValue.guard(() async {
      await ref.read(todoRepoProvider).create(title);
      return ref.read(todoRepoProvider).fetchAll();
    });
  }
}
```

Key rules:

- Providers are `autoDispose` **by default** with code-gen. To keep state alive:
  `@Riverpod(keepAlive: true)`, or inside `build`: `ref.keepAlive();`.
- Parameters ("family") are just method parameters: `Future<Todo> build(String id)`.
  Each distinct argument set gets its own provider instance; args must have `==`.
- `ref.watch` in `build` only. `ref.read` in callbacks. `ref.listen` for side
  effects (snackbar, navigation) - never navigate from inside `build`.
- Riverpod 3: `Notifier`/`AsyncNotifier` are the stable base classes, `Ref` lost its
  type parameter, providers auto-retry failed `build`s with backoff (disable via
  `retry: null` on the provider or container), and errors rethrown by providers are
  wrapped in `ProviderException` in 3.0+.

### Consuming

```dart
class TodoScreen extends ConsumerWidget {
  const TodoScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Side effect on failure - listen, don't watch:
    ref.listen(todoListProvider, (prev, next) {
      if (next is AsyncError) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('${next.error}')));
      }
    });

    return switch (ref.watch(todoListProvider)) {
      AsyncData(:final value) => TodoListView(todos: value),
      AsyncError(:final error) => RetryView(
          error: error,
          onRetry: () => ref.invalidate(todoListProvider)),
      _ => const Center(child: CircularProgressIndicator()),
    };
  }
}
```

- `ref.watch(p.select((s) => s.field))` to rebuild on one field only.
- `ref.invalidate(p)` / `ref.refresh(p)` to force refetch (refresh returns the new value).
- Testing/DI override: `ProviderScope(overrides: [todoRepoProvider.overrideWithValue(fake)])`.

## Bloc 9.x

```yaml
dependencies:
  flutter_bloc: ^9.0.0
  bloc_concurrency: ^0.3.0
```

Prefer `Cubit` unless you need event objects (traceability, transformers, replay):

```dart
class CounterCubit extends Cubit<int> {
  CounterCubit() : super(0);
  void increment() => emit(state + 1);
}
```

Full Bloc with Dart 3 sealed events/states and an event transformer:

```dart
sealed class SearchEvent {}
final class SearchQueryChanged extends SearchEvent {
  SearchQueryChanged(this.query);
  final String query;
}

sealed class SearchState {}
final class SearchInitial extends SearchState {}
final class SearchLoading extends SearchState {}
final class SearchLoaded extends SearchState {
  SearchLoaded(this.results);
  final List<Result> results;
}
final class SearchError extends SearchState {
  SearchError(this.message);
  final String message;
}

class SearchBloc extends Bloc<SearchEvent, SearchState> {
  SearchBloc(this._repo) : super(SearchInitial()) {
    on<SearchQueryChanged>(
      _onQueryChanged,
      transformer: restartable(), // bloc_concurrency: cancel stale searches
    );
  }
  final SearchRepo _repo;

  Future<void> _onQueryChanged(
      SearchQueryChanged event, Emitter<SearchState> emit) async {
    emit(SearchLoading());
    try {
      emit(SearchLoaded(await _repo.search(event.query)));
    } catch (e) {
      emit(SearchError(e.toString()));
    }
  }
}
```

Consuming - use the narrowest widget:

```dart
BlocProvider(create: (_) => SearchBloc(repo), child: ...)
// Rebuild UI:
BlocBuilder<SearchBloc, SearchState>(
  buildWhen: (prev, next) => prev.runtimeType != next.runtimeType,
  builder: (context, state) => switch (state) {
    SearchInitial() => const SearchHint(),
    SearchLoading() => const CircularProgressIndicator(),
    SearchLoaded(:final results) => ResultsList(results),
    SearchError(:final message) => ErrorView(message),
  },
)
// Side effects only:
BlocListener<SearchBloc, SearchState>(listener: ..., child: ...)
// Read in a callback:
context.read<SearchBloc>().add(SearchQueryChanged(q));
```

## Bloc rules Claude gets wrong

- Never `emit` after an `await` without the handler still running - use the
  `Emitter`, never store it; check `emit.isDone` in long-running streams, or use
  `emit.forEach(stream, onData: ...)`.
- `context.watch<T>()` in `build` rebuilds on **every** state change; prefer
  `BlocBuilder` with `buildWhen` or `context.select((SearchBloc b) => ...)`.
- States must be new instances (or use `Equatable`/`freezed`); mutating and
  re-emitting the same object is a no-op because `==` doesn't change.
- Don't create blocs inside `build` without `BlocProvider` - you'll leak and
  recreate them on every rebuild.

## Modeling state: freezed 3 + json_serializable

Immutable state classes with value equality are what make both libraries work.

```yaml
dependencies:
  freezed_annotation: ^3.0.0
  json_annotation: ^4.9.0
dev_dependencies:
  freezed: ^3.0.0
  json_serializable: ^6.9.0
```

```dart
import 'package:freezed_annotation/freezed_annotation.dart';
part 'user.freezed.dart';
part 'user.g.dart';

@freezed
abstract class User with _$User {          // freezed 3: MUST be abstract/sealed
  const factory User({
    required String id,
    required String name,
    @Default(false) bool isAdmin,
    @JsonKey(name: 'avatar_url') String? avatarUrl,
  }) = _User;

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
}

// Union type - declare `sealed` and match with plain Dart switch:
@freezed
sealed class SyncStatus with _$SyncStatus {
  const factory SyncStatus.idle() = SyncIdle;
  const factory SyncStatus.syncing(double progress) = Syncing;
  const factory SyncStatus.failed(Object error) = SyncFailed;
}

final label = switch (status) {
  SyncIdle() => 'Up to date',
  Syncing(:final progress) => '${(progress * 100).round()}%',
  SyncFailed(:final error) => 'Failed: $error',
};
```

freezed 3 breaking changes LLMs miss: classes must be declared `abstract` (single
constructor) or `sealed` (union); the generated `.when`/`.map`/`.maybeWhen`
methods are **gone** - use Dart `switch` patterns as above. Update state with
`user.copyWith(name: 'New')`; nested updates via `user.copyWith.address(city: 'X')`.
Regenerate with `dart run build_runner build --delete-conflicting-outputs`.

