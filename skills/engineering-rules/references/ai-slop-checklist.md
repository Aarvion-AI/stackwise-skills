# AI Slop Checklist (Rule 4)

AI slop is code that looks plausible but no engineer would defend in review. Scan every diff against every item below. Each item is a concrete pattern with a fix; if the pattern matches, the diff is not done.

## The Checklist

- [ ] 1. Unused imports or variables
- [ ] 2. Leftover debug output (`console.log`, `print`, `fmt.Println`)
- [ ] 3. try/catch that swallows or only re-logs
- [ ] 4. Defensive checks for impossible states
- [ ] 5. Over-abstraction for single-use code
- [ ] 6. Redundant type annotations
- [ ] 7. Placeholder names shipped
- [ ] 8. Near-duplicate blocks that should be one function
- [ ] 9. Emoji in code, comments, or output
- [ ] 10. Apology, filler, or narration comments
- [ ] 11. Gratuitous null checks after non-nullable returns

## 1. Unused Imports and Variables

The linter catches most; run it. Also delete variables assigned "just in case":

```typescript
// Bad
import { useMemo, useCallback, useEffect } from "react";  // only useEffect used
const result = await save(user);  // result never read

// Good
import { useEffect } from "react";
await save(user);
```

## 2. Leftover Debug Output

```bash
grep -rn "console\.log\|console\.debug" src/ --include="*.ts" --include="*.tsx"
grep -rn "^\s*print(" src/ --include="*.py"
grep -rn "fmt\.Println" ./ --include="*.go"
```

Every hit is either deleted or promoted to the project's real logger with a level and context. `console.log("here 2")` never ships.

## 3. try/catch That Swallows or Only Re-Logs

```python
# Bad: swallow (caller sees success that did not happen)
try:
    charge(order)
except Exception:
    pass

# Bad: log-and-rethrow adds a duplicate log line and nothing else
try:
    charge(order)
except Exception as e:
    logger.error(f"error: {e}")
    raise

# Good: catch only what you can handle, add context, act
try:
    charge(order)
except CardDeclinedError as e:
    order.mark_payment_failed(reason=e.code)
    notify_customer(order)
```

If you cannot handle it and cannot add context, do not catch it.

## 4. Defensive Checks for Impossible States

```typescript
// Bad: items is typed string[], it cannot be a non-array
function total(items: string[]): number {
  if (!Array.isArray(items)) return 0;
  if (items === null || items === undefined) return 0;
  return items.length;
}

// Good
function total(items: string[]): number {
  return items.length;
}
```

Validate at trust boundaries (HTTP input, file parsing, external APIs) once, then trust your types internally. A check for a state the type system forbids is noise that implies the types are lies.

## 5. Over-Abstraction for Single-Use Code

One implementation needs no interface, factory, base class, or strategy enum.

```typescript
// Bad: ceremony around a single concrete emailer
interface INotificationStrategy { send(msg: string): Promise<void>; }
class EmailNotificationStrategy implements INotificationStrategy { /* ... */ }
class NotificationStrategyFactory {
  static create(): INotificationStrategy { return new EmailNotificationStrategy(); }
}
await NotificationStrategyFactory.create().send(msg);

// Good
await sendEmail(msg);
```

```python
# Bad: config class wrapping one value
class TimeoutConfigurationProvider:
    def get_timeout(self) -> int:
        return 30

# Good
TIMEOUT_SECONDS = 30
```

Add the abstraction when the second implementation arrives, not before.

## 6. Redundant Type Annotations

Annotate where inference fails or at public boundaries; never restate the right-hand side.

```typescript
// Bad
const name: string = "checkout";
const users: User[] = await repo.list();  // list() already returns Promise<User[]>

// Good
const name = "checkout";
const users = await repo.list();
export function parsePrice(raw: string): Decimal { /* public API: keep the annotation */ }
```

```python
# Bad
count: int = 0
names: list[str] = ["a", "b"]

# Good
count = 0
names = ["a", "b"]
def parse_price(raw: str) -> Decimal: ...  # signatures stay annotated
```

## 7. Placeholder Names Shipped

`foo`, `bar`, `myFunction`, `temp`, `data2`, `newFile`, `test123`, `helper`. See `readability-and-naming.md` for the full table. Any of these in a diff means the naming pass was skipped.

## 8. Near-Duplicate Blocks

Two blocks differing only in a value or a field name are one function with a parameter:

```go
// Bad
activeUsers := 0
for _, u := range users {
    if u.Status == "active" { activeUsers++ }
}
bannedUsers := 0
for _, u := range users {
    if u.Status == "banned" { bannedUsers++ }
}

// Good
func countByStatus(users []User, status string) int {
    n := 0
    for _, u := range users {
        if u.Status == status { n++ }
    }
    return n
}
```

## 9. Emoji in Code or Output

No emoji in identifiers, comments, log lines, CLI output, commit messages, or error text. `logger.info("Deployment successful ✅")` ships as `logger.info("deployment successful")`. Exceptions: user-facing copy where the product spec explicitly includes them, and test fixtures asserting emoji handling.

## 10. Apology, Filler, and Narration Comments

```python
# Bad: all of these are deleted on sight
# This is a simple helper function
# Sorry, this is a bit hacky
# Now we loop over the users
# TODO: fix this later
users = load_users()  # load the users

# Good: nothing, or a why-comment (see comments-and-dead-code.md)
users = load_users()
```

TODO survives only as `TODO(owner, #482): remove after v2 migration`, with an owner and an issue.

## 11. Gratuitous Null Checks After Non-Nullable Returns

```typescript
// Bad: createUser is typed to return User, never null
const user = await createUser(input);
if (!user) throw new Error("user creation failed");

// Good: trust the signature; the function throws on failure
const user = await createUser(input);
```

If the function can actually fail with null, fix its type to say so (`User | null`, `Optional[User]`), then the check is honest and required by the compiler, not decorative.

## How to Run This Checklist

1. Generate the diff: `git diff` (or `git diff main...HEAD` for a branch).
2. Walk items 1-11 against every hunk; grep commands above cover items 1, 2, and 9 mechanically.
3. Fix every hit, then re-run the full checklist over the new diff until a complete pass finds nothing. Fixes routinely introduce new hits (deleting a catch block can orphan an import).
