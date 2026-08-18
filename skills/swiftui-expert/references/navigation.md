# Navigation: NavigationStack, NavigationPath, Split Views, Deep Links

`NavigationView` is deprecated. Everything here targets `NavigationStack`/`NavigationSplitView` (iOS 16+, current through iOS 18+). Training data is saturated with the old API - do not emit `NavigationView`, `NavigationLink(destination:isActive:)`, `NavigationLink(destination:tag:selection:)`, or `.navigationBarItems`.

## The model: data-driven navigation

Navigation state is *data* (a path of Hashable values); destinations are *declared* (`navigationDestination(for:)` maps value types to screens). Pushing = appending to the path. Popping = removing. Deep linking = constructing the path.

```swift
enum Route: Hashable {
    case product(Product.ID)
    case reviews(Product.ID)
    case checkout
}

struct ShopRoot: View {
    @State private var path: [Route] = []          // typed path - prefer over NavigationPath

    var body: some View {
        NavigationStack(path: $path) {
            ProductGrid()                           // root
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .product(let id): ProductDetail(id: id)
                    case .reviews(let id): ReviewList(productID: id)
                    case .checkout:        CheckoutView()
                    }
                }
        }
        .environment(\.navigate, Navigate { path.append($0) })   // optional: DI a navigate action
    }
}

// Links push by value - no destination views constructed up front:
NavigationLink(value: Route.product(product.id)) { ProductCard(product) }

// Programmatic control:
path.append(.checkout)                 // push
path.removeLast()                      // pop
path.removeAll()                       // pop to root
path = [.product(id), .reviews(id)]    // rebuild the whole stack (deep link)
```

Rules:

- `navigationDestination(for:)` goes **inside** the `NavigationStack` (on the root content), not outside it, and **never inside a lazy container** (`List` rows, `LazyVStack` content) - a destination registered from a lazy view may not exist when the value is pushed.
- One `navigationDestination(for: T.self)` per value type per stack. A single `Route` enum per flow keeps this trivially true and makes the `switch` exhaustive.
- The presenting *view values* must be `Hashable`. Push IDs, not fat model objects - `case product(Product.ID)` not `case product(Product)` - so paths stay cheap, equatable, and codable.

## Typed path vs NavigationPath

- **`[Route]` (typed array)** - default choice. Inspectable (`path.contains`), pattern-matchable, easy deep links.
- **`NavigationPath`** - type-erased heterogeneous path. Use only when a stack genuinely pushes unrelated types you can't unify into one enum (e.g., framework-provided values). Supports `append`, `removeLast`, `count`, and `codable` state restoration via `NavigationPath.CodableRepresentation` when every element is `Codable`.

```swift
@State private var path = NavigationPath()
path.append(product)          // any Hashable
path.append(user)             // different type, same path
// Restoration:
if let codable = path.codable { save(try JSONEncoder().encode(codable)) }
path = NavigationPath(try JSONDecoder().decode(NavigationPath.CodableRepresentation.self, from: data))
```

## navigationDestination(item:) - push driven by optional state

```swift
@State private var selectedOrder: Order?
List(orders) { order in
    Button(order.title) { selectedOrder = order }
}
.navigationDestination(item: $selectedOrder) { order in OrderDetail(order: order) }
// Setting the binding pushes; system pops set it back to nil.
```

Good for detail-from-selection without managing a path; don't mix it with a path-driven stack for the same flow.

## NavigationSplitView (iPad/Mac, adaptive to stack on iPhone)

```swift
struct MailView: View {
    @State private var selectedFolder: Folder?
    @State private var selectedMessage: Message.ID?

    var body: some View {
        NavigationSplitView {
            List(folders, selection: $selectedFolder) { folder in
                NavigationLink(folder.name, value: folder)
            }
        } content: {
            MessageList(folder: selectedFolder, selection: $selectedMessage)
        } detail: {
            if let id = selectedMessage { MessageDetail(id: id) }
            else { ContentUnavailableView("Select a message", systemImage: "envelope") }
        }
        .navigationSplitViewStyle(.balanced)
    }
}
```

- Selection drives columns: `List(selection:)` with `NavigationLink(value:)` rows. On compact width it automatically collapses to a push stack.
- A `NavigationStack` may live *inside* the detail column for drill-in beyond the columns; never nest a `NavigationStack` directly inside another `NavigationStack`'s pushed views.
- Detail column should always render something (`ContentUnavailableView` for empty selection).

## Deep links and routing

```swift
// shop://product/123/reviews
extension [Route] {
    static func parse(_ url: URL) -> [Route] {
        guard url.host() == "product",
              let id = url.pathComponents.dropFirst().first.flatMap(Product.ID.init)
        else { return [] }
        var path: [Route] = [.product(id)]
        if url.pathComponents.last == "reviews" { path.append(.reviews(id)) }
        return path
    }
}

WindowGroup { ShopRoot() }
    .onOpenURL { url in path = .parse(url) }        // replace, don't append - idempotent links
```

- Handle `onOpenURL` at the stack owner; replacing the path is idempotent for repeated links, appending is not.
- Tab apps: route to the tab first (`selectedTab = .shop`), then set that tab's path. Each tab owns its own `NavigationStack` and path.
- Cold start and warm start must behave identically - parsing into a path value guarantees it.

## Presentation (sheets, covers) alongside navigation

Sheets are separate from the path - model them as their own state, ideally item-driven:

```swift
enum Modal: Identifiable, Hashable {
    case login, filters(FilterSet)
    var id: Self { self }
}
@State private var modal: Modal?

.sheet(item: $modal) { modal in
    switch modal {
    case .login: LoginView()
    case .filters(let set): FilterView(initial: set)
    }
}
.sheet(item: $editingProduct) { product in ... }   // item-driven beats isPresented + force-unwrap
```

- A sheet gets its **own** `NavigationStack` if it needs pushes/toolbars; the parent's stack does not extend into it.
- `.presentationDetents([.medium, .large])`, `.presentationDragIndicator(.visible)` for half sheets.
- `.fullScreenCover` for flows that must not be swipe-dismissed; gate dismissal with `.interactiveDismissDisabled(hasUnsavedChanges)`.

## Toolbar and bar styling (replacing navigationBarItems)

```swift
.navigationTitle("Products")
.navigationBarTitleDisplayMode(.inline)
.toolbar {
    ToolbarItem(placement: .topBarTrailing) { Button("Add", systemImage: "plus") { modal = .add } }
    ToolbarItem(placement: .topBarLeading)  { EditButton() }
    ToolbarItemGroup(placement: .bottomBar) { FilterButton(); Spacer(); SortButton() }
}
.toolbarBackground(.visible, for: .navigationBar)
```

## Common navigation bugs

- **Push happens then immediately pops** - usually the pushed value's `Hashable`/identity changes on re-render (e.g., pushing a struct containing a freshly computed property), or the `navigationDestination` is registered in a lazy container. Push stable IDs; hoist the destination.
- **`navigationDestination` "was declared earlier on the stack" warning / wrong screen** - duplicate registrations for the same type. One registration per type per stack.
- **Back button disappears** - a second `NavigationStack` nested in pushed content. Pushed views inherit the stack; never wrap them in another one.
- **State lost on pop/push** - view identity churn in the path (see observation-state.md); path elements must be stable values.
- **`dismiss` from the wrong scope** - `@Environment(\.dismiss)` dismisses the nearest enclosing presentation *or* pops the current view; read it in the presented/pushed view itself, not in a parent, or it dismisses the wrong thing.
