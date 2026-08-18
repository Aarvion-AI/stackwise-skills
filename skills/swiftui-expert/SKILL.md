---
name: swiftui-expert
description: Use when working in a native iOS/SwiftUI project - *.swift files, an *.xcodeproj or Package.swift, Xcode schemes, or mentions of SwiftUI, Swift 6, @Observable, SwiftData, NavigationStack, actors, or Swift Testing. Builds views and features, wires Observation-based state, fixes Swift 6 strict-concurrency errors, models persistence with SwiftData, and writes Swift Testing/XCTest suites for iOS 18+ apps. Invoke for adding screens or view models, migrating ObservableObject to @Observable, resolving Sendable/actor-isolation compile errors, NavigationStack routing and deep links, async URLSession networking, diagnosing excess body re-evaluation, and UI-test-ready accessibility identifiers.
license: MIT
metadata:
  version: "0.1.0"
  category: mobile
  frameworks: "Swift 6.x, SwiftUI (iOS 18+), SwiftData, Swift Testing, Xcode 16+"
  triggers: swiftui, swift 6, ios, xcode, @Observable, @Bindable, observation, sendable, actor, @MainActor, strict concurrency, swiftdata, @Model, @Query, navigationstack, navigationpath, urlsession, async await, swift testing, @Test, #expect, xctest, xcuitest, preview, accessibility identifier
  related: flutter-expert, react-native-expert, mobile-qa-expert
---

# SwiftUI Expert

Turns Claude into a senior iOS engineer who ships Swift 6 / iOS 18+ SwiftUI - Observation-based state, strict concurrency that compiles, SwiftData, NavigationStack - instead of the ObservableObject/NavigationView idioms that dominate training data.

## When to Use This Skill

- Building screens, components, or features in a SwiftUI app
- Wiring state with the Observation framework (`@Observable`, `@Bindable`, `@State`) or migrating off `ObservableObject`/`@Published`
- Fixing Swift 6 strict-concurrency compile errors (Sendable, actor isolation, `@MainActor`)
- Navigation with `NavigationStack`/`NavigationPath`: programmatic routing, deep links, split views
- Persistence with SwiftData (`@Model`, `@Query`) or deciding SwiftData vs Core Data
- Async/await networking with URLSession and dependency injection via `@Environment`
- Diagnosing unnecessary `body` re-evaluation, view-identity bugs, or slow lists
- Writing Swift Testing (`@Test`, `#expect`) and XCTest/XCUITest suites, including accessibility identifiers for UI testability

## Core Workflow

1. **Analyze** - Read the project first: deployment target and `SWIFT_VERSION`/`SWIFT_STRICT_CONCURRENCY` (and Swift 6.2 default-isolation settings) in project.pbxproj or `Package.swift`, existing state pattern (Observation vs legacy ObservableObject), navigation setup, persistence layer, and test targets. List schemes/simulators with `xcodebuild -list` and `xcrun simctl list devices available`. Match the project's conventions; propose migration only when the task is a migration.
2. **Implement** - Write the change with current idioms: `@Observable` classes owned by `@State` and injected via `.environment(...)`, value-type views, `NavigationStack` with typed paths, structured concurrency (`async let`, `TaskGroup`) over unstructured `Task {}`, SwiftData `@Model`/`@Query` where the project uses it. Add `.accessibilityIdentifier(...)` to any interactive element a UI test will need.
3. **Verify build** - Run `xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 16' build` (or `swift build` for a package); fix all reported issues and re-run until clean before proceeding. Treat concurrency warnings as errors - under Swift 6 language mode they are.
4. **Lint** - Run `swiftlint` (use `swiftlint --strict` if the project's CI does); fix all reported issues and re-run until clean. Respect the project's `.swiftlint.yml`; do not disable rules inline to silence findings.
5. **Test** - Write or update tests for the change (Swift Testing `@Test`/`#expect` for new tests; keep existing XCTest suites in their framework), then run `xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 16' test` (or `swift test` for a package); fix all failures and re-run until every test passes.
6. **Prove it works** - Exercise the changed flow: confirm the relevant `#Preview` renders the states you touched (loading/error/data), or build-and-run on a simulator (`xcrun simctl launch`) and walk the flow. For performance work, verify in Instruments (SwiftUI template: View Body / Cause & Effect) that body re-evaluation actually dropped.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Observation state: `@Observable`, `@Bindable`, `@State`, Environment DI, ObservableObject migration, view identity & re-evaluation | `references/observation-state.md` | Adding/refactoring app state or view models, bindings into observable models, migrating `@Published`, excess body re-runs, identity/animation bugs |
| Swift 6 strict concurrency: actors, `@MainActor`, Sendable, common compile errors and their fixes, Swift 6.2 default isolation | `references/swift6-concurrency.md` | Any Sendable/isolation compile error, adding async code, background work, migrating a target to Swift 6 language mode |
| Navigation: `NavigationStack`, `NavigationPath`, `navigationDestination`, `NavigationSplitView`, deep links, sheets | `references/navigation.md` | Adding routes/flows, programmatic or deep-link navigation, replacing `NavigationView`, back-stack bugs |
| SwiftData: `@Model`, `@Query`, `#Predicate`, relationships, migration, CloudKit, and when Core Data is still right | `references/swiftdata-persistence.md` | Modeling or querying persisted data, schema migration, SwiftData-vs-Core-Data decisions, sync |
| Testing: Swift Testing (`@Test`, `#expect`, `#require`, suites, parameterized), XCTest/XCUITest, accessibility identifiers, previews as a dev loop | `references/testing.md` | Writing or fixing any test, choosing Swift Testing vs XCTest, UI-test element queries, preview setup |

## Key Patterns

**Observable model + Environment injection (the default architecture):**

```swift
@Observable @MainActor
final class StoreModel {
    var products: [Product] = []
    var isLoading = false
    private let client: APIClient
    init(client: APIClient) { self.client = client }
    func load() async { /* ... */ }
}

@main struct ShopApp: App {
    @State private var store = StoreModel(client: .live)   // @State owns it
    var body: some Scene {
        WindowGroup { RootView().environment(store) }      // .environment, not .environmentObject
    }
}

struct RootView: View {
    @Environment(StoreModel.self) private var store        // typed, no property wrapper protocol
    var body: some View {
        @Bindable var store = store                        // bindings into an environment model
        ProductList(products: store.products)
            .searchable(text: $store.query)
            .task { await store.load() }
    }
}
```

**NavigationStack with a typed path (programmatic + deep-linkable):**

```swift
enum Route: Hashable { case product(Product.ID), cart, settings }

struct ContentView: View {
    @State private var path: [Route] = []
    var body: some View {
        NavigationStack(path: $path) {
            HomeView()
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .product(let id): ProductView(id: id)
                    case .cart: CartView()
                    case .settings: SettingsView()
                    }
                }
        }
        .onOpenURL { url in path = Route.parse(url) }   // deep link = set the path
    }
}
```

**Async networking, checked and typed:**

```swift
func fetch<T: Decodable>(_ type: T.Type, from url: URL) async throws -> T {
    let (data, response) = try await URLSession.shared.data(from: url)
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
        throw APIError.badStatus((response as? HTTPURLResponse)?.statusCode ?? -1)
    }
    return try JSONDecoder().decode(T.self, from: data)
}
```

**Swift Testing over XCTest for new unit tests:**

```swift
import Testing

@Suite struct PriceTests {
    @Test(arguments: [(100, "₹100"), (0, "Free")])
    func formats(amount: Int, expected: String) {
        #expect(Price(amount).display == expected)
    }

    @Test func loadsProducts() async throws {
        let store = StoreModel(client: .stub)
        await store.load()
        let first = try #require(store.products.first)   // unwraps or fails the test
        #expect(first.name == "Widget")
    }
}
```

## Common Mistakes

- **Writing `ObservableObject`/`@Published`/`@StateObject`/`@EnvironmentObject` in new code.** On iOS 17+ use `@Observable` with `@State` ownership, `.environment(...)`, and `@Environment(Type.self)`. `@Bindable` (not `@Binding`) creates bindings into an observable class. Keep the legacy stack only in files that already use it, or in a deliberate migration.
- **Spawning `Task { await vm.load() }` in `onAppear`.** Use `.task { await vm.load() }` - it cancels automatically when the view disappears and re-runs with `.task(id:)` when inputs change. Unstructured tasks leak past the view's lifetime.
- **Silencing Swift 6 concurrency errors with `@unchecked Sendable` or `nonisolated(unsafe)`.** These erase the compiler's proof, and are almost never the fix. Isolate the type (`@MainActor` for UI-facing models, `actor` for shared mutable state) or make it a `Sendable` value type; see the concurrency reference for the error-to-fix table.
- **`NavigationView`, `.navigationBarItems`, `NavigationLink(destination:isActive:)`.** All deprecated. Use `NavigationStack`/`NavigationSplitView`, `.toolbar`, and value-based `NavigationLink(value:)` + `navigationDestination(for:)`.
- **Conditional view branches that destroy identity.** `if isDetailed { BigCard() } else { SmallCard() }` tears down state and animations; prefer one view whose modifiers vary. Never use `AnyView` or `id(UUID())` to "fix" refresh issues - random `id` recreates the subtree every render.
- **Passing whole `@Observable` models through many layers "for convenience".** Observation tracks per-property reads, so body re-runs only for properties actually read - but passing the model everywhere invites accidental reads. Pass the values a subview needs; keep models at feature roots.
- **Fetching SwiftData manually in `onAppear` and storing results in `@State`.** Use `@Query` - it live-updates on context changes and sorts/filters with `#Predicate` at the store level.
- **Testing async view-model code with `XCTestExpectation` polling.** Swift Testing's `async` test functions plus `confirmation(...)` cover callbacks; `await store.load()` directly - no `waitForExpectations`, no `sleep`.
