---
name: go-expert
description: Use when writing or reviewing Go backend services - go.mod, *.go files, net/http handlers, pgx/sqlc database code, goroutines, context.Context plumbing, or failing `go test` runs. Builds HTTP APIs on the Go 1.22+ stdlib router, fixes error-wrapping and context-cancellation bugs, designs leak-free goroutine lifecycles with errgroup, and wires pgx/sqlc data layers. Invoke for HTTP routing, error handling, concurrency, database access, slog logging, project layout, or table-driven tests.
license: MIT
metadata:
  version: "0.1.0"
  category: backend
  frameworks: "Go 1.23+ (patterns current through Go 1.25), net/http 1.22+ ServeMux, pgx v5, sqlc, errgroup, log/slog, testcontainers-go"
  triggers: Go, golang, go.mod, goroutine, channel, net/http, ServeMux, chi, echo, errgroup, context, pgx, sqlc, slog, go vet, golangci-lint, go test, race detector, table-driven tests, testcontainers
  related: react-expert, vue-expert, terraform-expert, playwright-expert
---

# Go Expert

Senior Go backend engineer for Go 1.23+ services: stdlib-first HTTP, disciplined error and context handling, leak-free concurrency, and pgx/sqlc data access.

## When to Use This Skill

- Build or extend an HTTP API/service in Go (handlers, routing, middleware, graceful shutdown)
- Fix error handling: wrapping with `%w`, `errors.Is`/`errors.As`, sentinel vs typed errors
- Debug or design concurrency: goroutine leaks, `errgroup`, channels, worker pools, cancellation
- Add or refactor database access with pgx v5 and sqlc (transactions, pooling, migrations)
- Write table-driven tests, integration tests with testcontainers, or fix `-race` failures
- Review Go code for idiom violations, over-abstraction, or misuse of generics/interfaces
- Lay out a new Go service (`cmd/`, `internal/`, module structure)

## Core Workflow

1. **Analyze** - Read `go.mod` for the Go version and existing dependencies before adding any. Check for an existing router, logger, and DB layer and match them - do not introduce chi/zap/GORM into a stdlib/slog/pgx codebase. Look for `internal/` structure and follow the established package boundaries.
2. **Implement** - Write the change following the patterns below and in the loaded references. Stdlib first: net/http ServeMux, `log/slog`, `database/sql` semantics via pgx. Accept interfaces, return concrete types. Every function that does I/O takes `ctx context.Context` as its first parameter.
3. **Verify (vet + lint)** - Run `go vet ./...`, then `golangci-lint run ./...` if the repo has a `.golangci.yml` (or golangci-lint is installed). If either reports problems, fix all reported issues and re-run until clean before proceeding. Do not suppress findings with `//nolint` unless there is a documented false positive.
4. **Test** - Write or update table-driven tests for the change, then run `go test -race ./...`. If any test fails or the race detector reports a data race, fix all reported issues and re-run until clean. Never delete or skip a failing test to get green; fix the code or the test's expectations deliberately.
5. **Prove it works** - Build and run the actual entrypoint (`go run ./cmd/<service>` or the repo's make target) and exercise the changed behavior: `curl` the new endpoint, run the migration, or trigger the job. For services, confirm graceful shutdown works (Ctrl-C returns promptly, no goroutines hang). If the run fails, fix and re-run until the observed behavior matches the requirement.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| HTTP services | `references/http-services.md` | Handlers, routing, middleware, ServeMux vs chi/echo, graceful shutdown, timeouts, JSON APIs |
| Errors & context | `references/errors-and-context.md` | Error wrapping, sentinel/typed errors, `errors.Is/As`, context propagation, cancellation, deadlines |
| Concurrency | `references/concurrency.md` | Goroutines, channels, errgroup, worker pools, goroutine leaks, sync primitives, data races |
| Database | `references/database-pgx-sqlc.md` | Postgres access, pgx v5 pools, sqlc codegen, transactions, migrations, why not GORM |
| Testing | `references/testing.md` | Table-driven tests, subtests, testcontainers, httptest, race detector, benchmarks, fuzzing |

## Key Patterns

**Go 1.22+ ServeMux - method + wildcard routing, no framework needed:**

```go
mux := http.NewServeMux()
mux.HandleFunc("GET /api/orders/{id}", h.getOrder)   // method-scoped since 1.22
mux.HandleFunc("POST /api/orders", h.createOrder)
mux.HandleFunc("GET /healthz", h.health)

func (h *Handler) getOrder(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id") // wildcard extraction is stdlib now
    order, err := h.store.GetOrder(r.Context(), id)
    if errors.Is(err, store.ErrNotFound) {
        http.Error(w, "order not found", http.StatusNotFound)
        return
    }
    if err != nil {
        h.log.ErrorContext(r.Context(), "get order", "id", id, "err", err)
        http.Error(w, "internal error", http.StatusInternalServerError)
        return
    }
    writeJSON(w, http.StatusOK, order)
}
```

**Error wrapping - `%w` once per level, decide with `errors.Is/As`:**

```go
var ErrNotFound = errors.New("not found") // sentinel: caller branches on identity

func (s *Store) GetOrder(ctx context.Context, id string) (Order, error) {
    row, err := s.q.GetOrder(ctx, id)
    if errors.Is(err, pgx.ErrNoRows) {
        return Order{}, fmt.Errorf("order %s: %w", id, ErrNotFound) // translate driver error at the boundary
    }
    if err != nil {
        return Order{}, fmt.Errorf("get order %s: %w", id, err)
    }
    return fromRow(row), nil
}
```

**errgroup - bounded, cancellable, leak-free fan-out:**

```go
g, ctx := errgroup.WithContext(ctx) // ctx cancels when any task errors
g.SetLimit(8)                       // bound concurrency; never spawn unbounded goroutines
for _, id := range ids {
    g.Go(func() error {             // Go 1.22+: loop var is per-iteration, no capture bug
        return process(ctx, id)     // must honor ctx or the group can't stop it
    })
}
if err := g.Wait(); err != nil {    // first error; all goroutines finished
    return fmt.Errorf("process batch: %w", err)
}
```

**slog - structured, context-aware logging (not fmt.Printf, not logrus):**

```go
log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
slog.SetDefault(log)
log.InfoContext(ctx, "order created", "order_id", o.ID, "user_id", o.UserID, "amount_cents", o.Amount)
```

## Common Mistakes

- **Reaching for chi/echo/gin by default.** Since Go 1.22, `http.ServeMux` handles method routing and path wildcards (`GET /users/{id}`, `r.PathValue`). Use a framework only for real needs: route groups with shared middleware stacks, path regexes, or an existing codebase already using one. Never mix two routers.
- **Storing `context.Context` in a struct field.** Context flows through call chains as the first function parameter, full stop. A struct-held ctx outlives its request and silently breaks cancellation. The only sanctioned exception is `http.Request`, which predates the rule.
- **Wrapping every error with `%w` reflexively - or with none.** Wrap with `%w` when callers may need to branch (`errors.Is/As`) or when adding operation context; use `%v` (or a new error) at boundaries where you want to *stop* callers depending on internals (e.g., hide `pgx.ErrNoRows` behind your own `ErrNotFound`). `err.Error() == "..."` string comparison is always wrong.
- **Fire-and-forget goroutines.** Every `go` statement needs an answer to "how does this goroutine stop, and who sees its error?" Use `errgroup.WithContext` for request-scoped work and an explicit shutdown signal (`ctx.Done()`) + `Wait` for background workers. A goroutine blocked forever on an unread channel is a leak the race detector will not find.
- **Generics where an interface (or nothing) belongs.** Use type parameters for data structures and slice/map helpers with two-plus concrete instantiations. Do not write `func Process[T any](...)` when `T` is only ever one type, constrain to a one-method interface (just take the interface), or build generic "repository" abstractions over sqlc.
- **ORMs (GORM/ent) as the default.** For Postgres services, use pgx v5 + sqlc: SQL you can read and EXPLAIN, compile-time-checked query results, no N+1 surprises. Reach for ent only when you genuinely need a graph schema with typed traversals.
- **Premature `pkg/` and giant `util` packages.** Start with `cmd/<service>/main.go` (wiring only) and `internal/<domain>` packages named by what they provide (`billing`, `store`), not by kind (`models`, `helpers`, `utils`). `pkg/` earns its place only when an external module actually imports the code.
- **`http.ListenAndServe(":8080", mux)` in production.** Zero timeouts means slow-loris and leaked connections. Configure `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, `IdleTimeout`, and shut down with `srv.Shutdown(ctx)` on SIGTERM.
