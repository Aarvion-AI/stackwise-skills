# PostgreSQL 17 Schema Design and Types

Production patterns for robust schema design, identifier strategy, constraints, and data type choices in PostgreSQL 17.

## Primary Keys: IDENTITY vs SERIAL

PostgreSQL 10+ introduced standard SQL identity columns, which supersede `SERIAL`. Always use `GENERATED ALWAYS AS IDENTITY` for new tables.

```sql
-- Good: Standard SQL, sequence owned directly, prevents accidental manual inserts
CREATE TABLE accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL
);

-- Forcing an override requires explicit clause (auditable):
INSERT INTO accounts (account_id, name)
OVERRIDING SYSTEM VALUE
VALUES (100, 'Migrated Account');

-- Avoid: Legacy SERIAL creates unmanaged sequence objects
CREATE TABLE legacy_accounts (
    account_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
```

## Identifier Strategies: Sequential vs UUID

When exposing identifiers publicly, avoid sequential integer enumeration:

1. **Internal Bigint ID**: Primary key for efficient joins and clustered B-Tree locality.
2. **Public UUID**: Secondary unique column for public API references.

```sql
CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

## Text and Strings: VARCHAR vs TEXT

In PostgreSQL, `TEXT` and `VARCHAR(n)` share identical underlying storage engine representation (`varlena`). Adding arbitrary length limits like `VARCHAR(255)` adds maintenance overhead without performance benefits.

```sql
-- Good: TEXT with semantic check constraint when bounds matter
CREATE TABLE organizations (
    org_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legal_name TEXT NOT NULL,
    country_code TEXT NOT NULL CHECK (char_length(country_code) = 2)
);

-- Avoid: Arbitrary 255 length bounds
CREATE TABLE legacy_orgs (
    org_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legal_name VARCHAR(255) NOT NULL
);
```

## Timestamps and Dates

Always store timestamps with timezone (`TIMESTAMPTZ`). Plain `TIMESTAMP` discards client timezone offsets upon storage.

```sql
-- Good: UTC normalized timestamp with timezone
created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()

-- Note: now() and CURRENT_TIMESTAMP return transaction start time.
-- clock_timestamp() returns current wall clock time.
```

## JSONB vs Normalization

Use JSONB for sparse attributes, dynamic schemas, and audit logs. Normalize core queryable entities into relational columns.

```sql
CREATE TABLE customer_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES accounts(account_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT valid_payload CHECK (jsonb_typeof(payload) = 'object')
);

-- JSONB existence and containment operators
-- payload ? 'session_id' (key exists)
-- payload @> '{"action": "checkout"}' (contains key-value)
```
