# Project And Dependencies

## Project shape

A dbt Core project normally has `dbt_project.yml`, model SQL files, YAML properties, macros, and optional seeds, snapshots, and tests.

```text
dbt_project.yml
models/
  staging/
    stg_orders.sql
    _sources.yml
  marts/
    fct_orders.sql
    _models.yml
macros/
seeds/
snapshots/
tests/
```

Keep the project's existing layout when extending it. Do not create a new hierarchy just because it is familiar from another project.

## Model dependencies

Use `ref()` for dbt-managed models, seeds, and snapshots.

```sql
select *
from {{ ref('stg_orders') }}
```

`ref()` creates a dependency edge in the DAG and compiles to the deployed relation. It also allows environments to change schemas without rewriting model SQL.

Do not write this for a dbt model:

```sql
select *
from analytics.stg_orders
```

The hardcoded relation bypasses the DAG and can break development, CI, and deployment environments.

## Raw inputs

Declare raw tables as sources and use `source()`.

```yaml
sources:
  - name: app
    schema: raw
    tables:
      - name: orders
      - name: customers
```

Then:

```sql
select *
from {{ source('app', 'orders') }}
```

This keeps raw inputs visible to dbt and gives source metadata a stable place to live.

## Source discipline

Do not create a source for an already-modeled dbt relation. Use `ref()`.

Do not use `ref()` for a raw table that has been declared as a source. Use `source()`.

A useful boundary is:

```text
raw warehouse objects
        |
      source()
        |
staging models
        |
       ref()
        |
intermediate models
        |
       ref()
        |
mart models
```

## Model grain

Before writing SQL, state the intended grain in one sentence.

Example:

```text
One row per order.
```

Then ensure joins preserve that grain. If a one-to-many join is intentional, aggregate before joining to the final grain.

## Selection

Use dbt selectors rather than manually naming unrelated models.

```bash
dbt ls --select fct_orders
dbt build --select fct_orders
dbt build --select +fct_orders
dbt build --select fct_orders+
dbt build --select +fct_orders+
```

Use `+` intentionally. `+model` includes parents, `model+` includes children, and `+model+` includes both.

## Compilation

Inspect generated SQL when debugging Jinja or dependency problems.

```bash
dbt compile --select fct_orders
```

Compilation should succeed before using a model as evidence that the generated SQL is correct.

## Project configuration

Keep environment-specific settings in profiles and project configuration rather than hardcoding credentials or warehouse details in model SQL.

Do not commit secrets.

## Macros

Search for an existing macro before creating a new one.

```bash
grep -R "macro " macros models
```

A macro should remove meaningful duplication or encode a project-wide rule. Do not create a macro for a single simple SQL expression.

## Verification loop

After dependency changes:

```bash
dbt parse
```

Fix every error and run it again.

Then:

```bash
dbt ls --select <selector>
dbt compile --select <selector>
dbt build --select <selector>
```

Fix every failure and re-run until clean.

## Practical review checklist

Before opening a PR, confirm:

```text
[ ] model grain is explicit
[ ] raw tables use source()
[ ] dbt models use ref()
[ ] no hardcoded environment-specific relations
[ ] selectors include the intended parents/children
[ ] parse succeeds
[ ] compile succeeds
[ ] affected build succeeds
```

## Avoiding dependency surprises

A model can compile while still producing an incorrect DAG if a raw relation is hardcoded. Compilation is necessary but not sufficient. Review every relation in the SQL and ask whether it should be `ref()` or `source()`.

## Versioned refs

When a project uses versioned models, follow the project's declared versioning policy. If you intentionally need a specific version, use the version argument:

```sql
select *
from {{ ref('customer', version=1) }}
```

Do not introduce model versioning casually. It is a contract decision for downstream consumers.

## Cross-project references

If the project uses cross-project dependencies, use the project's documented two-argument form:

```sql
select *
from {{ ref('upstream_project', 'customer') }}
```

Do not invent a cross-project dependency configuration. Follow the project's existing setup.

## Final verification

For a dependency change, the minimum useful evidence is:

```bash
dbt parse
dbt ls --select <selector>
dbt compile --select <selector>
dbt build --select <selector>
```

If the model is incremental or its historical logic changed, also perform an appropriate full-refresh validation.
