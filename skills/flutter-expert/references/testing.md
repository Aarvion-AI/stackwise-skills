# Testing: Widget, Golden, Integration, Patrol

Test pyramid for Flutter: many unit tests (pure Dart, blocs/notifiers/repos),
a solid layer of widget tests, few device-level integration tests for the
critical flows. All run with `flutter test`; integration tests need a device.

```yaml
dev_dependencies:
  flutter_test: {sdk: flutter}
  integration_test: {sdk: flutter}
  mocktail: ^1.0.0        # prefer over mockito: no codegen
  bloc_test: ^10.0.0      # if the app uses bloc
  patrol: ^3.0.0          # if native-interaction E2E is needed
```

## Widget tests

```dart
void main() {
  testWidgets('shows todos after load', (tester) async {
    final repo = _FakeTodoRepo([Todo(id: '1', title: 'Buy milk')]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [todoRepoProvider.overrideWithValue(repo)],
        child: const MaterialApp(home: TodoScreen()),
      ),
    );

    // Initial frame: loading state
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    // Let the async provider resolve + rebuild:
    await tester.pump();          // start the future
    await tester.pump();          // apply the AsyncData frame

    expect(find.text('Buy milk'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });
}
```

Non-negotiables:

- Always wrap in `MaterialApp` (or `MaterialApp.router`) - `Directionality`,
  `Theme`, `Navigator`, and localizations come from it; bare widgets throw.
- Inject fakes at the seam the app already has: `ProviderScope(overrides:)` for
  Riverpod, `BlocProvider.value(value: mockBloc)` for bloc, constructor params
  otherwise. Never spin up real HTTP/plugins in widget tests.
- `pump()` advances one frame / a given duration; `pumpAndSettle()` pumps until
  no frames are scheduled - it **times out with infinite animations** (shimmer,
  spinners, `AnimatedBuilder` loops). For those, pump explicit durations.
- Timers must be flushed before the test ends or it fails with "A Timer is still
  pending" - pump past debounce durations
  (`await tester.pump(const Duration(milliseconds: 500));`).
- Finders: `find.text`, `find.byType`, `find.byKey(const ValueKey('save'))`,
  `find.byIcon`, `find.bySemanticsLabel`. Add `Key`s to widgets you assert on
  rather than matching English copy that will change.
- Interactions: `tester.tap(finder)`, `tester.enterText(finder, 'x')`,
  `tester.drag(finder, const Offset(0, -300))` - each followed by `pump`.
- Scrolling to off-screen items:
  `await tester.scrollUntilVisible(find.text('Item 40'), 200);`
- Mocktail: `class MockRepo extends Mock implements TodoRepo {}` then
  `when(() => repo.fetchAll()).thenAnswer((_) async => [...]);` and
  `verify(() => repo.create('x')).called(1);`. Register fallback values for
  non-primitive `any()` matchers:
  `setUpAll(() => registerFallbackValue(FakeTodo()));`

## Unit-testing state

Riverpod - test the provider, not a widget:

```dart
test('add() appends and refetches', () async {
  final container = ProviderContainer(
    overrides: [todoRepoProvider.overrideWithValue(fakeRepo)],
  );
  addTearDown(container.dispose);

  await container.read(todoListProvider.future); // wait initial load
  await container.read(todoListProvider.notifier).add('New');

  expect(container.read(todoListProvider).value, hasLength(2));
});
```

Bloc - `bloc_test` gives arrange/act/assert on emitted states:

```dart
blocTest<SearchBloc, SearchState>(
  'emits [Loading, Loaded] on query',
  build: () => SearchBloc(mockRepo),
  act: (bloc) => bloc.add(SearchQueryChanged('cats')),
  wait: const Duration(milliseconds: 350), // ride out debounce transformers
  expect: () => [isA<SearchLoading>(), isA<SearchLoaded>()],
);
```

## Golden tests

```dart
testWidgets('card matches golden', (tester) async {
  await tester.pumpWidget(const MaterialApp(home: ProductCard(product: demo)));
  await expectLater(
    find.byType(ProductCard),
    matchesGoldenFile('goldens/product_card.png'),
  );
});
```

- Create/update baselines: `flutter test --update-goldens`.
- Goldens render with the Ahem placeholder font by default; load real fonts in a
  `flutter_test_config.dart` or accept blocky text consistently.
- Rendering differs slightly across OSes - pin golden generation to one platform
  in CI (e.g. run goldens on Linux only) or use a tolerance-comparator package.

## Integration tests (integration_test)

Live in `integration_test/`, run on a real device/emulator, drive the full app:

```dart
// integration_test/checkout_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('checkout happy path', (tester) async {
    app.main(); // or runApp with a staging config
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('product-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-to-cart')));
    await tester.tap(find.byKey(const ValueKey('checkout')));
    await tester.pumpAndSettle();

    expect(find.text('Order confirmed'), findsOneWidget);
  });
}
```

```bash
flutter test integration_test                      # local device/emulator
flutter test integration_test --flavor dev         # flavored apps
# Firebase Test Lab / Device Farm need the android/iOS native harness builds -
# for Android: ./gradlew app:assembleAndroidTest plus -Ptarget=... instrumentation.
```

- Point the app at a fake/staging backend via `--dart-define=API_URL=...`; never
  hit production.
- `pumpAndSettle` here too fails on endless animations - same fixed-duration
  workaround.

## Patrol (when you must touch native UI)

`integration_test` cannot interact with anything outside the Flutter view:
permission dialogs, notifications, WebViews, system settings. Patrol can.

```dart
patrolTest('grants location permission', ($) async {
  await $.pumpWidgetAndSettle(const MyApp());
  await $(#enableLocationButton).tap();       // finds by Key symbol
  await $.native.grantPermissionWhenInUse();  // taps the OS dialog
  await $.native.pressHome();
  await $.native.openApp();
  expect($(#locationBanner), findsOneWidget);
});
```

Run with the Patrol CLI, not plain `flutter test`:
`dart pub global activate patrol_cli` then `patrol test -t
integration_test/permissions_test.dart`. Patrol's finders (`$(#key)`,
`$('text')`) auto-wait and auto-settle, which removes most manual `pump` calls.

## CI notes

- `flutter test --coverage` writes `coverage/lcov.info`; gate on it if the repo does.
- Run `flutter analyze` and `dart format --set-exit-if-changed .` in the same job -
  test-passing-but-unformatted PRs bounce.
- Shard big suites: `flutter test --total-shards 4 --shard-index $N`.
- Widget tests run headless anywhere; integration tests in CI need an emulator
  step (e.g. `reactivecircus/android-emulator-runner`) or a device farm.
