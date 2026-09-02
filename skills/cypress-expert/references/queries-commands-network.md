# Cypress Queries, Commands, and Network Control

## Query priority

Use queries in this order:

1. `findByRole` with an accessible name
2. `findByLabelText` or `findByPlaceholderText`
3. `findByText` for user-visible copy
4. `get` with a stable `data-cy` attribute when no accessible handle exists

Prefer `findBy*` for content that appears after an async transition. Cypress retries the query and assertion together.

```ts
cy.findByRole("button", { name: "Save" }).click();
cy.findByRole("status").should("contain.text", "Saved");
```

## Custom commands

Commands should represent a meaningful user or test boundary, not a selector shortcut:

```ts
declare global {
  namespace Cypress {
    interface Chainable {
      loginAs(role: "admin" | "viewer"): Chainable<void>;
    }
  }
}

Cypress.Commands.add("loginAs", (role) => {
  cy.request("POST", "/api/test-login", { role }).then(({ body }) => {
    window.localStorage.setItem("session", body.session);
  });
});
```

Do not hide assertions or navigation inside a generic command. Name commands after intent and document unusual preconditions.

## Network control

Declare intercepts before the action that triggers them:

```ts
cy.intercept("POST", "/api/orders", { statusCode: 500, body: { error: "timeout" } }).as("saveOrder");
cy.findByRole("button", { name: "Save order" }).click();
cy.wait("@saveOrder").its("request.body").should("include", { orderId: "order-1" });
cy.findByRole("alert").should("contain.text", "Try again");
```

Use `routeHandler` when the response must depend on request data. Assert both the request contract and the visible result when the test owns that boundary.

## Aliases and retries

Aliases are for a specific request, subject, or fixture. Avoid broad aliases such as `@api`. Keep each alias close to its use so the test reads as one journey.

Do not add `cy.wait` for time. Use an alias for network readiness or a retryable assertion for UI readiness. A passing retry after a failure is evidence to investigate, not proof of stability.

## Authentication

Use `cy.session` for a deterministic login setup that is expensive and unrelated to the behavior under test:

```ts
cy.session(["admin"], () => {
  cy.request("POST", "/api/test-login", { role: "admin" });
});
```

Validate the session with a lightweight check when it can expire. Keep login UI coverage outside the cached setup.

## Verification

Run the changed spec with `npx cypress run --spec <spec>`; fix every selector, command-chain, and intercept failure and re-run until passing. Do not replace a failing assertion with a weaker assertion.