# SwiftData Persistence: @Model, @Query, Migration, and the Core Data Boundary

SwiftData (iOS 17+, materially better on iOS 18+) is the default persistence choice for new SwiftUI apps. It compiles your models into a schema, gives views live queries, and syncs with CloudKit. Know where its edges are - the last section covers when Core Data is still the right call.

## Models

```swift
import SwiftData

@Model
final class Trip {
    #Unique<Trip>([\.code])                     // iOS 18: compound uniqueness constraints
    #Index<Trip>([\.startDate], [\.name])       // iOS 18: real indexes for query speed

    var name: String
    var code: String
    var startDate: Date
    var notes: String = ""                      // defaults make lightweight migration possible

    @Relationship(deleteRule: .cascade, inverse: \Stop.trip)
    var stops: [Stop] = []

    @Attribute(.externalStorage) var coverImage: Data?
    @Transient var isSelected = false           // never persisted; must have a default

    init(name: String, code: String, startDate: Date) {
        self.name = name; self.code = code; self.startDate = startDate
    }
}

@Model
final class Stop {
    var city: String
    var trip: Trip?                             // inverse; optional to-one
    init(city: String) { self.city = city }
}
```

- `@Model` classes are **not Sendable** - they are bound to the `ModelContext` that loaded them. Pass `PersistentIdentifier`s across actors, never model instances.
- Declare the inverse on **one** side with `@Relationship(inverse:)`; SwiftData infers the pair. Delete rules: `.cascade` for owned children, `.nullify` (default) for references.
- Every new property added after release needs a default value (or be optional) to keep lightweight migration working.

## Container and context setup

```swift
@main struct TravelApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
            .modelContainer(for: Trip.self)      // Stop is pulled in via the relationship
    }
}

// Explicit configuration (in-memory for tests/previews, CloudKit, custom URL):
let config = ModelConfiguration(isStoredInMemoryOnly: true)
let container = try ModelContainer(for: Trip.self, configurations: config)
```

- Views get the main-actor context via `@Environment(\.modelContext) private var context`.
- Insert/delete through the context: `context.insert(trip)`, `context.delete(trip)`. Autosave is on by default in app contexts; call `try context.save()` explicitly at transaction boundaries you care about (tests have autosave off).
- Background work: `@ModelActor` gives an actor with its own context bound to the actor's executor:

```swift
@ModelActor
actor Importer {
    func importTrips(from data: Data) throws {
        let dtos = try JSONDecoder().decode([TripDTO].self, from: data)
        for dto in dtos { modelContext.insert(Trip(dto)) }
        try modelContext.save()
    }
}
let importer = Importer(modelContainer: container)   // pass the container, not a context
```

## Queries in views

```swift
struct TripList: View {
    @Query(sort: \Trip.startDate, order: .reverse) private var trips: [Trip]

    // Dynamic predicate: inject via init
    init(searchText: String) {
        let predicate = #Predicate<Trip> {
            searchText.isEmpty || $0.name.localizedStandardContains(searchText)
        }
        _trips = Query(filter: predicate, sort: [SortDescriptor(\.startDate, order: .reverse)])
    }

    var body: some View {
        List(trips) { trip in TripRow(trip: trip) }
    }
}
```

- `@Query` live-updates on any context change - no manual refetching, no `onAppear` fetch.
- `#Predicate` is compiled, not a closure: only a supported subset of Swift works inside it (comparisons, `contains`, `localizedStandardContains`, `?? `, boolean logic, keypaths). No function calls, no captures of non-Sendable values, no computed model properties. Complex logic → fetch broader and filter in memory, or denormalize a stored property.
- Imperative fetches (models, view models, `@ModelActor`): `FetchDescriptor`:

```swift
var descriptor = FetchDescriptor<Trip>(predicate: #Predicate { $0.stops.count > 3 },
                                       sortBy: [SortDescriptor(\.name)])
descriptor.fetchLimit = 50
descriptor.propertiesToFetch = [\.name, \.startDate]
let results = try context.fetch(descriptor)
let n = try context.fetchCount(FetchDescriptor<Trip>())   // count without materializing
```

## Migration

Lightweight changes (add property with default, add model, rename via `@Attribute(originalName:)`) migrate automatically. Anything structural needs a versioned schema:

```swift
enum TripSchemaV1: VersionedSchema {
    static var versionIdentifier = Schema.Version(1, 0, 0)
    static var models: [any PersistentModel.Type] { [Trip.self, Stop.self] }
}
enum TripSchemaV2: VersionedSchema { /* version 2 models */
    static var versionIdentifier = Schema.Version(2, 0, 0)
    static var models: [any PersistentModel.Type] { [Trip.self, Stop.self] }
}

enum TripMigrationPlan: SchemaMigrationPlan {
    static var schemas: [any VersionedSchema.Type] { [TripSchemaV1.self, TripSchemaV2.self] }
    static var stages: [MigrationStage] {
        [.custom(fromVersion: TripSchemaV1.self, toVersion: TripSchemaV2.self,
                 willMigrate: { context in /* dedupe rows before a new #Unique */ try context.save() },
                 didMigrate: nil)]
    }
}

let container = try ModelContainer(for: Trip.self, migrationPlan: TripMigrationPlan.self)
```

Ship the migration plan from v1 onward in spirit: once real data exists, every schema change gets a stage. Test migrations by keeping a fixture store file from each shipped version.

## CloudKit sync

`ModelConfiguration(cloudKitDatabase: .automatic)` (plus the iCloud + push capabilities) syncs the private database. CloudKit constraints tighten the schema:

- No `#Unique` constraints; all relationships must be optional or have defaults; all properties need defaults or optionality.
- Dedupe on conflict yourself (fetch-and-merge on launch/foreground).
- No public/shared database support in SwiftData - sharing scenarios are a Core Data + `NSPersistentCloudKitContainer` reason.

## Previews and tests

```swift
// iOS 18 PreviewModifier caches one container for all previews:
struct SampleData: PreviewModifier {
    static func makeSharedContext() async throws -> ModelContainer {
        let container = try ModelContainer(for: Trip.self,
            configurations: ModelConfiguration(isStoredInMemoryOnly: true))
        container.mainContext.insert(Trip(name: "Kyoto", code: "KYO", startDate: .now))
        return container
    }
    func body(content: Content, context: ModelContainer) -> some View {
        content.modelContainer(context)
    }
}
#Preview(traits: .modifier(SampleData())) { TripList(searchText: "") }
```

In Swift Testing, build a fresh in-memory container per test (`@Suite` init or a helper); never share a container across tests - autosave-off contexts make assertions deterministic.

## SwiftData vs Core Data - decide honestly

Choose **SwiftData** when: new app, iOS 17/18+ floor, SwiftUI-first UI, private-DB CloudKit at most, schema of moderate complexity. You get `@Query` live views, macro-checked models, and versioned migrations with far less code.

Choose **Core Data** when any of these hold:

- Existing Core Data stack with nontrivial `NSManagedObjectModel` features: abstract entities, derived attributes, ordered relationships, fetched properties, batch insert/update/delete at scale.
- CloudKit **shared or public** database, or record-zone-level sharing.
- Sectioned fetches with change tracking (`NSFetchedResultsController` semantics) beyond what `@Query` + `Dictionary(grouping:)` handles at your data size.
- Deployment below iOS 17, or a large multi-target codebase already fluent in Core Data.

The two interoperate: SwiftData is built on Core Data, and one SQLite store can be opened by both (matching schemas) during an incremental migration - keep a single writer at a time.

## Common mistakes

- Fetching in `onAppear` into `@State` instead of `@Query` - stale lists, missed updates.
- Passing `@Model` objects to background tasks/actors - crashes or silent races. Pass `persistentModelID`, re-fetch with `context.model(for:)` in the destination context.
- Writing `#Predicate` with unsupported expressions (computed properties, method calls) - compiles into runtime errors or silent full scans; keep predicates to stored-property comparisons.
- Forgetting defaults on new properties → migration crash on upgrade, only reproducible on real upgraded installs.
- Using `.modelContainer(for:)` in the app *and* constructing another container in a model layer - two stacks, two truths. One container, injected everywhere (previews/tests get in-memory ones).
