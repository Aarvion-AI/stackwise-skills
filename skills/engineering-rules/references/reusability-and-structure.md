# Reusability and Structure (Rules 1-2)

Rule 1: search before writing, extract on the second occurrence, one responsibility per unit.
Rule 2: small units, clear boundaries, one-way dependencies, no hidden global state, config over hardcoding, follow the project's idioms.

## Search Before Writing

Before writing any helper, run searches by domain concept, not just by the name you would have picked:

```bash
# Looking to format a date? Search the concept, its synonyms, and likely locations.
grep -rn "formatDate\|toDateString\|dateFmt\|humanDate" src/
ls src/utils src/lib src/shared 2>/dev/null
# Python projects
grep -rn "def .*date" src/ --include="*.py" | grep -i "format\|parse\|human"
```

If a near-fit exists, extend it with a parameter rather than writing a sibling:

```typescript
// Bad: found formatDate but wrote a variant anyway
export function formatDate(d: Date): string { return d.toISOString().slice(0, 10); }
export function formatDateWithTime(d: Date): string { return d.toISOString().slice(0, 16).replace("T", " "); }

// Good: one function, one axis of variation
export function formatDate(d: Date, withTime = false): string {
  const iso = d.toISOString();
  return withTime ? iso.slice(0, 16).replace("T", " ") : iso.slice(0, 10);
}
```

## Extract on the Second Occurrence

The first time a shape appears, write it inline. The second time, extract it. Do not wait for a third.

```python
# Bad: same retry shape copy-pasted into two clients
class OrdersClient:
    def fetch(self, order_id: str) -> Order:
        for attempt in range(3):
            try:
                return self._get(f"/orders/{order_id}")
            except TransientError:
                time.sleep(2 ** attempt)
        raise RetryExhaustedError(order_id)

class InvoicesClient:
    def fetch(self, invoice_id: str) -> Invoice:
        for attempt in range(3):
            try:
                return self._get(f"/invoices/{invoice_id}")
            except TransientError:
                time.sleep(2 ** attempt)
        raise RetryExhaustedError(invoice_id)
```

```python
# Good: the repeated shape becomes one function; call sites keep their meaning
def with_retry(op: Callable[[], T], key: str, attempts: int = 3) -> T:
    for attempt in range(attempts):
        try:
            return op()
        except TransientError:
            time.sleep(2 ** attempt)
    raise RetryExhaustedError(key)

class OrdersClient:
    def fetch(self, order_id: str) -> Order:
        return with_retry(lambda: self._get(f"/orders/{order_id}"), order_id)

class InvoicesClient:
    def fetch(self, invoice_id: str) -> Invoice:
        return with_retry(lambda: self._get(f"/invoices/{invoice_id}"), invoice_id)
```

Extraction test: the extracted unit must be nameable by what it does (`with_retry`), not by where it came from (`shared_fetch_logic`). If you cannot name it, the duplication may be coincidental; leave it.

## Single Responsibility

A function that fetches, transforms, and persists is three functions wearing one name.

```typescript
// Bad: one function, three jobs, untestable seams
async function syncUsers(): Promise<void> {
  const res = await fetch(`${API}/users`);
  const users = (await res.json()) as ApiUser[];
  const rows = users.map((u) => ({ id: u.id, email: u.email.toLowerCase(), active: u.status === "ok" }));
  for (const row of rows) await db.upsert("users", row);
}

// Good: each unit testable alone; the orchestrator reads as the plan
async function fetchUsers(): Promise<ApiUser[]> {
  const res = await fetch(`${API}/users`);
  return res.json();
}

function toUserRow(u: ApiUser): UserRow {
  return { id: u.id, email: u.email.toLowerCase(), active: u.status === "ok" };
}

async function syncUsers(): Promise<void> {
  const users = await fetchUsers();
  await db.upsertMany("users", users.map(toUserRow));
}
```

## Module Boundaries and Dependency Direction

Dependencies point from outer layers (HTTP, CLI, UI) toward the domain, never the reverse. A domain module importing a controller, view, or ORM entity is a boundary violation.

```
src/
  domain/        # pure logic; imports nothing outside domain/
  services/      # orchestrates domain; imports domain/, not routes/
  routes/        # HTTP shells; imports services/; no business logic
```

```python
# Bad: domain reaching outward
# domain/pricing.py
from routes.checkout import current_request       # domain now depends on HTTP
def discount(total): return total * (0.9 if current_request.user.is_vip else 1.0)

# Good: caller passes what the domain needs
# domain/pricing.py
def discount(total: Decimal, is_vip: bool) -> Decimal:
    return total * (Decimal("0.9") if is_vip else Decimal("1"))
# routes/checkout.py
price = discount(cart.total, is_vip=request.user.is_vip)
```

## No Hidden Global State

Module-level mutable state makes call order matter and tests order-dependent.

```typescript
// Bad: mutable module global; who set it, and when?
let currentTenant: string;
export function setTenant(t: string) { currentTenant = t; }
export function tableName(base: string) { return `${currentTenant}_${base}`; }

// Good: state travels explicitly
export function tableName(tenant: string, base: string) { return `${tenant}_${base}`; }
```

Acceptable module-level state: immutable constants, and caches that are pure functions of their inputs.

## Configuration Over Hardcoding

Anything that varies by environment (URLs, limits, timeouts, feature toggles, file paths) is read from config, once, at the edge.

```python
# Bad: literals buried mid-function, different per environment
def upload(file: bytes) -> str:
    if len(file) > 10 * 1024 * 1024:
        raise FileTooLargeError()
    return s3.put("prod-uploads-bucket", file)

# Good: config object built once at startup, injected where needed
@dataclass(frozen=True)
class UploadConfig:
    bucket: str
    max_bytes: int

def upload(file: bytes, cfg: UploadConfig) -> str:
    if len(file) > cfg.max_bytes:
        raise FileTooLargeError(limit=cfg.max_bytes)
    return s3.put(cfg.bucket, file)
```

Do not swing to the other extreme: a value used once, identical in every environment, is a named constant next to its use, not a config entry.

## Follow the Project's Structure and Idioms

Before adding a file, look at how neighbors do it and match them, even when you would have chosen differently:

- Where do tests live (`__tests__/`, `*.test.ts` beside source, `tests/` tree)? Put yours in the same place.
- How are errors surfaced (exceptions, `Result` types, error codes)? Use the existing channel; do not introduce a second.
- Naming conventions (`camelCase` vs `snake_case` files, `IThing` vs `Thing`)? Consistency beats preference.

A diff that is locally "better" but idiomatically foreign costs every future reader a context switch. Change the idiom repo-wide in its own PR, or follow it.

## Checklist for This Reference

- [ ] Searched for an existing helper before writing a new one
- [ ] Every shape appearing twice in the diff is extracted, and the extraction has a behavior-based name
- [ ] Each new function does one thing; orchestration is separate from work
- [ ] No import points from domain code outward to HTTP/UI/DB layers
- [ ] No new mutable module-level state
- [ ] Environment-dependent values come from config; single-use constants stay local
- [ ] New files, tests, and errors follow the surrounding project's conventions
