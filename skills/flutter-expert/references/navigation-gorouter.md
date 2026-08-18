# Navigation: GoRouter (15+)

go_router is the standard router for Flutter 3.3x. Do not mix raw
`Navigator.push(MaterialPageRoute(...))` into a GoRouter app for screen-level
navigation - it bypasses the URL, breaks deep links, web URLs, and state
restoration. (Dialogs/bottom sheets via `showDialog`/`showModalBottomSheet` are fine.)

```yaml
dependencies:
  go_router: ^16.0.0
```

## Core setup

```dart
final _rootNavigatorKey = GlobalKey<NavigatorState>();

final router = GoRouter(
  navigatorKey: _rootNavigatorKey,
  initialLocation: '/',
  debugLogDiagnostics: true, // dev only
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const HomeScreen(),
      routes: [
        // Nested route -> '/details/:id'; child pushes ON TOP of parent.
        GoRoute(
          path: 'details/:id',
          builder: (context, state) => DetailsScreen(
            id: state.pathParameters['id']!,
            // Query params: /details/42?tab=reviews
            tab: state.uri.queryParameters['tab'],
            // `extra` carries objects, but is lost on deep link/web refresh -
            // always make the screen loadable from the id alone.
            preloaded: state.extra as Product?,
          ),
        ),
      ],
    ),
    GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
  ],
  errorBuilder: (context, state) => NotFoundScreen(uri: state.uri),
);

MaterialApp.router(routerConfig: router);
```

## go vs push vs replace

- `context.go('/details/1')` - navigates to the location; the stack becomes the
  route hierarchy of that path (parents above it). Back button follows hierarchy.
- `context.push('/details/1')` - stacks on top of the current page regardless of
  hierarchy; `context.pop()` returns. `push` returns a `Future<T?>` for results:
  `final ok = await context.push<bool>('/confirm');`
- `context.replace(...)` / `pushReplacement(...)` - swap current entry.
- Pop with a result: `context.pop(true)`.
- Named routes: give routes `name:` and use `context.goNamed('details',
  pathParameters: {'id': '1'})` - safer than string interpolation.

## Redirects (auth guards)

`redirect` runs on every navigation and every `refreshListenable` tick. Return a
new location or `null` (no redirect). Keep it synchronous and fast.

```dart
final router = GoRouter(
  refreshListenable: authState, // any Listenable; re-evaluates redirect on change
  redirect: (context, state) {
    final loggedIn = authState.isLoggedIn;
    final onLogin = state.matchedLocation == '/login';
    if (!loggedIn && !onLogin) {
      return '/login?from=${Uri.encodeComponent(state.matchedLocation)}';
    }
    if (loggedIn && onLogin) {
      return state.uri.queryParameters['from'] ?? '/';
    }
    return null;
  },
  routes: [...],
);
```

With Riverpod, bridge a provider to a `Listenable`:

```dart
class AuthListenable extends ChangeNotifier {
  AuthListenable(Ref ref) {
    ref.listen(authProvider, (_, __) => notifyListeners());
  }
}
```

Per-route `redirect:` also exists (runs after the top-level one) - use for
role-gating a subtree. Redirect loops throw; the `from` query-param pattern above
avoids them.

## Tabs that keep state: StatefulShellRoute

`ShellRoute` wraps children in shared chrome but one navigator. For bottom-nav
tabs that each keep their own stack and scroll position, use
`StatefulShellRoute.indexedStack`:

```dart
StatefulShellRoute.indexedStack(
  builder: (context, state, navigationShell) => Scaffold(
    body: navigationShell,
    bottomNavigationBar: NavigationBar(
      selectedIndex: navigationShell.currentIndex,
      onDestinationSelected: (i) => navigationShell.goBranch(
        i,
        // Tap current tab again -> pop that tab to its root:
        initialLocation: i == navigationShell.currentIndex,
      ),
      destinations: const [
        NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
        NavigationDestination(icon: Icon(Icons.person), label: 'Profile'),
      ],
    ),
  ),
  branches: [
    StatefulShellBranch(routes: [
      GoRoute(path: '/', builder: (_, __) => const HomeTab(), routes: [
        GoRoute(path: 'item/:id', builder: ...), // pushes INSIDE the Home tab
      ]),
    ]),
    StatefulShellBranch(routes: [
      GoRoute(path: '/profile', builder: (_, __) => const ProfileTab()),
    ]),
  ],
)
```

To push a screen over the whole shell (hide the bottom bar), give the route
`parentNavigatorKey: _rootNavigatorKey`.

## Deep links / app links

Flutter handles the plumbing; GoRouter maps the incoming URI to a route
automatically (initial and while-running links).

- Android - `android/app/src/main/AndroidManifest.xml`, inside the main activity:

```xml
<meta-data android:name="flutter_deeplinking_enabled" android:value="true" />
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="https" android:host="example.com" android:pathPrefix="/app" />
</intent-filter>
```

App Links verification also needs `https://example.com/.well-known/assetlinks.json`
with the app's package name + SHA-256 signing cert fingerprint.

- iOS - Universal Links: add the Associated Domains capability
  (`applinks:example.com`) and host
  `https://example.com/.well-known/apple-app-site-association`. Custom schemes go
  in `Info.plist` under `CFBundleURLTypes`.
- Test without a backend:
  `adb shell am start -a android.intent.action.VIEW -d "https://example.com/app/details/1" com.example.app`
  and on iOS simulator: `xcrun simctl openurl booted "https://example.com/app/details/1"`.
- Deep-linked screens must construct themselves from path/query params only -
  `state.extra` is null on a cold-start deep link.

## Typed routes (go_router_builder)

For larger apps, generate type-safe routes to eliminate string typos:

```dart
part 'routes.g.dart';

@TypedGoRoute<DetailsRoute>(path: '/details/:id')
class DetailsRoute extends GoRouteData with _$DetailsRoute {
  const DetailsRoute({required this.id, this.tab});
  final String id;
  final String? tab; // becomes ?tab=

  @override
  Widget build(BuildContext context, GoRouterState state) =>
      DetailsScreen(id: id, tab: tab);
}

// Navigate: const DetailsRoute(id: '42', tab: 'reviews').go(context);
```

Run `dart run build_runner build --delete-conflicting-outputs` after editing.

## Gotchas

- `GoRouter` must be a long-lived instance (global/provider) - rebuilding it in
  `build` resets the whole navigation state.
- Back-button interception: `WillPopScope` is dead; use
  `PopScope(canPop: false, onPopInvokedWithResult: (didPop, result) {...})`.
- `state.uri.queryParameters` (not the removed `state.queryParams`); full
  location is `state.uri.toString()`, matched pattern is `state.matchedLocation`.
- Route paths are matched case-sensitively by default (`caseSensitive: false` per route to relax).
- Nested `GoRoute` paths must NOT start with `/`.
