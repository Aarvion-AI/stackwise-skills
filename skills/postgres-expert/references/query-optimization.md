# PostgreSQL Query Optimization Patterns

Advanced techniques for query optimization, execution plan tuning, and efficient set processing in PostgreSQL 17.

## Keyset (Cursor) Pagination vs OFFSET

Avoid `OFFSET` for pagination beyond page 1. `OFFSET 10000` forces the database engine to scan and discard 10,000 index tuples and heap pages.

```sql
-- Keyset pagination (always scans exactly 20 tuples):
SELECT order_id, customer_id, total_amount, created_at
FROM orders
WHERE (created_at, order_id) < ($last_seen_created_at, $last_seen_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Requires supporting composite index:
CREATE INDEX idx_orders_pagination 
ON orders (created_at DESC, order_id DESC);
```

## Optimizing Common Table Expressions (CTEs)

PostgreSQL 12+ can inline simple CTEs automatically. To prevent materialization or force inlining explicitly:

```sql
-- Explicitly inline CTE (treat like subquery for index pushdown):
WITH recent_orders AS MATERIALIZED (
    -- Forces evaluation once and caches result in temp buffer
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    WHERE created_at >= now() - INTERVAL '30 days'
    GROUP BY customer_id
)
SELECT c.email, r.revenue
FROM customers c
JOIN recent_orders r ON r.customer_id = c.customer_id;
```

## Lateral Joins for Correlated Subqueries

Use `LEFT JOIN LATERAL` to retrieve top-N records per parent entity in a single query:

```sql
-- Get 3 most recent comments for every blog post:
SELECT p.post_id, p.title, c.comment_id, c.body, c.created_at
FROM posts p
LEFT JOIN LATERAL (
    SELECT comment_id, body, created_at
    FROM comments
    WHERE comments.post_id = p.post_id
    ORDER BY created_at DESC
    LIMIT 3
) c ON true;

-- Supported by index on comments (post_id, created_at DESC)
```

## Eliminating Sequential Scans on Big Tables

Check why the planner avoided an index:
1. **Low table selectivity**: If the query matches >15% of the table rows, sequential scans are naturally faster.
2. **Missing functional indexes**: Query filters `WHERE lower(email) = 'test@example.com'`; standard index on `email` cannot be used. Create `CREATE INDEX idx_users_lower_email ON users (lower(email))`.
3. **Data type mismatches**: Querying `WHERE varchar_col = 123` forces a sequential scan due to implicit type cast.
