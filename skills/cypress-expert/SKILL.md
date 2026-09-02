---
name: cypress-expert
description: Use when writing or fixing Cypress tests in a Cypress project - cypress.config.ts, cypress/e2e, cypress/component, cy commands, Cypress fixtures, or Cypress Cloud. Builds reliable browser and component tests, debugs flake, controls network dependencies, and wires CI evidence. Invoke for adding E2E coverage, component testing, custom commands, migration from brittle selectors, or CI parallelization.
license: MIT
metadata:
  version: "0.1.0"
  category: qa
  frameworks: "Cypress 13+, TypeScript, Cypress Cloud"
  triggers: cypress, cypress.config, cy., cypress/e2e, cypress/component, custom commands, fixtures, intercept, clock, component testing, Cypress Cloud
  related: react-expert, vue-expert, playwright-expert
---

# Cypress Expert

Turns Claude into a senior Cypress engineer who proves browser behavior with user-facing queries, deterministic command chains, controlled boundaries, and actionable CI artifacts.

## Safety and Authorization

- Start with local, read-only inspection and the smallest relevant verification commands.
- Ask for explicit user approval before installing software, accessing accounts or secrets, uploading artifacts, using paid services, changing shared or production systems, applying migrations, or deploying infrastructure.
- Before an approved consequential action, show the exact target, expected impact, cost implications, and rollback or recovery path.
- Never weaken tests, security controls, or approval gates to make a workflow pass. Redact secrets and personal data from screenshots, videos, logs, and recordings.

## When to Use This Skill

- Add or extend Cypress E2E coverage for a feature or bug fix
- Build Cypress component tests for React or Vue components
- Replace brittle selectors, arbitrary waits, and shared mutable state
- Stub APIs and assert request behavior with `cy.intercept`
- Diagnose retries, screenshots, videos, and CI-only failures
- Configure Cypress Cloud recording, parallelization, or browser matrices

## Core Workflow

1. **Analyze** - Read `cypress.config.ts`, support files, fixtures, package scripts, and nearby specs. Identify the base URL, browser targets, test isolation settings, and the real user journey.
2. **Specify the behavior** - Reproduce the bug or write the smallest journey that demonstrates the feature. Define stable visible outcomes and required API boundaries before editing.
3. **Implement** - Use Testing Library queries or stable `data-cy` attributes, keep commands chainable, isolate external services with `cy.intercept`, and use `cy.session` only for reusable authenticated state. Load the relevant reference before using an unfamiliar pattern.
4. **Verify types and lint** - Run `npx tsc --noEmit` and the project's lint command; fix every reported issue and re-run until clean.
5. **Run the focused test** - Run `npx cypress run --spec <spec> --browser <browser>`; fix every failure and re-run until passing. Use screenshots, videos, command logs, and the Cypress runner to find the root cause instead of adding waits.
6. **Prove stability** - Run the focused spec repeatedly or through the configured CI command; fix every intermittent failure and re-run until all repetitions pass. Then run the affected suite and confirm artifacts are reviewable.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Configuration and test structure | `references/configuration-and-structure.md` | Creating `cypress.config.ts`, choosing E2E versus component tests, or defining support and fixture boundaries |
| Queries, commands, and network control | `references/queries-commands-network.md` | Writing selectors, custom commands, `cy.intercept`, aliases, retries, or authentication helpers |
| CI, flake, and artifacts | `references/ci-and-flake.md` | Debugging CI-only failures, enabling recordings, parallelizing runs, or reviewing Cypress Cloud configuration |

## Key Patterns

**Assert the UI after an intercepted request:**

```ts
cy.intercept("GET", "/api/orders", { fixture: "orders.json" }).as("getOrders");
cy.visit("/orders");
cy.wait("@getOrders").its("response.statusCode").should("eq", 200);
cy.findByRole("heading", { name: "Orders" }).should("be.visible");
```

**Use a scoped, user-facing query:**

```ts
cy.findByRole("row", { name: /invoice-2026-08/ })
  .findByRole("button", { name: "Approve" })
  .click();
```

## Common Mistakes

- **Using `cy.wait(2000)`.** Wait on a request alias or assert the UI condition that signals readiness.
- **Relying on CSS structure.** Prefer accessible queries; add a stable `data-cy` attribute when no user-facing handle exists.
- **Sharing state between tests.** Reset data or create isolated records because test order and retries must not change outcomes.
- **Overusing `cy.session`.** Cache only stable login setup; tests about login must exercise the login UI directly.
- **Stubbing every request.** Keep the important application boundary real and stub only unstable, external, expensive, or deliberately exceptional dependencies.