# Materializations

## Choose based on workload

The default choice should follow the project's needs, not a fixed preference.

```text
view
  -> cheap to build
  -> query logic runs when the view is queried

table
  -> materialized result
  -> useful when repeated downstream queries should not recompute complex logic

incremental
  -> rebuilds only selected new or changed rows after the first run
  -> requires correct incremental logic

ephemeral
  -> inlined into downstream SQL
  -> useful for small reusable transformations that should not exist as warehouse relations
```

## Views

Use a view when the transformation is cheap enough to run at query time and the project benefits from avoiding stored copies.

```sql
{{ config(materialized='view') }}

select
    customer_id,
    count(*) as order_count
from {{ ref('stg_orders') }}
group by 1
```

Do not choose a view for an expensive transformation simply because the model is small in code.

## Tables

Use a table when materializing the result improves repeated query performance or isolates expensive transformations.

```sql
{{ config(materialized='table') }}

select
    customer_id,
    sum(order_total) as lifetime_value
from {{ ref('fct_orders') }}
group by 1
```

Consider rebuild cost and warehouse storage before making a table the default.

## Ephemeral

Use ephemeral for small reusable SQL that is useful as a building block but does not need to be queried directly.

```sql
{{ config(materialized='ephemeral') }}

select
    order_id,
    lower(trim(email)) as email
from {{ ref('stg_orders') }}
```

Do not use ephemeral for a large transformation whose SQL would become difficult to debug after being inlined.

## Incremental

Use incremental when the model is expensive enough that processing only new or changed records materially reduces runtime or compute.

```sql
{{
  config(
    materialized='incremental',
    unique_key='order_id'
  )
}}

select
    order_id,
    updated_at,
    order_total
from {{ ref('stg_orders') }}

{% if is_incremental() %}
where updated_at >= (
    select coalesce(max(updated_at), '1900-01-01')
    from {{ this }}
)
{% endif %}
```

The SQL must remain valid for both the initial/full-refresh path and the incremental path.

## Unique key

If updates can arrive for an existing logical row, define a unique key that matches the model grain.

```yaml
models:
  - name: fct_orders
    config:
      materialized: incremental
      unique_key: order_id
```

Do not use a nullable column as a unique key. If the grain is composite, use a list:

```yaml
unique_key: ['account_id', 'order_date']
```

The combination must actually identify one row.

## Append versus update behavior

Without a unique key, many incremental strategies append rows. This can duplicate records when source data contains updates.

Do not add a unique key blindly. First establish whether the model needs update semantics and whether the chosen adapter and strategy support the desired behavior.

## Incremental filter

Use `is_incremental()` for logic that should run only during an incremental build.

```sql
{% if is_incremental() %}
where updated_at >= (
    select coalesce(max(updated_at), '1900-01-01')
    from {{ this }}
)
{% endif %}
```

Keep the filter aligned with the source's update semantics. A creation timestamp is not sufficient if records can be updated after creation.

## Historical correctness

If incremental SQL changes historical transformations, a normal run does not necessarily rewrite old rows.

Use:

```bash
dbt build --full-refresh --select <model>
```

when a full rebuild is required.

Include downstream models when their historical results depend on the changed model and the project's workflow requires it.

## Schema changes

`on_schema_change` can control some top-level schema differences for incremental models.

```sql
{{ config(
    materialized='incremental',
    unique_key='order_id',
    on_schema_change='fail'
) }}
```

Choose the behavior deliberately. `ignore` is the default. `append_new_columns` adds new columns without removing old ones. `sync_all_columns` also removes missing columns and handles data type changes subject to adapter behavior.

Do not claim that `on_schema_change` backfills old rows. It does not.

## Strategy

Incremental strategy is adapter-dependent. Do not assume every strategy works everywhere.

Check the adapter and project documentation before choosing `merge`, `delete+insert`, `insert_overwrite`, or another strategy.

## Performance

Filter large upstream relations as early as practical in incremental SQL.

```sql
with events as (
    select *
    from {{ ref('stg_events') }}
    {% if is_incremental() %}
    where event_at >= (
        select coalesce(max(event_at), '1900-01-01')
        from {{ this }}
    )
    {% endif %}
)
select ...
from events
```

The exact optimization depends on the warehouse and query planner.

## Verification

For materialization changes:

```bash
dbt parse
dbt compile --select <model>
dbt build --select <model>
```

Fix every issue and re-run until clean.

For incremental logic changes:

```bash
dbt build --full-refresh --select <model>
dbt build --select <model>
```

Then inspect the target relation and relevant tests.

## Review checklist

```text
[ ] materialization matches workload
[ ] model grain is known
[ ] incremental filter captures new/updated rows
[ ] unique_key matches the grain when needed
[ ] nullable unique keys are avoided
[ ] historical rebuild impact is considered
[ ] adapter-specific strategy is confirmed
[ ] build and tests are clean
```
