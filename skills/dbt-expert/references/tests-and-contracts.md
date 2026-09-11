# Tests And Contracts

## Test important assumptions

A model is not finished because its SQL executes. Test assumptions that would make downstream analysis wrong if violated.

High-value tests commonly include:

```yaml
models:
  - name: fct_orders
    columns:
      - name: order_id
        data_tests:
          - unique
          - not_null
```

Use the project's dbt Core 1.x syntax and existing conventions.

## Column tests

Use `not_null` when a value is required.

Use `unique` when the column is the model's declared unique grain.

Do not add `unique` merely because a column looks like an identifier. Confirm the grain first.

## Relationship tests

Use relationships when a foreign key should resolve to a parent model.

```yaml
models:
  - name: fct_orders
    columns:
      - name: customer_id
        data_tests:
          - relationships:
              to: ref('dim_customers')
              field: customer_id
```

This tests a data relationship, not just SQL syntax.

## Accepted values

For controlled dimensions, use an accepted-values test when the project needs a hard rule.

```yaml
columns:
  - name: order_status
    data_tests:
      - accepted_values:
          values: ['placed', 'shipped', 'cancelled']
```

Keep the values aligned with the actual source contract.

## Singular tests

Use a singular SQL test for a business rule that does not fit a reusable generic test.

```sql
select
    order_id
from {{ ref('fct_orders') }}
where revenue < 0
```

A singular test should return failing rows. Zero rows means the assertion passed.

## Test selection

Run focused tests while developing:

```bash
dbt test --select fct_orders
```

Prefer:

```bash
dbt build --select fct_orders
```

when the change needs both model execution and associated tests.

## Fix-until-clean loop

After changing tests:

```bash
dbt parse
```

Fix every parse error and re-run.

Then:

```bash
dbt test --select <selector>
```

Fix every failure and re-run until clean.

## Contracts

A model contract makes the expected shape of a model explicit. Use contracts when the project needs a stable schema guarantee and the adapter supports the required contract behavior.

A typical configuration is:

```yaml
models:
  - name: fct_orders
    config:
      contract:
        enforced: true
    columns:
      - name: order_id
        data_type: integer
      - name: order_total
        data_type: numeric
```

The exact supported data types depend on the adapter and project.

## Contract versus tests

Contracts protect model structure and declared column types.

Data tests validate data values and relationships.

Use both when both kinds of correctness matter.

```text
contract
  -> column names and declared types

data tests
  -> uniqueness, nullability, relationships, business rules
```

Do not treat a contract as a replacement for data-quality tests.

## Contract workflow

Before enforcing a contract:

1. Inspect the compiled model schema.
2. Declare every required column and its adapter-compatible type.
3. Run the model build.
4. Fix all contract errors.
5. Run the model tests.
6. Re-run until clean.

## Schema YAML placement

Follow the repository's existing convention for YAML files. Do not duplicate a model's properties across multiple files unless the project already uses that pattern.

## Source tests

Sources can have tests and metadata. Keep source definitions close to the source configuration when that matches project structure.

## Tests are executable specifications

Prefer a test when a rule is important enough that a future change should fail loudly if it breaks.

Bad:

```text
This column should usually be unique.
```

Better:

```yaml
- name: order_id
  data_tests:
    - unique
```

## Avoid noisy tests

Do not test every trivial expression. Focus on keys, required fields, important relationships, accepted domains, and high-impact business invariants.

## Incremental model tests

For an incremental model with a unique key, test the unique key explicitly when uniqueness is part of the model's correctness.

```yaml
columns:
  - name: event_id
    data_tests:
      - not_null
      - unique
```

A test failure can reveal a broken incremental merge assumption before duplicate records reach downstream models.

## Test dependencies

If a test references another model, use `ref()` in the test or YAML configuration where supported. Do not hardcode environment-specific relation names.

## Verification evidence

A useful PR should state the focused commands that were run:

```bash
dbt parse
dbt build --select <model>
dbt test --select <model>
```

If contracts changed, include the build result because contract enforcement occurs during model execution.

## Review checklist

```text
[ ] important key tested
[ ] required columns tested
[ ] critical relationships tested
[ ] business rules tested where needed
[ ] contract used only when schema stability matters
[ ] test failures investigated rather than suppressed
[ ] focused dbt build is clean
```
