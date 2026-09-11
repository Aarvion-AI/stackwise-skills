# Incremental Models

## Mental model

An incremental model has two important paths:

```text
first run / full refresh
    -> process all eligible source data

incremental run
    -> process only rows selected by is_incremental()
    -> apply the adapter's incremental strategy
```

The model SQL must be valid in both paths.

## Minimal pattern

```sql
{{
  config(
    materialized='incremental',
    unique_key='event_id'
  )
}}

select
    event_id,
    user_id,
    event_at,
    updated_at
from {{ ref('stg_events') }}

{% if is_incremental() %}
where updated_at >= (
    select coalesce(max(updated_at), '1900-01-01')
    from {{ this }}
)
{% endif %}
```

## Why the unique key matters

If the same logical record can arrive again with updated values, append-only behavior can create duplicates.

The key should represent the model grain.

```text
event_id
```

is appropriate only if one row per event is the model grain.

For a composite grain:

```yaml
unique_key: ['account_id', 'event_date']
```

The key columns should not contain nulls.

## Late-arriving data

A strict `>` filter can miss records that arrive with the same timestamp as the current maximum. A bounded lookback can be safer when the source can arrive late.

Example:

```sql
{% if is_incremental() %}
where updated_at >= (
    select coalesce(max(updated_at), '1900-01-01')
    from {{ this }}
)
{% endif %}
```

Whether a lookback window is needed depends on source guarantees.

## Updated records

For mutable sources, filter on a column that changes when the source record changes.

Do not use `created_at` as the incremental watermark if records can be updated after creation.

Prefer:

```sql
where updated_at >= (
    select coalesce(max(updated_at), '1900-01-01')
    from {{ this }}
)
```

when `updated_at` is reliable.

## New records only

For append-only sources:

```sql
{% if is_incremental() %}
where event_at >= (
    select coalesce(max(event_at), '1900-01-01')
    from {{ this }}
)
{% endif %}
```

This is appropriate only when older records are never corrected or re-sent.

## `this`

`{{ this }}` points to the target relation for the current model.

It is useful for finding the current high-water mark:

```sql
select max(updated_at)
from {{ this }}
```

The target table may not exist during the first run, which is why the query belongs inside `is_incremental()`.

## Full refresh

Use a full refresh when the transformation logic changes in a way that affects historical rows.

```bash
dbt build --full-refresh --select fct_events
```

For dependent incremental models, select the required downstream graph according to the project's conventions.

## Schema changes

Choose an explicit policy when incremental columns evolve.

```sql
{{
  config(
    materialized='incremental',
    unique_key='event_id',
    on_schema_change='fail'
  )
}}
```

`fail` is a conservative option when silent schema drift is unacceptable.

## Incremental predicates

Some adapters support `incremental_predicates` for limiting scans of existing target data during supported strategies.

```yaml
config:
  materialized: incremental
  unique_key: id
  incremental_strategy: merge
  incremental_predicates:
    - "DBT_INTERNAL_DEST.session_start > dateadd(day, -7, current_date)"
```

This is an advanced optimization. Confirm adapter support and syntax before using it.

## Debugging duplicate rows

If an incremental model duplicates records:

1. Check whether the unique key truly identifies one row.
2. Check whether the key contains nulls.
3. Check whether the incoming incremental batch has duplicate keys.
4. Check whether the selected incremental strategy uses the unique key.
5. Inspect the compiled SQL.
6. Run a full refresh and compare results.

Useful query:

```sql
select
    event_id,
    count(*) as row_count
from {{ ref('stg_events') }}
group by 1
having count(*) > 1
```

## Debugging missed updates

Check:

```text
[ ] watermark column changes on source updates
[ ] incremental predicate includes the desired boundary
[ ] late-arriving records are handled
[ ] target max timestamp is trustworthy
[ ] full-refresh result is the expected baseline
```

## Verification sequence

Run:

```bash
dbt parse
```

Fix every issue and repeat until clean.

Then:

```bash
dbt compile --select <model>
```

Fix every issue and repeat until clean.

Then establish a clean baseline:

```bash
dbt build --full-refresh --select <model>
```

Fix every issue and repeat until clean.

Then validate the incremental path:

```bash
dbt build --select <model>
```

Fix every issue and repeat until clean.

Then run tests:

```bash
dbt test --select <model>
```

Fix every failure and repeat until clean.

## Historical validation

When logic changes, compare a full-refresh result with the expected business result. Do not assume a successful incremental run proves historical correctness.

## Cost awareness

Incremental models reduce transformation work when the incremental predicate is selective. If the query still scans almost all source and target data, incremental materialization may add complexity without meaningful savings.

Measure before optimizing.

## Anti-patterns

Do not write:

```sql
select *
from {{ ref('events') }}
```

and call the model incremental without a meaningful incremental predicate.

Do not use a unique key that is not unique.

Do not hide incremental logic in a macro that makes the model impossible to audit.

Do not assume `--full-refresh` is harmless in production. It can rebuild a large relation and materially increase compute or lock pressure depending on the adapter.

## Final checklist

```text
[ ] model grain defined
[ ] source update semantics understood
[ ] incremental predicate matches source semantics
[ ] unique key is non-null and truly unique
[ ] strategy is supported by the adapter
[ ] first/full-refresh path works
[ ] incremental path works
[ ] tests pass
[ ] historical impact reviewed
```
