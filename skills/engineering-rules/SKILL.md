---
name: engineering-rules
description: Use when writing, modifying, or reviewing code in any language or framework. Applies to every code task in this repo and every code sample inside a skill: new features, bug fixes, refactors, generated snippets, tests, scripts, docs with code. Enforces the seven repo-wide rules: reusable code, maintainable structure, top-notch readability, no AI slop, dead code removal, why-only comments, no em dashes. Invoke for implementing changes, self-reviewing a diff, cleaning up generated code, writing reference examples, or reviewing a PR.
license: MIT
metadata:
  version: "0.1.0"
  category: core
  frameworks: language-agnostic
  triggers: code quality, refactor, cleanup, review, readability, naming, dead code, comments, duplication, reuse, maintainability, ai slop, diff review, self-review
  related: react-expert, nestjs-expert, go-expert, flutter-expert, playwright-expert
---

# Engineering Rules

Turns Claude into the repo's staff engineer: every diff it produces already passes the review these seven rules describe.

## When to Use This Skill

- Implementing any feature, fix, or refactor, in any language
- Self-reviewing a diff before commit or PR
- Cleaning up AI-generated or copy-pasted code
- Writing code samples for skills, docs, or references
- Reviewing someone else's PR against repo standards
- Deciding whether to extract, inline, or delete code

## Core Workflow

1. **Search before writing.** Grep the codebase for an existing helper, component, or util that already does the job (search by domain nouns and verbs, not just exact names). Reuse or extend it; only write new code when nothing fits.
2. **Implement.** Small single-responsibility units, follow the project's existing structure and idioms, configuration over hardcoded values, no new global state.
3. **Run the rules checklist over the diff** (the seven rules below, each is concrete and checkable):
   - Rule 1, Reusable: no copy-paste variants; shared shape appearing a second time is extracted.
   - Rule 2, Maintainable: units small, module boundaries clear, dependencies point one way, nothing hardcoded that belongs in config.
   - Rule 3, Readable: intention-revealing names (no `data`, `tmp`, `handle`, `process2`), early returns over nesting, reads top-down.
   - Rule 4, No AI slop: scan the diff against `references/ai-slop-checklist.md` item by item.
   - Rule 5, Dead code: everything your change made unreachable is deleted; zero commented-out code; orphaned exports removed.
   - Rule 6, Comments: every comment states a non-obvious why; any comment narrating what gets deleted or the code gets rewritten.
   - Rule 7, No em dashes: `grep -rn "$(printf '\xe2\x80\x94')"` over changed files, in code, comments, docs, and commit messages; returns nothing.
4. **Fix all violations and re-run the checklist until clean.** A single pass is never assumed sufficient; fixes for one rule often introduce violations of another.
5. **Run the project's formatter and linter** (e.g. `prettier --check .` + `eslint .`, `ruff format --check && ruff check`, `gofmt -l . && go vet ./...`); fix every reported issue and re-run until clean.
6. **Verify behavior.** Run the project's tests for the touched area; debug failures before declaring done.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Reuse and structure (rules 1-2) | `references/reusability-and-structure.md` | Adding a helper/util, seeing duplicated logic, deciding module boundaries or where code lives |
| Readability and naming (rule 3) | `references/readability-and-naming.md` | Naming anything, untangling nested conditionals, code that needs a comment to be understood |
| AI slop checklist (rule 4) | `references/ai-slop-checklist.md` | Self-reviewing any diff, cleaning generated code, reviewing a PR |
| Comments, dead code, em dashes (rules 5-7) | `references/comments-and-dead-code.md` | Writing or deleting comments, removing a feature/flag/branch, touching a file with leftover code |

## Key Patterns

**Extract on the second occurrence, not the first, not the third:**

```typescript
// Two call sites already format money the same way: extract now.
const formatCents = (cents: number, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);
```

**Early return instead of nesting:**

```python
def ship(order: Order) -> Shipment:
    if not order.items:
        raise EmptyOrderError(order.id)
    if order.status is not Status.PAID:
        raise UnpaidOrderError(order.id)
    return carrier.dispatch(order)
```

**Comment carries the why, code carries the what:**

```go
// Stripe retries webhooks for 3 days; dedupe on event ID or refunds double-apply.
if store.SeenEvent(evt.ID) {
    return nil
}
```

## Common Mistakes

- Writing a new helper without searching first. The repo almost always has one; grep for the domain term (`grep -rn "formatCurrency\|toMoney"`) before writing line one.
- Extracting an abstraction for a single caller. One implementation needs no interface, factory, or base class; wait for the second concrete use.
- "Cleaning up" by commenting code out. Delete it; version control is the archive. Commented-out code fails review outright.
- Adding try/catch that only logs and re-throws, or swallows. Catch only where you can handle or add context; otherwise let it propagate.
- Narrating comments (`// increment counter`) and section markers (`// helpers`). Both are deleted on sight; restructure the code instead.
- Defensive null checks after calls whose types guarantee non-null. Trust the type system; a gratuitous check hides the real contract.
- Leaving the checklist at one pass. A rename fixes rule 3 but can orphan an export (rule 5); loop until a full pass reports nothing.
