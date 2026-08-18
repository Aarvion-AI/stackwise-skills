# Swift 6 Strict Concurrency: Actors, @MainActor, Sendable, Error-to-Fix Table

Swift 6 language mode makes data-race safety a compile-time guarantee. Most "SwiftUI code that used to work" fails here; this file maps the errors to their real fixes.

## Project settings that change everything

Check these before diagnosing any concurrency error:

- `SWIFT_VERSION = 6.0` (or `swiftLanguageModes: [.v6]` in Package.swift) - strict checking is on, warnings become errors.
- Swift 5 mode + `SWIFT_STRICT_CONCURRENCY = complete` - same diagnostics as warnings; fix them the same way.
- **Swift 6.2 "approachable concurrency"** (new Xcode templates default to it):
  - `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` - every unannotated type/function in that module is implicitly `@MainActor`. Explains why example code compiles in a fresh app target but fails in your package.
  - `NonisolatedNonsendingByDefault` feature - `nonisolated async` functions run on the *caller's* actor unless marked `@concurrent`.
- Under default-MainActor modules, opt work *off* the main actor explicitly:

```swift
@concurrent func parseHugeJSON(_ data: Data) async throws -> Catalog { ... } // always off-main
nonisolated struct Parser { ... }                                            // opt a type out
```

## Isolation model in one page

- **`@MainActor`** - one global serial actor bound to the main thread. SwiftUI `View.body`, `App`, and most UI-facing code are main-actor-isolated. Annotate view models `@MainActor` and stop fighting.
- **`actor`** - a type whose mutable state is isolated; external calls are `await`ed. Use for shared mutable state accessed from multiple tasks (caches, connection pools, rate limiters).
- **`nonisolated`** - opts a member out of its type's isolation; it can then only touch immutable/`Sendable` state. Good for pure helpers, `Codable` conformances, protocol requirements.
- **`Sendable`** - a type safe to send across isolation boundaries. Value types of Sendable properties are implicitly Sendable; classes must be `final` with only immutable Sendable storage (or be an actor / `@MainActor`).
- **`sending`** parameters/results - transfer ownership of a non-Sendable value across a boundary when the compiler can prove the sender never touches it again. Often the fix for "pass this builder into a Task".
- **`Mutex<Value>`** (`import Synchronization`, iOS 18+) - lock-protected state when an actor's `await` is unacceptable; the wrapper type can then be `Sendable`.

## Error-to-fix table

| Compiler error (abridged) | Root cause | Fix, in order of preference |
|---|---|---|
| `Main actor-isolated property 'x' can not be referenced from a nonisolated context` | Background code touching UI-facing state | Make the caller `@MainActor`; or hop: `await MainActor.run { ... }`; or make the member `nonisolated` if it's pure |
| `Call to main actor-isolated instance method in a synchronous nonisolated context` | Calling a `@MainActor` method without `await` from outside | `await` it from an async context; or move the caller onto `@MainActor` |
| `Non-sendable type 'T' passed in call to ... crossing actor boundary` / `cannot exit main actor-isolated context` | Passing a non-Sendable class between isolation domains | Make `T` Sendable (struct, or `final class` + immutable, or actor); or mark the parameter `sending`; or keep the whole flow in one isolation domain |
| `Capture of 'self' with non-Sendable type in a '@Sendable' closure` | `Task { self.doWork() }` inside a non-Sendable class | Isolate the class (`@MainActor` or make it an `actor`); or capture only the Sendable values you need: `Task { [id] in ... }` |
| `Sending 'value' risks causing data races ... later accesses could race` | Region-based isolation sees you reuse a value after sending it | Stop reusing it after the send; make a copy to send; or make the type Sendable |
| `Actor-isolated property cannot be passed 'inout'` | `&actorProp` across isolation | Do the mutation inside the actor: add a method on the actor that mutates internally |
| `Conformance of 'M' to protocol 'P' crosses into main actor-isolated code` / protocol requirement isolation mismatch | `@MainActor` type conforming to a nonisolated protocol | Mark requirement implementations `nonisolated` (only touching Sendable state); Swift 6.2: `extension M: @MainActor P` (isolated conformance) when the protocol is only used on main |
| `Static property 'shared' is not concurrency-safe because it is nonisolated global shared mutable state` | `static var` singleton | `static let` of a Sendable/actor type; or annotate the global `@MainActor`; last resort `nonisolated(unsafe)` with a real external lock |
| `'deinit' cannot access main-actor-isolated property` | Cleanup touching isolated state | Move cleanup into an explicit `func shutdown()`; or `isolated deinit` (Swift 6.1+) |

**Escape hatches** - `@unchecked Sendable`, `nonisolated(unsafe)`, `@preconcurrency import` - are for wrapping audited legacy/third-party code only. `@preconcurrency import SomeSDK` is the right tool for un-annotated vendor SDKs; the other two must come with a comment proving the manual synchronization.

## Actors done right

```swift
actor ImageCache {
    private var cache: [URL: Image] = [:]
    private var inFlight: [URL: Task<Image, Error>] = [:]

    func image(for url: URL) async throws -> Image {
        if let hit = cache[url] { return hit }
        if let running = inFlight[url] { return try await running.value }  // coalesce
        let task = Task { try await Self.load(url) }
        inFlight[url] = task
        defer { inFlight[url] = nil }
        let image = try await task.value
        cache[url] = image
        return image
    }

    private static func load(_ url: URL) async throws -> Image { ... }
}
```

- **Actors are re-entrant**: state can change across every `await` inside an actor method. Re-read state after each `await`; the in-flight-task pattern above exists because two callers can interleave.
- Don't make an actor for UI state - that's `@MainActor`'s job. An `actor` view model forces `await` on every property read from `body`, which doesn't compile usefully.
- Keep actor methods small and synchronous where possible; hop in, mutate, hop out.

## Structured concurrency in views and models

```swift
// Parallel independent fetches - async let, not sequential awaits:
func loadDashboard() async throws -> Dashboard {
    async let user = api.fetch(User.self, from: .me)
    async let orders = api.fetch([Order].self, from: .orders)
    return try await Dashboard(user: user, orders: orders)
}

// Dynamic fan-out with bounded results:
let thumbnails = try await withThrowingTaskGroup(of: (Int, Image).self) { group in
    for (i, url) in urls.enumerated() {
        group.addTask { (i, try await cache.image(for: url)) }
    }
    var result = [Image?](repeating: nil, count: urls.count)
    for try await (i, image) in group { result[i] = image }
    return result.compactMap { $0 }
}
```

- Prefer `.task {}` / `.task(id:)` on views: auto-cancelled on disappear. `Task {}` in `onAppear` outlives the view.
- Cancellation is cooperative: long loops must `try Task.checkCancellation()` or check `Task.isCancelled`; URLSession checks for you.
- `Task.detached` almost never - it drops priority, task-locals, and actor context. `@concurrent` (6.2) or a plain `Task {}` from a nonisolated context covers "get off the main actor".
- Bridge callback APIs once, at the edge: `withCheckedThrowingContinuation` - resume exactly once, and use `withTaskCancellationHandler` if the underlying API supports cancel.

## MainActor + SwiftUI facts

- `View.body` is `@MainActor`. So are `@Observable @MainActor` model methods you call from it - no `await` needed from body's context for synchronous members.
- After `await` inside a `@MainActor` function you are *back on the main actor* - no `DispatchQueue.main.async` ever. Its presence in new code is a smell.
- `onReceive`/delegate callbacks from nonisolated contexts: wrap the hop with `Task { @MainActor in ... }` or, better, isolate the delegate type.
- SwiftUI previews, `#Preview` bodies, and Swift Testing `@Test` functions can be isolated with `@MainActor` when they touch main-actor state - annotate the test, not the assertions.
