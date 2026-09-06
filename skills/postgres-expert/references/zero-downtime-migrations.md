# Zero-Downtime PostgreSQL Migrations

Best practices for executing schema migrations safely on high-throughput PostgreSQL databases without blocking transactions or table locks.

## Lock Hierarchy and The Danger of Lock Queues

DDL operations require table locks (`ACCESS EXCLUSIVE`). When an `ACCESS EXCLUSIVE` lock request is queued behind a long-running `SELECT`, all subsequent queries to that table are blocked behind the queued lock request, causing connection pool exhaustion and application outage.

### Rule 1: Always Set Lock Timeout

Every migration script modifying production schemas must specify a short lock timeout:

```sql
SET lock_timeout = '2s';
SET statement_timeout = '30s';
```

If the lock cannot be acquired within 2 seconds, the migration aborts immediately, letting background queries continue without queueing.

## Non-Blocking Index Creation

Never run `CREATE INDEX` in transactional migration steps on large tables.

```sql
-- Safe: Builds index concurrently without holding table write locks
CREATE INDEX CONCURRENTLY idx_users_organization_id
ON users (organization_id);
```

If `CREATE INDEX CONCURRENTLY` fails, it leaves behind an `INVALID` index stub that continues to incur write overhead. Always check for and drop invalid indexes:

```sql
SELECT indexrelid::regclass, indisvalid
FROM pg_index
WHERE NOT indisvalid;

-- Clean up invalid index
DROP INDEX CONCURRENTLY IF EXISTS idx_users_organization_id;
```

## Adding Columns Safely

In PostgreSQL 11+, adding a column with a constant default does not rewrite the table:

```sql
-- Fast metadata-only update in PostgreSQL 11+:
ALTER TABLE orders 
ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT false;

-- For volatile defaults (e.g. gen_random_uuid()), add column nullable first:
ALTER TABLE orders ADD COLUMN token UUID;
-- Backfill in batches:
UPDATE orders SET token = gen_random_uuid() WHERE token IS NULL;
-- Add constraint NOT VALID then validate:
ALTER TABLE orders ALTER COLUMN token SET NOT NULL;
```

## Adding Foreign Keys Safely

Adding a foreign key constraint normally requires scanning the entire table under `SHARE ROW EXCLUSIVE` lock. Break this into two safe steps:

```sql
-- Step 1: Add constraint without validating existing rows (takes immediate light lock)
ALTER TABLE line_items
ADD CONSTRAINT fk_line_items_order_id
FOREIGN KEY (order_id) REFERENCES orders(order_id)
NOT VALID;

-- Step 2: Validate existing rows in background (takes SHARE UPDATE EXCLUSIVE, non-blocking)
ALTER TABLE line_items
VALIDATE CONSTRAINT fk_line_items_order_id;
```
