# HTTP Services (Go 1.23+, stdlib-first)

## Routing with the 1.22+ ServeMux

Method routing and path wildcards are stdlib. Do not add chi/echo/gin for these.

```go
mux := http.NewServeMux()

mux.HandleFunc("GET /api/orders", h.listOrders)
mux.HandleFunc("POST /api/orders", h.createOrder)
mux.HandleFunc("GET /api/orders/{id}", h.getOrder)
mux.HandleFunc("DELETE /api/orders/{id}", h.deleteOrder)
mux.HandleFunc("GET /api/files/{path...}", h.getFile) // {path...} matches rest of URL
mux.HandleFunc("GET /{$}", h.home)                    // {$} = exactly "/", not a prefix match
mux.HandleFunc("GET /healthz", h.health)
```

Rules that matter:

- `r.PathValue("id")` extracts wildcard segments.
- A pattern without a method matches all methods. `GET` also matches `HEAD`.
- Precedence is "most specific wins", independent of registration order:
  `GET /orders/latest` beats `GET /orders/{id}`. Two patterns that overlap with
  no clear winner (`GET /a/{x}/c` vs `GET /a/b/{y}`) panic at registration -
  that panic is a design smell, restructure the routes.
- Unmatched method on a matched path returns 405 with a correct `Allow` header
  automatically; unmatched path returns 404. You get this for free - do not
  hand-roll method switches inside handlers anymore.
- Trailing-slash patterns (`/static/`) are subtree matches and redirect
  `/static` → `/static/`; use `{$}` when you do not want subtree behavior.

## When you actually need chi (or echo)

Reach for a router package only when the task requires:

- **Route groups with per-group middleware stacks** (`/api` authenticated,
  `/admin` authenticated + RBAC, `/public` neither) and the service has enough
  routes that hand-composing middleware per route is error-prone.
- **Pattern features ServeMux lacks**: regex constraints on segments, or
  mounting sub-routers from other packages.
- **An existing codebase already on chi/echo** - consistency beats purity.

chi is preferred over echo/gin for new code because its handlers are plain
`http.HandlerFunc` - no framework context type infects your signatures, and
migration back to stdlib stays trivial. Never run two routers in one service.

## Handler and server construction

Handlers hang off a struct holding dependencies. No package-level state, no
`init()` wiring, no global DB handles.

```go
type Handler struct {
    store *store.Store
    log   *slog.Logger
}

func New(store *store.Store, log *slog.Logger) http.Handler {
    h := &Handler{store: store, log: log}
    mux := http.NewServeMux()
    mux.HandleFunc("GET /api/orders/{id}", h.getOrder)
    mux.HandleFunc("POST /api/orders", h.createOrder)
    var handler http.Handler = mux
    handler = withRequestID(handler)   // outermost runs first
    handler = withRecover(handler, log)
    return handler
}
```

Production server - never bare `http.ListenAndServe`:

```go
srv := &http.Server{
    Addr:              ":8080",
    Handler:           handler,
    ReadHeaderTimeout: 5 * time.Second,  // slow-loris defense
    ReadTimeout:       10 * time.Second,
    WriteTimeout:      30 * time.Second, // must exceed slowest handler
    IdleTimeout:       120 * time.Second,
}
```

## Graceful shutdown

```go
func run(ctx context.Context, srv *http.Server, log *slog.Logger) error {
    ctx, stop := signal.NotifyContext(ctx, os.Interrupt, syscall.SIGTERM)
    defer stop()

    errCh := make(chan error, 1)
    go func() {
        if err := srv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
            errCh <- err
        }
    }()

    select {
    case err := <-errCh:
        return fmt.Errorf("serve: %w", err)
    case <-ctx.Done():
        shutCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
        defer cancel()
        if err := srv.Shutdown(shutCtx); err != nil { // drains in-flight requests
            return fmt.Errorf("shutdown: %w", err)
        }
        log.Info("server stopped cleanly")
        return nil
    }
}
```

`Shutdown` uses a *fresh* context - the signal context is already cancelled, so
reusing it would abort in-flight requests instantly.

## JSON request/response

One pair of helpers; no framework "bind" magic.

```go
func writeJSON(w http.ResponseWriter, status int, v any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    if err := json.NewEncoder(w).Encode(v); err != nil {
        // headers already sent; log only
        slog.Error("encode response", "err", err)
    }
}

func readJSON(w http.ResponseWriter, r *http.Request, dst any) error {
    r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // cap request bodies (1 MiB)
    dec := json.NewDecoder(r.Body)
    dec.DisallowUnknownFields() // reject typos in client payloads
    if err := dec.Decode(dst); err != nil {
        return fmt.Errorf("decode body: %w", err)
    }
    if dec.More() {
        return errors.New("body must contain a single JSON object")
    }
    return nil
}
```

Handler shape - validate, call the domain, translate errors to status codes at
this boundary and nowhere deeper:

```go
func (h *Handler) createOrder(w http.ResponseWriter, r *http.Request) {
    var req createOrderRequest
    if err := readJSON(w, r, &req); err != nil {
        http.Error(w, err.Error(), http.StatusBadRequest)
        return
    }
    if err := req.validate(); err != nil {
        http.Error(w, err.Error(), http.StatusUnprocessableEntity)
        return
    }
    order, err := h.store.CreateOrder(r.Context(), req.toParams())
    switch {
    case errors.Is(err, store.ErrConflict):
        http.Error(w, "duplicate order", http.StatusConflict)
    case err != nil:
        h.log.ErrorContext(r.Context(), "create order", "err", err)
        http.Error(w, "internal error", http.StatusInternalServerError) // never leak err.Error() at 500
    default:
        writeJSON(w, http.StatusCreated, order)
    }
}
```

## Middleware

Plain `func(http.Handler) http.Handler`. Composition order: the last-applied
wrapper runs first.

```go
func withRecover(next http.Handler, log *slog.Logger) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        defer func() {
            if v := recover(); v != nil {
                log.ErrorContext(r.Context(), "panic", "value", v, "stack", string(debug.Stack()))
                http.Error(w, "internal error", http.StatusInternalServerError)
            }
        }()
        next.ServeHTTP(w, r)
    })
}

type ctxKey int

const requestIDKey ctxKey = 0 // unexported key type: collisions impossible

func withRequestID(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := r.Header.Get("X-Request-Id")
        if id == "" {
            id = rand.Text() // crypto/rand, Go 1.24+
        }
        ctx := context.WithValue(r.Context(), requestIDKey, id)
        w.Header().Set("X-Request-Id", id)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
```

Context values are for request-scoped *telemetry* (request ID, auth principal,
trace span) - never for passing business parameters a function signature
should carry.

## Timeouts on outbound calls

The default `http.Client` has no timeout. Always construct your own:

```go
client := &http.Client{Timeout: 10 * time.Second}
req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil) // ctx, always
```

`http.Get`/`http.Post` use the shared default client and ignore your context -
banned in service code.
