# Comments, Dead Code, and Em Dashes (Rules 5-7)

Rule 5: every touch of a file removes the code your change killed.
Rule 6: comments exist only to answer "why", never "what".
Rule 7: no em dashes anywhere, ever.

## Rule 5: Dead Code Removal on Every Iteration

When your change makes code unreachable, deleting it is part of the change, not a follow-up.

### Delete what your change orphaned

```typescript
// Change: checkout now always uses the v2 tax service.

// Bad: the old path left behind "for reference"
function calculateTax(order: Order): Money {
  return taxServiceV2.calculate(order);
}
function legacyCalculateTax(order: Order): Money {  // no callers remain
  return order.total.times(0.08);
}

// Good: the diff that adds v2 also deletes legacyCalculateTax,
// its tests, and its export from index.ts
```

After removing a function, chase the chain: its now-unused imports, the helpers only it called, the types only it referenced, the fixtures only its tests used.

```bash
# Find orphaned exports after a removal (TS example)
npx knip            # or: npx ts-prune
# Python
ruff check --select F401,F811,F841 .
# Go: the compiler already rejects unused imports and locals; also run
staticcheck ./...   # catches unused exported identifiers (U1000)
```

### No commented-out code, ever

```python
# Bad
def totals(orders):
    # old approach, keeping just in case
    # result = 0
    # for o in orders:
    #     result += o.amount
    return sum(o.amount for o in orders)

# Good
def totals(orders):
    return sum(o.amount for o in orders)
```

Version control remembers every deleted line: `git log -S "old approach" -- path/file.py` resurrects it in seconds. A commented-out block is a lie that says "this might come back"; it never does, and every reader pays to skip it.

### Remove flags and branches that can no longer execute

```typescript
// The rollout finished: ENABLE_NEW_PRICING is true in every environment.

// Bad: the flag and the dead branch outlive the rollout
if (config.ENABLE_NEW_PRICING) {
  return newPricing(cart);
} else {
  return oldPricing(cart);   // can never run again
}

// Good: flag deleted from config, branch inlined, oldPricing() and its tests deleted
return newPricing(cart);
```

The same applies to environment checks for retired environments, version guards below the minimum supported version, and `if (false)` blocks however they are spelled.

## Rule 6: Comments Only for "Why"

A comment is justified only when it states a non-obvious constraint, tradeoff, or decision rationale that the code cannot express. Everything else is deleted.

### The three comments worth writing

```go
// Constraint imposed from outside:
// Upstash caps pipelines at 1000 commands; batch or the whole pipeline 500s.
for _, chunk := range chunks(keys, 1000) { ... }
```

```python
# Tradeoff chosen deliberately:
# O(n^2) is fine here: n is bounded at 50 by the API page size,
# and the sorted-merge alternative doubled the code for no measurable gain.
for a in items:
    for b in items:
        ...
```

```typescript
// Decision rationale a future refactorer needs:
// Intentionally NOT debounced: compliance requires every keystroke logged
// (audit finding AR-114), so do not "optimize" this into a debounce.
onKeyStroke(logKeystroke);
```

### The comments that are always deleted

```python
# Narration of the next line
i += 1  # increment i
users = load_users()  # load users from the database

# Section markers
# ---------- helpers ----------
# ============ MAIN ============

# Ownerless TODOs
# TODO: clean this up
# FIXME: hack

# Restated signatures (docstring that adds zero information)
def get_user(user_id: str) -> User:
    """Gets a user by user id."""
```

Allowed TODO form: `# TODO(owner, #482): drop after the v2 migration completes`. Owner plus tracking issue, or it does not ship.

### If a comment explains "what", rewrite the code

The comment is a signal the code failed; fix the code, then delete the comment.

```typescript
// Bad: comment doing the code's job
// check if the user is eligible for the discount
if (u.t === "p" && u.since < cutoff && !u.d) {
  applyDiscount(u);
}

// Good: the code says it, so no comment exists
const eligibleForLoyaltyDiscount =
  user.tier === "premium" && user.memberSince < loyaltyCutoff && !user.hasActiveDiscount;
if (eligibleForLoyaltyDiscount) {
  applyDiscount(user);
}
```

```python
# Bad
# convert to cents to avoid float issues
a = int(p * 100)

# Good: the name carries the what; a comment remains only if there is a why
price_cents = int(price_dollars * 100)
```

Test for every comment in the diff: cover the comment; if the code alone tells the same story, delete the comment; if not, ask whether renaming or extracting would make it tell the story, and only keep the comment when the answer is a genuine external constraint, tradeoff, or decision.

## Rule 7: No Em Dashes

The em dash character is banned everywhere: code, string literals, comments, docs, commit messages, generated output, and skill files. CI rejects it.

```markdown
Bad:  The retry loop <em dash> capped at three attempts <em dash> backs off exponentially.
Good: The retry loop, capped at three attempts, backs off exponentially.
Good: The retry loop backs off exponentially. It is capped at three attempts.
Good: Retry loop: three attempts, exponential backoff.
```

Substitutions by intent:

| You wanted | Use instead |
|------------|-------------|
| Parenthetical aside | Paired commas, or parentheses |
| Dramatic pause or pivot | A period and a new sentence |
| Label-to-detail | A colon |
| Range or compound word | A hyphen (`pages 3-7`, `fix-until-clean`) |

Sweep before every commit:

```bash
# The character is written as its UTF-8 bytes so this file stays clean itself.
EMDASH="$(printf '\xe2\x80\x94')"
grep -rn "$EMDASH" . --include='*.ts' --include='*.tsx' --include='*.py' \
  --include='*.go' --include='*.md' --include='*.json' | grep -v node_modules
git log -1 --format=%B | grep "$EMDASH" && echo "em dash in commit message"
```

Both greps must return nothing. Em dashes commonly sneak in via pasted prose and generated text, so run the sweep after any copy-paste from docs or LLM output.

## Checklist for This Reference

- [ ] Every function/branch made unreachable by this diff is deleted, with its imports, helpers, types, and tests
- [ ] Zero commented-out code in the diff
- [ ] Fully-rolled-out feature flags and their dead branches removed
- [ ] Unused-export scan run after any removal
- [ ] Every surviving comment states a constraint, tradeoff, or rationale
- [ ] No narration, section markers, restated docstrings, or ownerless TODOs
- [ ] Em dash grep over changed files and the commit message returns nothing
