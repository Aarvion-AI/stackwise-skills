# Concurrency: Goroutine Lifecycle, errgroup, Leak Prevention

## The lifecycle rule

Before writing `go func`, answer three questions in code, not intent:

1. **How does it stop?** (ctx cancellation, channel close, bounded work)
2. **Who waits for it to finish?** (`errgroup.Wait`, `sync.WaitGroup`, join channel)
3. **Where does its error go?** (group error, error channel, logged at the loop)

A goroutine missing any answer is a leak or a silent failure. The race
detector does **not** find leaks - a goroutine parked forever on an unread
channel is invisible until memory or file descriptors run out. Use
`goleak.VerifyTestMain` (uber-go/goleak) in tests to catch them.

## errgroup - the default for request-scoped fan-out

```go
import "golang.org/x/sync/errgroup"

func fetchAll(ctx context.Context, ids []string) (map[string]Item, error) {
    g, ctx := errgroup.WithContext(ctx) // derived ctx cancels on first error
    g.SetLimit(10)                      // ALWAYS bound; len(ids) may be huge

    var mu sync.Mutex
    out := make(map[string]Item, len(ids))

    for _, id := range ids {
        g.Go(func() error { // Go 1.22+: loop var is fresh per iteration
            item, err := fetch(ctx, id) // must take ctx or cancellation is theater
            if err != nil {
                return fmt.Errorf("fetch %s: %w", id, err)
            }
            mu.Lock()
            out[id] = item
            mu.Unlock()
            return nil
        })
    }
    if err := g.Wait(); err != nil { // returns first error, after ALL finish
        return nil, err
    }
    return out, nil
}
```

Notes LLMs get wrong:

- `g.Wait()` returns only the **first** error; later ones are dropped. Need
  all of them? Collect into a mutex-guarded slice and `errors.Join` after Wait.
- `g.SetLimit(n)` must be called before any `g.Go`. `g.Go` blocks when the
  limit is reached (`g.TryGo` does not).
- The `ctx` returned by `WithContext` is cancelled after `Wait` returns -
  never use it for work that outlives the group.
- Writing to a shared map inside `g.Go` without a mutex is a data race even
  when keys are distinct. Alternative: pre-size a results slice and have
  goroutine *i* write only `out[i]` - disjoint indices need no lock.

## Background workers - stop via ctx, wait via Wait

```go
type Poller struct {
    interval time.Duration
    store    *store.Store
    log      *slog.Logger
}

func (p *Poller) Run(ctx context.Context) error { // caller owns the goroutine:
    t := time.NewTicker(p.interval)               //   g.Go(func() error { return p.Run(ctx) })
    defer t.Stop()
    for {
        select {
        case <-ctx.Done():
            return ctx.Err() // clean, prompt exit on shutdown
        case <-t.C:
            if err := p.pollOnce(ctx); err != nil {
                p.log.ErrorContext(ctx, "poll", "err", err) // log and continue; only fatal errors return
            }
        }
    }
}
```

Run the HTTP server and workers under one group in `main` so any fatal error
or SIGTERM stops everything:

```go
g, ctx := errgroup.WithContext(ctx)
g.Go(func() error { return runServer(ctx, srv) })
g.Go(func() error { return poller.Run(ctx) })
if err := g.Wait(); err != nil && !errors.Is(err, context.Canceled) {
    return err
}
```

## Channel discipline

- **Sender closes; receivers never do.** Close only to signal "no more values"
  to a ranging receiver. Not every channel needs closing - abandoning one is
  fine once no goroutine is blocked on it.
- `for v := range ch` exits when the channel is closed and drained - the
  correct consumer loop. `v, ok := <-ch` only when you must distinguish
  closed-vs-zero.
- Unbuffered = synchronization point; buffered = decoupling with a **measured**
  capacity. A buffer is not backpressure handling - a full buffer still blocks.
- Every send/receive that can block during shutdown must sit in a `select`
  with `<-ctx.Done()`:

```go
select {
case results <- r:
case <-ctx.Done():
    return ctx.Err() // without this arm, cancellation leaks this goroutine
}
```

## Worker pool (when errgroup's SetLimit isn't enough)

Only when workers hold per-worker state (a connection, a batch buffer):

```go
func pool(ctx context.Context, jobs <-chan Job, workers int) error {
    g, ctx := errgroup.WithContext(ctx)
    for i := 0; i < workers; i++ {
        g.Go(func() error {
            for {
                select {
                case <-ctx.Done():
                    return ctx.Err()
                case job, ok := <-jobs:
                    if !ok {
                        return nil // producer closed jobs: clean drain
                    }
                    if err := handle(ctx, job); err != nil {
                        return fmt.Errorf("job %s: %w", job.ID, err)
                    }
                }
            }
        })
    }
    return g.Wait()
}
```

The producer must also select on `ctx.Done()` while sending, then `close(jobs)`.

## sync primitives - when channels are the wrong tool

- **`sync.Mutex`** for protecting state; channels for transferring ownership.
  Guarding a map with a channel-based "manager goroutine" where a 5-line
  mutex would do is over-engineering.
- **`sync.RWMutex`** only with measured read-heavy contention; it is slower
  than `Mutex` uncontended.
- **`sync.Once` / `sync.OnceValue`** for lazy init. Prefer
  `sync.OnceValue(f)` (Go 1.21+) - it returns a typed getter and caches the
  result: `getConfig := sync.OnceValue(loadConfig)`.
- **`sync.WaitGroup`**: Go 1.25 added `wg.Go(f)` which does Add/done/go in one
  call - use it over the manual `wg.Add(1); go func(){ defer wg.Done() ... }`
  dance. WaitGroup carries no errors and no cancellation; the moment you need
  either, that is errgroup.
- **`atomic.Int64` / `atomic.Bool` / `atomic.Pointer[T]`**: counters and flags.
  Never mix atomic and plain access to the same variable.
- **`sync.Map`** is for append-mostly caches with disjoint key sets; a plain
  `map` + `Mutex` is right for everything else.

## Data races

Run `go test -race ./...` on every change; the detector only flags races the
test actually executes, so tests must exercise concurrent paths.

- A race on a `bool`/`int` is still undefined behavior - "it's just a flag"
  is not a defense; use `atomic.Bool`.
- `t.Parallel()` subtests sharing a captured variable is a classic
  false-alarm-looking *real* race - give each subtest its own state.
- Since Go 1.22, `for` loop variables are per-iteration: the historical
  `id := id` shadow line is dead weight in new code - delete it, but do not
  "fix" old code running on pre-1.22 toolchains (check `go.mod`).

## Time-based footguns

- `time.After` in a loop allocates a timer per iteration that is not collected
  until it fires (pre-1.23 semantics; 1.23+ made timers collectable, but the
  per-iteration allocation remains). In loops use `time.NewTimer` + `Reset`,
  or a `Ticker`.
- `time.Sleep` for coordination in tests produces flakes; synchronize on
  channels or use polling with a deadline (`require.Eventually`).
