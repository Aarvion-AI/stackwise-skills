# Database Access: pgx v5 + sqlc (Postgres)

## Why this stack, not an ORM

Default for Go + Postgres services: **pgx v5** (driver + pool) with **sqlc**
(compile SQL to typed Go). You write real SQL you can `EXPLAIN`; sqlc
generates the boilerplate and catches schema/query drift at codegen time, not
in production. GORM's reflection-heavy API hides N+1s, generates surprising
SQL, and its error handling (`ErrRecordNotFound` via `errors.Is` but half the
docs show `==`) is a bug farm. Choose ent only for genuinely graph-shaped
schemas with typed traversals; choose bare pgx without sqlc only for dynamic
query builders (search filters), and then consider squirrel for just that path.

## Pool setup

```go
import "github.com/jackc/pgx/v5/pgxpool"

func newPool(ctx context.Context, dsn string) (*pgxpool.Pool, error) {
    cfg, err := pgxpool.ParseConfig(dsn) // postgres://user:pass@host:5432/db?sslmode=verify-full
    if err != nil {
        return nil, fmt.Errorf("parse dsn: %w", err)
    }
    cfg.MaxConns = 20                        // default is max(4, NumCPU) - size for your DB, not the app host
    cfg.MinIdleConns = 2
    cfg.MaxConnLifetime = 30 * time.Minute   // survive failovers/rebalances
    cfg.MaxConnIdleTime = 5 * time.Minute

    pool, err := pgxpool.NewWithConfig(ctx, cfg)
    if err != nil {
        return nil, fmt.Errorf("create pool: %w", err)
    }
    if err := pool.Ping(ctx); err != nil { // fail fast at startup
        pool.Close()
        return nil, fmt.Errorf("ping: %w", err)
    }
    return pool, nil
}
```

- `pgxpool.Pool` is concurrency-safe; create **one** in `main`, inject it.
  Never `Acquire` a conn and hold it across requests.
- Use `database/sql` + `pgx/v5/stdlib` only when a library demands `*sql.DB`;
  native pgx is faster (binary protocol) and exposes Postgres types properly.

## sqlc setup

`sqlc.yaml`:

```yaml
version: "2"
sql:
  - engine: "postgresql"
    schema: "db/migrations"        # sqlc reads CREATE TABLEs from migration files
    queries: "db/queries"
    gen:
      go:
        package: "db"
        out: "internal/db"
        sql_package: "pgx/v5"      # generate against pgx, not database/sql
        emit_pointers_for_null_types: true
```

`db/queries/orders.sql` - annotations drive the generated signatures:

```sql
-- name: GetOrder :one
SELECT * FROM orders WHERE id = $1;

-- name: ListOrdersByUser :many
SELECT * FROM orders
WHERE user_id = $1 AND created_at < $2
ORDER BY created_at DESC
LIMIT $3;

-- name: CreateOrder :one
INSERT INTO orders (id, user_id, amount_cents, status)
VALUES ($1, $2, $3, 'pending')
RETURNING *;

-- name: SettleOrder :execrows
UPDATE orders SET status = 'settled', settled_at = now()
WHERE id = $1 AND status = 'pending';
```

Run `sqlc generate` after any query/schema change and commit the output.
`:one` → `(Order, error)`, `:many` → `([]Order, error)`, `:exec` → `error`,
`:execrows` → `(int64, error)` - use `:execrows` when "0 rows affected" is a
domain outcome (stale update, already settled).

## The store layer

Wrap generated code in one package owning error translation and transactions:

```go
package store

var ErrNotFound = errors.New("not found")

type Store struct {
    pool *pgxpool.Pool
    q    *db.Queries
}

func New(pool *pgxpool.Pool) *Store {
    return &Store{pool: pool, q: db.New(pool)}
}

func (s *Store) GetOrder(ctx context.Context, id string) (Order, error) {
    row, err := s.q.GetOrder(ctx, id)
    if errors.Is(err, pgx.ErrNoRows) {
        return Order{}, fmt.Errorf("order %s: %w", id, ErrNotFound)
    }
    if err != nil {
        return Order{}, fmt.Errorf("get order %s: %w", id, err)
    }
    return orderFromRow(row), nil
}
```

`pgx.ErrNoRows` stops here. Handlers branch on `store.ErrNotFound` only.

## Transactions

`Queries.WithTx` rebinds the generated queries to a transaction:

```go
func (s *Store) TransferCredit(ctx context.Context, fromID, toID string, cents int64) error {
    tx, err := s.pool.Begin(ctx)
    if err != nil {
        return fmt.Errorf("begin: %w", err)
    }
    defer tx.Rollback(ctx) // no-op after Commit - ALWAYS defer it

    q := s.q.WithTx(tx)
    if _, err := q.DebitAccount(ctx, db.DebitAccountParams{ID: fromID, Cents: cents}); err != nil {
        return fmt.Errorf("debit %s: %w", fromID, err)
    }
    if _, err := q.CreditAccount(ctx, db.CreditAccountParams{ID: toID, Cents: cents}); err != nil {
        return fmt.Errorf("credit %s: %w", toID, err)
    }
    if err := tx.Commit(ctx); err != nil {
        return fmt.Errorf("commit transfer: %w", err)
    }
    return nil
}
```

Rules:

- The transaction stays **inside one store method**. Passing `pgx.Tx` up to
  HTTP handlers couples transport to storage; if a use case spans methods,
  add a store method for that use case (or a `store.WithinTx(ctx, fn)` helper).
- Never do network calls or long computation inside a tx - you are holding a
  connection and row locks.
- Constraint violations are domain signals - translate them:

```go
var pgErr *pgconn.PgError
if errors.As(err, &pgErr) && pgErr.Code == "23505" { // unique_violation
    return fmt.Errorf("order %s: %w", id, ErrConflict)
}
```

## Batching and bulk loading

- N inserts in a loop → one round trip with `pgx.Batch`, or `COPY` for bulk:

```go
rows := make([][]any, 0, len(events))
for _, e := range events {
    rows = append(rows, []any{e.ID, e.Kind, e.At})
}
_, err := pool.CopyFrom(ctx, pgx.Identifier{"events"},
    []string{"id", "kind", "at"}, pgx.CopyFromRows(rows))
```

- For "WHERE id IN (...)" queries, pass a slice - pgx binds arrays natively:
  `WHERE id = ANY($1::text[])`.

## Migrations

sqlc does not run migrations; pair it with a migration tool - **goose** or
**golang-migrate** - and point sqlc's `schema:` at the migration directory so
generated code always matches the migrated schema.

```
db/migrations/00001_orders.sql
-- +goose Up
CREATE TABLE orders (
    id           text PRIMARY KEY,
    user_id      text NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    status       text NOT NULL DEFAULT 'pending',
    created_at   timestamptz NOT NULL DEFAULT now(),
    settled_at   timestamptz
);
-- +goose Down
DROP TABLE orders;
```

Run migrations as a deploy step or guarded startup step (`goose up`), never
implicitly per-request. Migration files are append-only once merged - fix
mistakes with a new migration, never by editing an applied one.

## Recurring mistakes

- Opening a pool per request or per handler struct - one pool, in `main`.
- `SELECT *` in sqlc queries on wide tables you partially need: name the
  columns; sqlc then generates lean row structs.
- Ignoring the `:execrows` count on UPDATE/DELETE, silently "succeeding" on
  rows that were not there.
- Scanning Postgres `timestamptz` into `time.Time` without ensuring UTC
  discipline - store UTC, convert at the edge.
- Interpolating identifiers or values into SQL strings. Parameters (`$1`) for
  values, always; identifiers must come from a fixed allowlist if dynamic.
