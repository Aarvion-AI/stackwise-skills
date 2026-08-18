# Readability and Naming (Rule 3)

Code is read far more often than written. Optimize every line for the next reader: intention-revealing names, early returns, top-down flow, and the project's formatter as the single source of style.

## Intention-Revealing Names

A name answers "what is this?" without reading the implementation. Banned name families:

| Banned | Why | Replace with |
|--------|-----|--------------|
| `data`, `info`, `obj`, `item` | Says nothing about content | `invoices`, `userProfile`, `lineItem` |
| `tmp`, `temp`, `x`, `val` | Placeholder that shipped | The thing it holds: `normalizedEmail` |
| `handle`, `process`, `manage`, `doStuff` | Verb with no object | `retryFailedWebhooks`, `parseCsvRow` |
| `process2`, `newHelper`, `utilsV2` | Numbered variants signal unextracted duplication | Merge or rename by difference: `processRefund` |
| `flag`, `check`, `isOk` | Boolean with no predicate | `hasUnpaidInvoices`, `isRetryable` |

```typescript
// Bad
function process(data: any[]): any[] {
  const tmp = [];
  for (const item of data) {
    if (check(item)) tmp.push(handle(item));
  }
  return tmp;
}

// Good: every name states its role; the signature alone documents the function
function activeSubscribers(users: User[]): Subscriber[] {
  return users
    .filter(isSubscriptionActive)
    .map(toSubscriber);
}
```

Scope rule: the smaller the scope, the shorter the name may be. `i` is fine for a 3-line loop; a module-level export needs a full sentence-grade name.

```python
# Bad: long-lived vague name
d = load_config()
...  # 80 lines later
timeout = d["timeout"]

# Good
config = load_config()
timeout_seconds = config["timeout"]
```

## Early Returns Over Nesting

Handle failure and edge cases first, then write the happy path at the lowest indent level. Every level of nesting is a fact the reader must hold in memory.

```python
# Bad: happy path buried three levels deep
def refund(order: Order, amount: Decimal) -> Refund:
    if order is not None:
        if order.status == Status.PAID:
            if amount <= order.total:
                refund = gateway.refund(order.charge_id, amount)
                ledger.record(refund)
                return refund
            else:
                raise AmountExceedsTotalError(amount, order.total)
        else:
            raise NotPaidError(order.id)
    else:
        raise OrderNotFoundError()

# Good: guards eliminate cases one by one; happy path is unindented
def refund(order: Order, amount: Decimal) -> Refund:
    if order is None:
        raise OrderNotFoundError()
    if order.status != Status.PAID:
        raise NotPaidError(order.id)
    if amount > order.total:
        raise AmountExceedsTotalError(amount, order.total)

    refund = gateway.refund(order.charge_id, amount)
    ledger.record(refund)
    return refund
```

```go
// Same rule in Go: check-and-return is the idiom, never else-ladders
func Refund(order *Order, amount Money) (*Refund, error) {
    if order == nil {
        return nil, ErrOrderNotFound
    }
    if order.Status != StatusPaid {
        return nil, fmt.Errorf("order %s not paid: %w", order.ID, ErrNotPaid)
    }
    if amount.GreaterThan(order.Total) {
        return nil, ErrAmountExceedsTotal
    }
    r, err := gateway.Refund(order.ChargeID, amount)
    if err != nil {
        return nil, fmt.Errorf("gateway refund: %w", err)
    }
    ledger.Record(r)
    return r, nil
}
```

## Code Reads Top-Down Like Prose

A file should read like an article: the headline (public entry point) first, supporting detail below, each function calling only downward. The reader should never scroll up to understand what they just read.

```typescript
// Good: newspaper order. Read exportReport and you know the whole story;
// dig into any paragraph only if you need the detail.
export async function exportReport(runId: string): Promise<string> {
  const findings = await loadFindings(runId);
  const rows = findings.map(toCsvRow);
  return writeCsv(rows);
}

async function loadFindings(runId: string): Promise<Finding[]> { /* ... */ }
function toCsvRow(f: Finding): CsvRow { /* ... */ }
function writeCsv(rows: CsvRow[]): string { /* ... */ }
```

Within a function, keep one level of abstraction. A function that mixes `await db.query(...)` with `retryQueue.schedule(order)` is telling two stories at once; push the low-level line into a named helper so every statement sits at the same altitude.

```python
# Bad: altitudes mixed; the SQL detail interrupts the business narrative
def close_month(month: str) -> Summary:
    invoices = db.execute("SELECT * FROM invoices WHERE month = %s AND status = 'open'", [month])
    total = sum(Decimal(r["amount"]) for r in invoices)
    notify_finance(month, total)
    return Summary(month, total)

# Good
def close_month(month: str) -> Summary:
    invoices = open_invoices(month)
    total = sum(inv.amount for inv in invoices)
    notify_finance(month, total)
    return Summary(month, total)
```

## Booleans, Conditions, and Positivity

- Name predicates so the call site reads as a sentence: `if user.can_refund(order):`.
- Prefer positive names: `isEnabled` over `isNotDisabled`; double negatives (`if not is_invalid`) fail review.
- Extract multi-clause conditions into a named predicate:

```typescript
// Bad
if (user.age >= 18 && user.country === "US" && !user.flags.includes("banned") && user.kycLevel > 1) { ... }

// Good
const canTrade = user.age >= 18 && user.country === "US" && !isBanned(user) && hasCompletedKyc(user);
if (canTrade) { ... }
```

## Consistent Formatting via the Project's Formatter

Formatting is never manual and never debated in review. Find the project's formatter and run it on every change:

| Ecosystem | Format | Lint |
|-----------|--------|------|
| JS/TS | `prettier --write .` | `eslint --fix .` |
| Python | `ruff format` | `ruff check --fix` |
| Go | `gofmt -w .` / `goimports -w .` | `go vet ./...` |
| Dart/Flutter | `dart format .` | `dart analyze` |

Rules that follow from this:

- Never hand-align comments or assignments; the formatter owns whitespace.
- Never disable the formatter for a region (`// prettier-ignore`, `# fmt: off`) to preserve a personal layout; the only acceptable use is data tables whose alignment carries meaning.
- If the project has no formatter config, match the dominant existing style exactly; do not introduce a new one inside a feature PR.

## Checklist for This Reference

- [ ] No banned names (`data`, `tmp`, `handle`, `process2`, `flag`) in the diff
- [ ] Name length matches scope; module-level names are fully descriptive
- [ ] Guard clauses first; happy path at minimum indentation
- [ ] Files read top-down; no upward scrolling required to follow the flow
- [ ] Each function holds one level of abstraction
- [ ] Predicates are positive and read as sentences at the call site
- [ ] Formatter and linter run clean; no ignore pragmas added
