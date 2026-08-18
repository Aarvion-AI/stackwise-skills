# Testing: Swift Testing, XCTest/XCUITest, Accessibility Identifiers, Previews as a Dev Loop

Swift Testing (Xcode 16+, `import Testing`) is the default for new unit tests. XCTest remains for UI tests (`XCUIApplication` has no Swift Testing equivalent) and performance tests (`measure`). Both frameworks coexist in one test target and both run under `xcodebuild test` and `swift test`.

## Swift Testing essentials

```swift
import Testing
@testable import Shop

@Suite("Cart")
struct CartTests {
    let cart = Cart()                       // fresh instance per test - init runs for EACH @Test

    @Test func startsEmpty() {
        #expect(cart.items.isEmpty)
    }

    @Test func addsItem() throws {
        cart.add(.stub(name: "Widget"))
        let first = try #require(cart.items.first)   // stops the test if nil - no force unwraps
        #expect(first.name == "Widget")
        #expect(cart.total == 999)
    }

    @Test func throwsOnEmptyCheckout() {
        #expect(throws: CartError.empty) { try cart.checkout() }
    }
}
```

- `#expect(expr)` takes any boolean expression and prints the *decomposed* values on failure - no `XCTAssertEqual`-style API zoo, no custom messages needed for readable output.
- `#require` unwraps optionals or asserts preconditions and exits the test on failure (replaces `XCTUnwrap` + `continueAfterFailure = false`).
- Struct suites give per-test isolation via `init`/`deinit` (use a class + `deinit` when teardown is needed). No `setUp`/`tearDown`.
- Tests run **in parallel by default** - including within a suite. Shared global state will flake; isolate it or mark the suite `.serialized`:

```swift
@Suite(.serialized) struct KeychainTests { ... }
```

## Parameterized tests and traits

```swift
@Test(arguments: [
    ("₹0", 0), ("₹1,000", 1000), ("₹99,999", 99999),
])
func formatsINR(expected: String, paise amount: Int) {
    #expect(PriceFormatter.inr(amount) == expected)
}

// Two collections = cartesian product; zip to pair them:
@Test(arguments: zip(inputs, expectedOutputs))
func parses(input: String, expected: Token) { ... }

@Test(.enabled(if: FeatureFlags.newCheckout), .tags(.checkout))
func newCheckoutFlow() async throws { ... }

@Test(.timeLimit(.minutes(1))) func slowImport() async throws { ... }

@Test(.bug("https://github.com/org/repo/issues/412", "Crash on empty cart"))
func regression412() { ... }
```

Each argument set is a separately reported, separately re-runnable test case - stop writing `for` loops inside one test.

## Async and concurrency-aware tests

```swift
@Test @MainActor
func loadPopulatesProducts() async throws {
    let model = StoreModel(client: .stub(returning: [.widget]))
    await model.load()
    #expect(model.products.count == 1)
}

// Callback-based APIs - confirmation replaces XCTestExpectation:
@Test func deliversCallback() async {
    await confirmation("delegate called", expectedCount: 1) { confirmed in
        let sut = Uploader()
        sut.onFinish = { confirmed() }
        await sut.uploadAll()
    }
}
```

- Annotate the test `@MainActor` when it touches `@MainActor` models - do not sprinkle `await MainActor.run`.
- `confirmation` must be *confirmed before its body returns*; it does not wait/poll. For "eventually true" conditions, await the actual async operation - never `Task.sleep` polling loops.
- Stub the clock/network at the dependency seam (Environment or init injection), not with real waits.

## Keeping XCTest where it belongs

Migrate assertions opportunistically (`XCTAssertEqual(a, b)` → `#expect(a == b)`), but keep XCTest for:

- **UI tests** - `XCUIApplication` (below).
- **Performance** - `measure { }` / `XCTMetric`.
- Existing large suites - mixing frameworks per-file is fine; don't rewrite wholesale unless asked.

## Accessibility identifiers: build for UI testability

Set identifiers on every element a UI test (or an external test harness) must find. Identifiers are invisible to users and independent of localization - never query by display text in tests.

```swift
// Production code:
Button("Add to cart") { cart.add(product) }
    .accessibilityIdentifier("product.addToCart")

TextField("Email", text: $email)
    .accessibilityIdentifier("auth.email")

List(products) { product in
    ProductRow(product)
        .accessibilityIdentifier("product.row.\(product.id)")   // stable per-item ids
}
```

Conventions that pay off: `feature.element` dot-paths, stable IDs (not indexes) for collection rows, one place (an enum of static strings shared between app and UI-test targets) so identifiers can't drift:

```swift
enum AXID { static let addToCart = "product.addToCart"; static let email = "auth.email" }
.accessibilityIdentifier(AXID.addToCart)
```

## XCUITest patterns

```swift
final class CheckoutUITests: XCTestCase {
    let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launchArguments += ["-uiTesting", "-seedData"]   // app reads these to stub network/state
        app.launch()
    }

    func testAddToCartBadge() {
        app.buttons[AXID.addToCart].tap()
        let badge = app.staticTexts["cart.badge"]
        XCTAssertTrue(badge.waitForExistence(timeout: 5))    // wait, never sleep()
        XCTAssertEqual(badge.label, "1")
    }
}
```

- Query by identifier: `app.buttons["product.addToCart"]`, `app.textFields["auth.email"]`.
- `waitForExistence(timeout:)` before asserting; `sleep()` is a flake generator.
- Launch arguments/environment are the seam for deterministic UI tests - the app checks them at startup to install stub clients and seed in-memory SwiftData.
- SwiftUI flattens some hierarchies: a labeled control may surface as `app.buttons[...]` even when built from HStacks; use `app.descendants(matching: .any)["id"]` or the Accessibility Inspector to debug queries.

## Running tests

```bash
# Whole scheme on a simulator (runs Swift Testing + XCTest together):
xcodebuild -scheme Shop -destination 'platform=iOS Simulator,name=iPhone 16' test

# One suite / one test:
xcodebuild ... test -only-testing:ShopTests/CartTests
xcodebuild ... test -only-testing:ShopTests/CartTests/addsItem

# SwiftPM package targets:
swift test                       # all
swift test --filter CartTests    # subset
```

Fix all failures and re-run until every test passes; a test you can't make deterministic gets fixed or deleted, not retried in CI.

## Previews as a dev loop

`#Preview` is the fastest verification step for view work - treat previews as executable documentation of view states, and keep them compiling (they break silently when neglected).

```swift
#Preview("Loaded") {
    ProductDetail(product: .stub)
        .environment(StoreModel(client: .stub))       // previews need every Environment dependency
}

#Preview("Loading") { ProductDetail(product: .stub, state: .loading) }

#Preview("Editable state") {
    @Previewable @State var quantity = 1              // @Previewable: live state inside a preview
    QuantityStepper(value: $quantity)
}

#Preview(traits: .sizeThatFitsLayout) { Badge(count: 3) }
```

- One preview per meaningful state (empty / loading / error / loaded / max-content) - this is where truncation, dark-mode, and Dynamic Type bugs surface. Add `.preferredColorScheme(.dark)` and `.dynamicTypeSize(.accessibility3)` variants for critical screens.
- Missing environment injections crash the preview, not the compile - inject stub models exactly as tests do; share the stub factories between previews and tests.
- For SwiftData views use an in-memory container via a `PreviewModifier` (see swiftdata-persistence.md).
- Preview stubs (`Model.stub`, `APIClient.stub`) live in the main target under `#if DEBUG` or in a dev-only module so both previews and tests reuse them.
