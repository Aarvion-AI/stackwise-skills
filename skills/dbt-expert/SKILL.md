---
name: dbt-expert
description: Use when working with dbt_project.yml, models/*.sql, schema.yml, dbt run, or dbt test. Builds and reviews dbt Core 1.x models, tests, sources, materializations, incremental models, and contracts. Invoke for creating or refactoring dbt models, choosing materializations, adding tests or contracts, wiring refs and sources, and validating dbt changes.
license: MIT
metadata:
  version: "0.1.0"
  category: data
  frameworks: "dbt Core 1.x"
  triggers: dbt_project.yml, models/*.sql, schema.yml, dbt run, dbt test, ref, source, incremental
  related: engineering-rules
---
# dbt Expert

## When to Use This Skill

* Creating or refactoring dbt models in `models/`
* Choosing between view, table, incremental, or ephemeral materialization
* Adding model and column tests, sources, or contracts
* Wiring model dependencies with `ref()` and raw inputs with `source()`
* Building or reviewing incremental models
* Debugging `dbt run`, `dbt test`, compile, parse, or selection failures

## Core Workflow

1. Inspect the project - read `dbt_project.yml`, the target model, nearby YAML, and existing conventions. Search for existing macros, tests, sources, and materialization configs before adding new ones.
2. Implement the smallest change that preserves the project's model grain and dependency graph. Prefer `ref()` for dbt-managed relations and `source()` for declared raw inputs. Add tests for important keys and business assumptions.
3. Verify parsing and compilation - run `dbt parse`; fix every reported error and re-run until clean.
4. Verify the affected build - run `dbt build --select <model_or_selector>`; fix every reported issue and re-run until clean.
5. Verify the DAG and generated SQL - run `dbt ls --select <model_or_selector>` and `dbt compile --select <model_or_selector>`; fix every issue and re-run until clean.
6. For incremental models, verify both paths - run a normal build and a `dbt build --full-refresh --select <model>` when the change affects historical logic; fix every issue and re-run until clean.
7. Prove the change - run `dbt test --select <model_or_selector>` and inspect the built relation and relevant test results; fix every failure and re-run until clean.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
| --- | --- | --- |
| Project structure and DAG | `references/project-and-dependencies.md` | Creating models, sources, refs, or project configuration |
| Tests and contracts | `references/tests-and-contracts.md` | Adding tests, constraints, or schema contracts |
| Materializations | `references/materializations.md` | Choosing view, table, ephemeral, or incremental |
| Incremental models | `references/incremental.md` | Building or debugging incremental pipelines |

## Key Patterns

Use declared sources instead of hardcoded raw relations:

```sql
select *
from {{ source('app', 'orders') }}
```

Use `ref()` to build the DAG:

```sql
select *
from {{ ref('stg_orders') }}
```

Give incremental models an explicit filter and a real grain:

```sql
{{
  config(
    materialized='incremental',
    unique_key='order_id'
  )
}}
select *
from {{ ref('stg_orders') }}
{% if is_incremental() %}
where updated_at >= (select coalesce(max(updated_at), '1900-01-01') from {{ this }})
{% endif %}
```

Test important assumptions in YAML:

```yaml
models:
  - name: fct_orders
    columns:
      - name: order_id
        data_tests:
          - unique
          - not_null
```

## Common Mistakes

* Hardcoding warehouse table names instead of `ref()` or `source()`. Use DAG-aware references.
* Choosing table or incremental materialization without considering query cost, freshness, rebuild cost, and downstream use.
* Adding an incremental model without defining how new or changed rows are identified.
* Treating tests as optional documentation. Add tests for keys, required fields, and critical business rules.
* Using `unique_key` columns that can be null or are not actually unique at the model grain.
* Changing incremental logic without considering whether a full refresh is required for historical rows.
