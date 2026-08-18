---
name: flutter-expert
description: Use when working in a Flutter project - pubspec.yaml, *.dart files, lib/main.dart, analysis_options.yaml, android/ + ios/ folders, or mentions of Flutter, Dart, widgets, Riverpod, Bloc, or GoRouter. Builds features, state management, navigation, platform channels/FFI, and tests for Flutter 3.3x / Dart 3.x apps. Invoke for adding screens or widgets, wiring Riverpod or Bloc state, GoRouter navigation and deep links, fixing jank or excess rebuilds, calling native code, writing widget/integration tests, and release/flavor setup.
license: MIT
metadata:
  version: "0.1.0"
  category: mobile
  frameworks: "Flutter 3.32-3.3x, Dart 3.x, Riverpod 2/3, bloc 9, go_router 15+, freezed 3, patrol 3"
  triggers: flutter, dart, pubspec.yaml, widget, riverpod, bloc, cubit, go_router, gorouter, freezed, json_serializable, build_runner, platform channel, method channel, ffi, pigeon, widget test, integration_test, patrol, flavors, app signing
  related: mobile-qa-expert, fastapi-expert, nestjs-expert
---

# Flutter Expert

Turns Claude into a senior Flutter engineer who ships idiomatic Dart 3 / Flutter 3.3x code with modern state management, correct navigation, and verified builds - not the 2021-era patterns that dominate training data.

## When to Use This Skill

- Building screens, widgets, or features in an existing Flutter app
- Choosing and wiring state management (Riverpod code-gen providers, AsyncNotifier, Bloc/Cubit)
- Navigation with GoRouter: ShellRoute/StatefulShellRoute, auth redirects, deep links
- Diagnosing jank, excessive rebuilds, or slow lists
- Calling native platform code (MethodChannel, Pigeon) or C libraries (dart:ffi)
- Modeling data with freezed + json_serializable and Dart 3 sealed classes/records
- Writing widget tests, golden tests, and integration tests (integration_test, patrol)
- Release prep: flavors, Android signing, iOS provisioning basics

## Core Workflow

1. **Analyze** - Read `pubspec.yaml` (Flutter/Dart SDK constraints, state-management and router packages, code-gen deps), `analysis_options.yaml` (lint set), and `lib/` layout before writing anything. Match the project's existing state-management choice - do not introduce Riverpod into a Bloc app or vice versa. Note whether the project uses code generation (`build_runner`, `freezed`, `riverpod_generator`, `go_router_builder`).
2. **Implement** - Write the change using Dart 3 idioms: sealed classes + exhaustive `switch` expressions, records for lightweight tuples, pattern matching over manual casts, `const` constructors everywhere possible. Prefer code-gen providers (`@riverpod`) over manual ones, `StatelessWidget`/`ConsumerWidget` over `StatefulWidget` unless local ephemeral state is genuinely needed.
3. **Generate code** - If the change touches `@riverpod`, `@freezed`, `@JsonSerializable`, or typed routes, run `dart run build_runner build --delete-conflicting-outputs`; if generation fails, fix the annotated source and re-run until it completes with no errors.
4. **Verify analyze/format** - Run `dart format .` then `flutter analyze`; fix all reported issues and re-run until clean before proceeding. Treat infos/deprecations (e.g. `withOpacity`, `WillPopScope`) as real work items, not noise.
5. **Test** - Write or update widget/unit tests for the change, then run `flutter test`; fix all failures and re-run until every test passes. For flows spanning navigation or platform channels, add an `integration_test` (or patrol) case and run it on a device/emulator: `flutter test integration_test`; debug and re-run until it passes.
6. **Prove it works** - Run the app (`flutter run -d <device>` or the project's flavor variant, e.g. `flutter run --flavor dev -t lib/main_dev.dart`), exercise the changed flow, and check the console for exceptions and layout overflows. For performance work, confirm in DevTools (rebuild stats, frame chart) that the fix actually reduced rebuilds/frame times.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| State management: Riverpod 2/3 code-gen, AsyncNotifier, Bloc/Cubit, freezed models | `references/state-riverpod-bloc.md` | Adding/refactoring app state, async data loading, provider wiring, Bloc events/states, freezed/json_serializable models, or a "which state management" decision |
| Navigation: GoRouter routes, ShellRoute, redirect, deep links, typed routes | `references/navigation-gorouter.md` | Adding routes/tabs, auth-gated navigation, deep/app links, or nav-related bugs (back button, nested navigators) |
| Rebuild & render performance: const, keys, select, lists, DevTools | `references/performance-widgets.md` | Jank, dropped frames, "whole screen rebuilds", slow/scroll-stuttering lists, or any perf review |
| Platform integration: MethodChannel/EventChannel, Pigeon, dart:ffi; release flavors + signing | `references/platform-integration.md` | Calling Android/iOS native APIs, wrapping a C library, channel-related crashes, or setting up flavors/signing for release |
| Testing: widget tests, ProviderScope/Bloc overrides, goldens, integration_test, patrol | `references/testing.md` | Writing or fixing any Flutter test, flaky `pumpAndSettle`, mocking state/channels, device-level E2E |

## Key Patterns

**Riverpod code-gen AsyncNotifier (the default for async app state):**

```dart
@riverpod
class Cart extends _$Cart {
  @override
  Future<List<CartItem>> build() => ref.watch(cartRepoProvider).fetch();

  Future<void> add(Product p) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      await ref.read(cartRepoProvider).add(p);
      return ref.read(cartRepoProvider).fetch();
    });
  }
}

// In build(): exhaustive handling, no .when soup needed in Dart 3
switch (ref.watch(cartProvider)) {
  AsyncData(:final value) => CartList(items: value),
  AsyncError(:final error) => ErrorView(error),
  _ => const CircularProgressIndicator(),
}
```

**Sealed state + exhaustive switch (Bloc or plain):**

```dart
sealed class LoginState {}
final class LoginIdle extends LoginState {}
final class LoginLoading extends LoginState {}
final class LoginFailure extends LoginState { LoginFailure(this.message); final String message; }
final class LoginSuccess extends LoginState { LoginSuccess(this.user); final User user; }
// switch (state) { ... } - compiler errors if a case is missed; no `default`.
```

**GoRouter auth redirect that re-evaluates on state change:**

```dart
final router = GoRouter(
  refreshListenable: authNotifier,          // re-run redirect when auth changes
  redirect: (context, state) {
    final loggedIn = authNotifier.isLoggedIn;
    final loggingIn = state.matchedLocation == '/login';
    if (!loggedIn && !loggingIn) return '/login?from=${state.matchedLocation}';
    if (loggedIn && loggingIn) return state.uri.queryParameters['from'] ?? '/';
    return null;                             // no redirect
  },
  routes: [/* ... */],
);
```

**Rebuild only what changed:**

```dart
// Watch one field, not the whole object:
final name = ref.watch(userProvider.select((u) => u.name));
// Scoped MediaQuery lookups (3.10+): rebuilds only on size changes
final size = MediaQuery.sizeOf(context);
```

## Common Mistakes

- **Writing pre-code-gen Riverpod** (`StateProvider`, `StateNotifierProvider`, `ChangeNotifierProvider`) in projects using `riverpod_generator`. Use `@riverpod` classes (`Notifier`/`AsyncNotifier`); `StateNotifier` is legacy and removed from Riverpod 3's core.
- **`ref.watch` inside callbacks** (`onPressed`, event handlers). `watch` is for `build`; use `ref.read` in callbacks and `ref.listen` for side effects like snackbars/navigation.
- **Using `BuildContext` across async gaps** without a `context.mounted` guard - a real crash and an analyzer lint (`use_build_context_synchronously`). Check `if (!context.mounted) return;` after every `await` before touching context.
- **Deprecated APIs from training data:** `WillPopScope` → `PopScope(canPop:, onPopInvokedWithResult:)`; `Color.withOpacity` → `withValues(alpha:)`; `MediaQuery.of(context).size` → `MediaQuery.sizeOf(context)`; `RaisedButton`/`FlatButton` → `ElevatedButton`/`TextButton`; `accentColor` → `colorScheme.secondary`.
- **Mixing `Navigator.push` with GoRouter** - the imperative push bypasses the router's URL/state and breaks deep links and web URLs. Use `context.go`/`context.push` (and know the difference: `go` replaces the stack per route hierarchy, `push` stacks).
- **`ListView(children: [...])` for long/unbounded lists** - builds everything eagerly. Use `ListView.builder`/`.separated` (with `itemExtent` or `prototypeItem` when heights are uniform), and give list items stable `ValueKey`s when reordering/removing.
- **Null-safety by force:** sprinkling `!` and `late` to silence the compiler. Prefer promotion via patterns (`if (user case User(:final email))`), `??`/`?.`, and making fields non-nullable at construction; each `!` and non-initialized `late` is a runtime crash waiting.
- **`pumpAndSettle` in tests with repeating animations** (shimmer, `CircularProgressIndicator`) - times out. Pump fixed durations instead (`await tester.pump(const Duration(milliseconds: 300))`).
