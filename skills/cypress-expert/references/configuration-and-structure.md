# Cypress Configuration and Structure

## Configuration baseline

Use the current Cypress configuration API and keep E2E and component concerns explicit:

```ts
import { defineConfig } from "cypress";

export default defineConfig({
  e2e: {
    baseUrl: "http://localhost:3000",
    specPattern: "cypress/e2e/**/*.cy.{js,jsx,ts,tsx}",
    supportFile: "cypress/support/e2e.ts",
    setupNodeEvents(on, config) {
      return config;
    },
  },
  component: {
    devServer: {
      framework: "react",
      bundler: "vite",
    },
    specPattern: "cypress/component/**/*.cy.{js,jsx,ts,tsx}",
    supportFile: "cypress/support/component.ts",
  },
});
```

## Directory roles

- `cypress/e2e/` contains complete user journeys.
- `cypress/component/` contains isolated component behavior and states.
- `cypress/support/e2e.ts` loads E2E commands and global hooks.
- `cypress/support/component.ts` loads component mounts and component-only commands.
- `cypress/fixtures/` stores small deterministic response bodies.
- `cypress/support/commands.ts` contains narrowly named reusable commands.

## Test boundary

Use E2E tests for routing, auth integration, server rendering, persistence, and cross-component journeys.

Use component tests for loading, error, empty, interaction, and accessibility states that do not need a real server.

Do not move a test to component testing merely to avoid fixing a broken integration. The test boundary should reflect the risk being proven.

## Scripts

```json
{
  "scripts": {
    "cy:open": "cypress open",
    "cy:run": "cypress run",
    "cy:e2e": "cypress run --e2e",
    "cy:component": "cypress run --component",
    "cy:verify": "cypress verify"
  }
}
```

Run `cypress verify` after installing or upgrading Cypress. Run the focused spec before the full suite.

## Node event rules

Use `setupNodeEvents` for filesystem tasks, preprocessor wiring, and task registration. Keep browser assertions and application behavior in the spec or support layer. Return the config object when it is unchanged so environment resolution remains predictable.

## TypeScript

Include Cypress types in the test tsconfig, keep application and test compiler settings deliberate, and type custom command arguments and return values. Do not use `any` to hide command-chain type errors.

## Verification

Run `npx cypress run --e2e --spec cypress/e2e/<name>.cy.ts`; fix all failures and re-run until passing. For component work, use `npx cypress run --component --spec cypress/component/<name>.cy.ts` and apply the same loop.