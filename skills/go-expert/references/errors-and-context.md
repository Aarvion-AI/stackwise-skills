# Errors and Context (Go 1.23+)

## Wrapping: `%w` vs `%v`

`fmt.Errorf` with `%w` builds a chain that `errors.Is`/`errors.As` can walk.
The choice between `%w` and `%v` is an API decision, not a style one:

```go
// %w: callers may branch on the underlying error - it is part of your contract.
return fmt.Errorf("load config %q: %w", path, err)

// %v: deliberately sever the chain - the underlying error is an implementation
// detail you do not want callers depending on (e.g., which driver you use).
return fmt.Errorf("load config %q: %v", path, err)
```

Wrap **once per level** with the operation and key identifiers. Do not restate
what the callee already said - chains like `"get user: get user: query user:"`
mean intermediate layers added no information; those should `return err` bare.

```go
// Good message discipline: each layer adds only its own context.
// Result: "sync account acct_9: fetch balance: Get "https://...": context deadline exceeded"
```

Messages: lowercase, no trailing punctuation, no "failed to"/"error:" prefixes
(the chain formatting supplies the narrative).

## Sentinel errors vs typed errors

**Sentinel** (`errors.New` at package level) when callers only need identity:

```go
package store

var (
    ErrNotFound = errors.New("not found")
    ErrConflict = errors.New("conflict")
)

// caller:
if errors.Is(err, store.ErrNotFound) { ... }
```

**Typed** (struct implementing `error`) when callers need fields:

```go
type ValidationError struct {
    Field  string
    Reason string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("field %s: %s", e.Field, e.Reason)
}

// caller:
var ve *ValidationError
if errors.As(err, &ve) {
    http.Error(w, ve.Error(), http.StatusUnprocessableEntity)
}
```

Decision rule: start with a sentinel; introduce a type only when a caller
demonstrably needs the fields. Do not export error types "just in case" -
every exported error is API surface you must keep compatible.

**Always** `errors.Is(err, target)`, never `err == target` (breaks under
wrapping) and never `strings.Contains(err.Error(), ...)` (breaks under any
message edit).

## Translating errors at boundaries

Driver/library errors must not leak past the layer that produced them:

```go
func (s *Store) GetUser(ctx context.Context, id string) (User, error) {
    u, err := s.q.GetUser(ctx, id)
    if errors.Is(err, pgx.ErrNoRows) {
        return User{}, fmt.Errorf("user %s: %w", id, ErrNotFound) // yours, not pgx's
    }
    if err != nil {
        return User{}, fmt.Errorf("get user %s: %w", id, err)
    }
    return u, nil
}
```

HTTP handlers are the last boundary: map domain errors to status codes there,
log the full chain, and return a generic body for 5xx - `err.Error()` in a 500
response leaks table names and hosts.

## errors.Join

`errors.Join` aggregates independent failures; `errors.Is/As` match any branch:

```go
func (c *Config) Validate() error {
    var errs []error
    if c.Port == 0 {
        errs = append(errs, errors.New("port required"))
    }
    if c.DSN == "" {
        errs = append(errs, errors.New("dsn required"))
    }
    return errors.Join(errs...) // nil when errs is empty - no length check needed
}
```

Use it for validation and multi-resource cleanup (`errors.Join(closeA(), closeB())`).
Do not use it where callers need to know *which* one failed first - that is
ordinary sequential returns.

## Handle once

An error is either handled (logged, translated, recovered) **or** returned -
never both. Log-and-return produces duplicate log lines at every level and is
the most common review finding in Go services. The layer that stops the
propagation (usually the HTTP handler or the worker loop) logs.

## Context propagation

Rules, in order of how often they are violated:

1. `ctx context.Context` is the **first parameter** of any function that does
   I/O, blocks, or calls something that does. Name it `ctx`.
2. **Never store a context in a struct.** A struct-held ctx outlives the call
   that created it and detaches cancellation from the caller. (The stdlib's
   `http.Request` is the grandfathered exception.) If a type needs a context
   at method-call time, the method takes one.
3. Never pass `nil`; use `context.Background()` at the top of `main`/tests and
   `context.TODO()` only as a marked migration placeholder.
4. `context.Value` carries request-scoped telemetry (request ID, principal,
   trace span) with unexported key types - never function parameters in disguise.

```go
// WRONG - cancellation silently broken, vet's containedctx linter flags it:
type Worker struct{ ctx context.Context }

// RIGHT:
func (w *Worker) Run(ctx context.Context) error { ... }
```

## Cancellation and deadlines

Every `WithCancel`/`WithTimeout`/`WithDeadline` must have its cancel called -
`defer cancel()` immediately, even when the ctx "obviously" expires. Missing
defers leak timer goroutines until the parent dies (`go vet` catches most).

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()

row, err := pool.Query(ctx, ...) // pgx, net/http, exec all honor ctx natively
```

Long loops must check for cancellation; nothing preempts a busy goroutine:

```go
for _, item := range items {
    if err := ctx.Err(); err != nil {
        return fmt.Errorf("processing cancelled: %w", err)
    }
    process(item)
}
```

Distinguish the two terminal causes when it matters:

```go
if errors.Is(err, context.DeadlineExceeded) { /* timeout - maybe retry */ }
if errors.Is(err, context.Canceled)         { /* caller gave up - do not retry */ }
```

### Cancellation cause (Go 1.21+)

`WithCancelCause`/`WithTimeoutCause` attach *why*; read it with `context.Cause`:

```go
ctx, cancel := context.WithCancelCause(parent)
// elsewhere:
cancel(fmt.Errorf("upstream feed closed: %w", err))
// consumer:
<-ctx.Done()
log.Error("worker stopped", "cause", context.Cause(ctx)) // the real reason, not just "context canceled"
```

### Detaching values from cancellation

For work that must outlive the request (audit log write, cache fill) but keep
its trace/request values, use `context.WithoutCancel(ctx)` (Go 1.21+) - do not
reach for `context.Background()`, which drops the telemetry values too:

```go
go func() {
    ctx := context.WithoutCancel(reqCtx)          // values kept, cancellation dropped
    ctx, cancel := context.WithTimeout(ctx, 30*time.Second) // always re-bound it
    defer cancel()
    if err := audit.Write(ctx, entry); err != nil {
        slog.ErrorContext(ctx, "audit write", "err", err)
    }
}()
```

### AfterFunc for cleanup

`context.AfterFunc(ctx, f)` runs `f` in its own goroutine once ctx is done -
the clean way to tie non-context-aware resources to cancellation:

```go
stop := context.AfterFunc(ctx, func() { conn.Close() }) // unblocks a stuck Read
defer stop()
```
