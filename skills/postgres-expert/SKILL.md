---
name: postgres-expert
description: Use when working with *.sql, migrations, EXPLAIN ANALYZE, indexes, psql, or PostgreSQL schemas and queries. Builds production-grade PostgreSQL 17 schemas, writes zero-downtime migrations with safe locks, designs high-performance indexes (B-Tree, BRIN, GIN, partial, covering), optimizes slow queries using EXPLAIN (ANALYZE, BUFFERS), and configures connection pools. Invoke for schema design, index strategy, query optimization, migration safety, or transaction isolation.
license: MIT
metadata:
  version: "0.1.0"
  category: backend
  frameworks: "PostgreSQL 17, psql, pg_stat_statements, pgvector"
  triggers: "*.sql, migrations, EXPLAIN ANALYZE, indexes, psql, postgres, postgresql, pg_stat_statements, pgvector, vacuum, wal, btree, brin, gin"
  related: go-expert, nestjs-expert, terraform-expert
---

# PostgreSQL Expert

Senior PostgreSQL database engineer specializing in PostgreSQL 17 schema architecture, safe zero-downtime migrations, query optimization with execution plans, and index engineering.

## When to Use This Skill

- Design or review database schemas (primary keys, foreign keys, constraints, table partitioning)
- Author safe zero-downtime migrations with explicit lock timeouts and non-blocking index creation
- Diagnose slow queries using `EXPLAIN (ANALYZE, BUFFERS)` to eliminate sequential scans and disk spill
- Select optimal indexing strategies (covering indexes with `INCLUDE`, partial indexes, BRIN, GIN)
- Configure transaction isolation levels (`READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`)
- Tune connection pooling (PgBouncer, pgcat) and manage VACUUM / autovacuum behavior

## Core Workflow

1. **Analyze** - Inspect target tables, row counts, volume growth, constraints, and query access patterns. Review `pg_stat_statements` or slow query logs to understand where execution time is spent before proposing index or schema changes.
2. **Implement** - Write standard SQL adhering to PostgreSQL 17 standards: prefer `GENERATED ALWAYS AS IDENTITY` over legacy `SERIAL`, use `TIMESTAMPTZ` for timestamps, and use declarative constraints. When altering production tables, use safe non-blocking patterns.
3. **Verify SQL syntax and migration safety** - Validate migration statements and queries with `psql -f <migration.sql> --single-transaction --dry-run` or a local staging container (`pg_dump` schema verification). If syntax or locking violations are detected, fix and re-run until clean before proceeding.
4. **Test execution plan** - Run `EXPLAIN (ANALYZE, BUFFERS) <query>` against realistic data volumes. Verify that the planner chooses index scans or bitmap heap scans where appropriate and that shared buffer hits dominate over disk reads. Fix plan regressions and re-run until clean.
5. **Prove it works** - Execute the complete transaction lifecycle against a live PostgreSQL 17 instance. Test rollback behavior, check lock hold durations with `pg_locks`, and confirm data integrity. If verification yields locking delays or query regressions, fix and re-run until the observed behavior meets latency and safety targets.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Schema & Types | `references/schema-and-types.md` | Primary keys, IDENTITY vs SERIAL, UUIDv7, JSONB, constraints, data types |
| Index Engineering | `references/indexes-and-execution.md` | B-tree, partial, covering (INCLUDE), BRIN, GIN, expression indexes, EXPLAIN ANALYZE |
| Zero-Downtime Migrations | `references/zero-downtime-migrations.md` | Lock levels, CREATE INDEX CONCURRENTLY, adding columns, lock_timeout, safe schema changes |
| Query Optimization | `references/query-optimization.md` | CTE optimization, window functions, LATERAL joins, pagination (keyset vs offset), grouping sets |

## Key Patterns

**PostgreSQL 17 Schema Design with IDENTITY and UUIDv7:**

```sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id UUID DEFAULT gen_random_uuid() NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'cancelled')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

**Safe Zero-Downtime Migration with Lock Timeout:**

```sql
-- Step 1: Set short lock timeout to avoid queueing blockers
SET lock_timeout = '2s';
SET statement_timeout = '30s';

-- Step 2: Add column as NULL or with safe constant DEFAULT (PostgreSQL 11+ metadata-only)
ALTER TABLE orders ADD COLUMN cancellation_reason TEXT;

-- Step 3: Create supporting index concurrently without locking writes
COMMIT;
CREATE INDEX CONCURRENTLY idx_orders_status_pending 
ON orders (customer_id, created_at DESC) 
WHERE status = 'pending';
```

## Common Mistakes

- **Using `SERIAL` instead of `GENERATED ALWAYS AS IDENTITY`**: `SERIAL` creates loose sequences with inconsistent permissions and missing ownership metadata; use standard SQL `IDENTITY` in modern PostgreSQL.
- **Adding non-concurrent indexes in transactions**: `CREATE INDEX` locks out all writes (`SHARE` lock) until index construction finishes; use `CREATE INDEX CONCURRENTLY` outside transactional blocks.
- **Running DDL without setting `lock_timeout`**: An ungranted `ACCESS EXCLUSIVE` lock queues behind long queries and blocks all subsequent read/write traffic; always prefix DDL with `SET lock_timeout = '2s'`.
- **Indexing columns without reading execution plans**: Adding composite indexes with wrong column ordering or redundant B-trees that degrade write throughput; inspect `EXPLAIN (ANALYZE, BUFFERS)` to verify selectivity.
- **Offset pagination on large datasets**: `LIMIT 20 OFFSET 50000` requires scanning and discarding 50,000 rows on every page; use keyset (cursor) pagination on indexed sequential columns.
