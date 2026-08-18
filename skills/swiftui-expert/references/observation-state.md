# Observation State: @Observable, @Bindable, Environment DI, View Identity

Covers the Observation framework (iOS 17+), which replaces the ObservableObject stack, plus the view-identity and re-evaluation model that determines SwiftUI performance.

## The modern state toolbox

| Need | Tool |
|------|------|
| Local value state owned by one view | `@State var count = 0` |
| Reference-type model owned by a view/scene | `@State private var model = Model()` (yes, `@State`, not `@StateObject`) |
| Model passed down without ownership | plain `let model: Model` property - Observation tracks reads automatically |
| Two-way binding into an observable class's property | `@Bindable var model: Model` (or `@Bindable var m = model` inline in `body`) |
| Two-way binding to a value | `@Binding var text: String` (unchanged) |
| App-wide/feature-wide injection | `.environment(model)` + `@Environment(Model.self) private var model` |
| Optional environment value | `@Environment(Model.self) private var model: Model?` |

## @Observable basics

```swift
import Observation

@Observable @MainActor
final class CartModel {
    var items: [CartItem] = []          // tracked
    var total: Decimal { items.map(\.price).reduce(0, +) }  // computed from tracked
    @ObservationIgnored var analyticsCache: [String: Int] = [:]  // NOT tracked
    private let api: APIClient
    init(api: APIClient) { self.api = api }

    func load() async {
        do { items = try await api.cart() } catch { items = [] }
    }
}
```

Rules that differ from ObservableObject:

- The macro rewrites stored properties; **no `@Published`** - every stored property is tracked unless marked `@ObservationIgnored`.
- Tracking is **per-property and per-read**: a `body` re-runs only if a property it actually read changed. `objectWillChange` fired for *any* published property; Observation does not.
- Works with `let model` plain properties - a subview reading `model.items` re-renders when `items` changes, no property wrapper needed.
- Mark UI-facing models `@MainActor` so Swift 6 lets views call them freely (with Swift 6.2 default MainActor isolation, this is implicit for app-target types).
- `@Observable` requires a class. Value types use `@State`/`@Binding` as always.

## Ownership: @State owns reference types now

```swift
struct CheckoutView: View {
    @State private var model = CheckoutModel()   // created once per view identity, survives re-renders
    var body: some View { /* reads model.* */ }
}
```

Do not create models as plain properties (`let model = CheckoutModel()`): the struct is recreated on every parent re-render and your model resets. `@State` persists it for the view's identity lifetime. To inject dependencies, initialize with `@State private var model: CheckoutModel` and `init(api:)` setting `_model = State(initialValue: CheckoutModel(api: api))` - knowing that `initialValue` is only respected the *first* time that identity appears.

## Bindings into observable classes: @Bindable

`$model.property` requires a binding source. For `@Observable` classes that source is `@Bindable`:

```swift
struct ProfileEditor: View {
    @Bindable var profile: ProfileModel          // passed in, not owned
    var body: some View {
        TextField("Name", text: $profile.name)
        Toggle("Public", isOn: $profile.isPublic)
    }
}

// From the environment - @Bindable can't wrap @Environment, so derive it in body:
struct SettingsView: View {
    @Environment(SettingsModel.self) private var settings
    var body: some View {
        @Bindable var settings = settings
        Form { Toggle("Dark mode", isOn: $settings.darkMode) }
    }
}
```

## Environment as the DI container

```swift
@main struct ShopApp: App {
    @State private var store = StoreModel(api: .live)
    @State private var session = SessionModel()
    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)      // keyed by type
                .environment(session)
        }
    }
}
```

- Reading a type that was never injected crashes at runtime - declare it optional (`Model?`) if injection is conditional, and inject stubs in every `#Preview` and test host.
- For protocol-typed or multiple-instance injection, define an `EnvironmentKey`/`@Entry`:

```swift
extension EnvironmentValues {
    @Entry var apiClient: APIClient = .live   // @Entry macro replaces boilerplate EnvironmentKey
}
// .environment(\.apiClient, .stub)   /   @Environment(\.apiClient) private var api
```

## Migration from ObservableObject (only when asked)

| Legacy | Replacement |
|--------|-------------|
| `class M: ObservableObject` + `@Published var x` | `@Observable class M` + plain `var x` |
| `@StateObject private var m = M()` | `@State private var m = M()` |
| `@ObservedObject var m: M` | `var m: M` (or `@Bindable var m: M` if `$m.x` needed) |
| `.environmentObject(m)` / `@EnvironmentObject` | `.environment(m)` / `@Environment(M.self)` |
| `objectWillChange.send()` | delete - mutation of tracked properties is enough |
| Combine pipelines on `$published` | `withObservationTracking` / `Observations` async sequence, or keep Combine at the data layer |

Migrate a whole dependency chain at once: a view using `@ObservedObject` on an `@Observable` class will not compile, and mixing both stacks in one feature causes double refreshes.

## View identity and body re-evaluation

SwiftUI decides what "the same view" is by **structural identity** (position in the type tree) unless you give **explicit identity** (`.id(...)`, `ForEach` ids).

- `if showA { A() } else { B() }` - two different identities; swapping destroys A's `@State` and animates as remove/insert. `A().opacity(showA ? 1 : 0)` keeps one identity.
- Branches of the *same* type still get distinct identities from `if/else`. Prefer parameterizing one view: `Card(style: isBig ? .big : .small)`.
- `ForEach(items)` needs stable `Identifiable`/`id:` values. Using `id: \.self` on non-unique data, or indices as ids on a mutable array, causes wrong-row animations and state bleeding between rows.
- `.id(someChangingValue)` resets the subtree (state, scroll position, animations). It is a reset tool, not a refresh tool; never `.id(UUID())`.

Re-evaluation model: `body` is cheap-ish but not free, and dependency changes propagate top-down.

- A view re-renders when: its `@State`/`@Binding` value changes, an `@Observable` property it *read* changes, an environment value it reads changes, or its parent re-renders it with different stored properties (compared by equality).
- Keep `body` pure and fast - no allocation-heavy formatting, no `DateFormatter()` construction, no side effects. Move that work into the model or `static let`s.
- Extract hot rows into their own `View` structs (not `@ViewBuilder` funcs/computed properties on the parent) so diffing can skip them; a `func makeRow()` shares the parent's identity and re-runs whenever the parent does.
- `Equatable` conformance on a view lets SwiftUI skip `body` when inputs are equal - use it for heavy leaf views receiving value-type props.
- Debug with Instruments' SwiftUI template (View Body, Cause & Effect) or `Self._printChanges()` inside `body` (deprecated alias `_logChanges` on newer SDKs prints to unified logging).

## Anti-patterns

- **God model in the environment read by everything.** Per-property tracking saves you only if subviews read few properties. Split models per feature; pass leaf views plain values.
- **State duplication:** copying model data into `@State` in `onAppear` and editing the copy. Bind to the model (`@Bindable`) or pass `Binding`s; duplicated state desyncs.
- **`didSet` side effects on tracked properties** to trigger loads. Use `.task(id:)` or `.onChange(of:)` at the view, or an explicit method on the model, so effects are cancellable and testable.
- **Computed properties that read untracked storage** (`@ObservationIgnored` or statics) - the view won't update when that storage changes. Anything the UI must react to stays tracked.
