# Testing Go Services (Go 1.23+)

## Commands

```sh
go test -race ./...                        # the default gate - always -race
go test -race -run TestStore_GetOrder ./internal/store   # one test while iterating
go test -race -count=1 ./...               # bypass test cache after env changes
go test -short ./...                       # skip testcontainers-backed tests locally
go test -cover ./...                       # coverage signal, not a target to game
```

`-race` is non-negotiable for any code with goroutines - but it only flags
races the tests execute, so concurrent paths need concurrent tests.

## Table-driven tests

The default shape. Map keys as test names, `t.Run` subtests, `t.Parallel()`
when cases share no state:

```go
func TestParseAmount(t *testing.T) {
    t.Parallel()
    tests := map[string]struct {
        in      string
        want    int64
        wantErr error
    }{
        "dollars and cents": {in: "12.34", want: 1234},
        "zero":              {in: "0", want: 0},
        "negative rejected": {in: "-1", wantErr: ErrNegativeAmount},
        "junk rejected":     {in: "12.3.4", wantErr: ErrMalformed},
    }
    for name, tc := range tests {
        t.Run(name, func(t *testing.T) {
            t.Parallel()
            got, err := ParseAmount(tc.in)
            if tc.wantErr != nil {
                if !errors.Is(err, tc.wantErr) {
                    t.Fatalf("ParseAmount(%q) err = %v, want %v", tc.in, err, tc.wantErr)
                }
                return
            }
            if err != nil {
                t.Fatalf("ParseAmount(%q) unexpected err: %v", tc.in, err)
            }
            if got != tc.want {
                t.Errorf("ParseAmount(%q) = %d, want %d", tc.in, got, tc.want)
            }
        })
    }
}
```

- Assert errors with `errors.Is`/`errors.As`, never string equality on
  `err.Error()`.
- `t.Fatal` when continuing is meaningless; `t.Error` to report and keep
  checking other fields.
- Since Go 1.22 the loop variable needs no re-declaration for `t.Parallel()`
  closures.
- testify (`require`/`assert`) is fine if the repo already uses it; do not
  introduce it into a stdlib-assertion codebase for one test.

## Test doubles: small interfaces, hand-written fakes

Define the interface where it is **consumed**, sized to what the consumer
uses - then a fake is ten lines and no mock framework is needed:

```go
// in package api (consumer) - not in package store
type OrderStore interface {
    GetOrder(ctx context.Context, id string) (store.Order, error)
}

type fakeStore struct {
    orders map[string]store.Order
    err    error
}

func (f *fakeStore) GetOrder(_ context.Context, id string) (store.Order, error) {
    if f.err != nil {
        return store.Order{}, f.err
    }
    o, ok := f.orders[id]
    if !ok {
        return store.Order{}, store.ErrNotFound
    }
    return o, nil
}
```

Avoid gomock/mockery expectation scripts for simple dependencies - they test
call choreography instead of behavior and shatter on refactors.

## HTTP handler tests

`httptest` - no server socket needed for handler logic:

```go
func TestGetOrder_NotFound(t *testing.T) {
    h := api.New(&fakeStore{}, slog.New(slog.DiscardHandler)) // DiscardHandler: Go 1.24+
    req := httptest.NewRequest(http.MethodGet, "/api/orders/nope", nil)
    rec := httptest.NewRecorder()

    h.ServeHTTP(rec, req) // exercises real routing, incl. method matching

    if rec.Code != http.StatusNotFound {
        t.Fatalf("status = %d, want %d; body: %s", rec.Code, http.StatusNotFound, rec.Body)
    }
}
```

Go through the full `http.Handler` (mux + middleware), not the bare method -
routing patterns like `GET /api/orders/{id}` are behavior worth covering.
Use `httptest.NewServer(h)` only when a real client/URL is required (redirects,
cookies, real timeouts).

## Integration tests with testcontainers

Real Postgres beats a mocked store for store-layer tests:

```go
import (
    "github.com/testcontainers/testcontainers-go"
    tcpostgres "github.com/testcontainers/testcontainers-go/modules/postgres"
)

func newTestPool(t *testing.T) *pgxpool.Pool {
    t.Helper()
    if testing.Short() {
        t.Skip("integration test: skipped with -short")
    }
    ctx := t.Context() // Go 1.24+: per-test ctx, cancelled at cleanup

    pg, err := tcpostgres.Run(ctx, "postgres:17-alpine",
        tcpostgres.WithDatabase("app_test"),
        tcpostgres.BasicWaitStrategies(), // waits for "ready to accept connections"
    )
    if err != nil {
        t.Fatalf("start postgres: %v", err)
    }
    testcontainers.CleanupContainer(t, pg)

    dsn, err := pg.ConnectionString(ctx, "sslmode=disable")
    if err != nil {
        t.Fatalf("dsn: %v", err)
    }
    applyMigrations(t, dsn) // goose/migrate against the container

    pool, err := pgxpool.New(ctx, dsn)
    if err != nil {
        t.Fatalf("pool: %v", err)
    }
    t.Cleanup(pool.Close)
    return pool
}
```

- One container per **package** (start in `TestMain` or a `sync.OnceValue`),
  one transaction-or-truncate per test for isolation - per-test containers
  make the suite minutes long.
- Guard with `testing.Short()` so `go test -short ./...` stays Docker-free.
- Never hardcode ports; the container maps a random host port and
  `ConnectionString` reflects it.

## Concurrency tests

```go
func TestCache_ConcurrentAccess(t *testing.T) {
    c := NewCache()
    var wg sync.WaitGroup
    for i := 0; i < 50; i++ {
        wg.Go(func() { // Go 1.25; pre-1.25: wg.Add(1) + defer wg.Done()
            c.Set("k", 1)
            _ = c.Get("k")
        })
    }
    wg.Wait()
}
```

Pointless without `-race`. Add `go.uber.org/goleak` to catch leaked goroutines:

```go
func TestMain(m *testing.M) {
    goleak.VerifyTestMain(m)
}
```

For async assertions, poll with a deadline instead of `time.Sleep`:
`require.Eventually(t, cond, 2*time.Second, 10*time.Millisecond)` (testify) or
a hand-rolled ticker loop. Go 1.24+ also offers `testing/synctest` for
virtual-time tests of timer-heavy code - check `go.mod` before using it.

## Benchmarks and fuzzing

```go
func BenchmarkParseAmount(b *testing.B) {
    for b.Loop() { // Go 1.24+; replaces `for i := 0; i < b.N; i++` and auto-prevents dead-code elision
        _, _ = ParseAmount("1234.56")
    }
}

func FuzzParseAmount(f *testing.F) {
    f.Add("12.34")
    f.Fuzz(func(t *testing.T, s string) {
        v, err := ParseAmount(s)
        if err == nil && v < 0 { // invariant, not exact output
            t.Errorf("ParseAmount(%q) = %d; negatives must error", s, v)
        }
    })
}
```

Fuzz parsers and validators at trust boundaries; run `go test -fuzz=Fuzz -fuzztime=30s`
locally and commit any corpus files it discovers into `testdata/`.

## What not to do

- Do not test unexported helpers through contortions - test the exported
  behavior; unexported details should be free to change.
- Do not assert on log output or exact error strings; assert on returned
  errors and observable state.
- Do not use `time.Sleep` to "wait for" goroutines - flake factory.
- Do not chase 100% coverage through getters and generated code (`internal/db`
  from sqlc is generated - exclude it from coverage expectations).
- Do not let tests depend on execution order or shared package-level state;
  `go test -shuffle=on ./...` in CI exposes these.
