---
name: remix-expert
description: Use when working in a React Router 7 / Remix v2 framework-mode codebase with app/routes, loaders and actions, react-router.config.ts, useLoaderData / useActionData, Form, useNavigation, Outlet, or ErrorBoundary. Builds and refactors route modules, server data loading, mutations, pending UI, nested routing, and route-level error handling. Invoke for adding routes, replacing unnecessary useEffect data fetching, implementing Form/action mutations, fixing nested routing or revalidation bugs, and debugging route errors.
license: MIT
metadata:
  version: "0.1.0"
  category: frontend
  frameworks: "React Router 7 / Remix v2"
  triggers: react router 7, remix, remix v2, app/routes, routes.ts, react-router.config, loader, action, useLoaderData, useActionData, Form, useNavigation, Outlet, ErrorBoundary
  related: react-expert, playwright-expert
---

# Remix Expert

Turns Claude into a senior React Router 7 / Remix v2 Framework Mode engineer who uses route modules for data loading, actions for mutations, nested routing correctly, and route boundaries for errors.

## When to Use This Skill

- Add or modify routes and route modules in a React Router 7 Framework Mode project
- Load server data with `loader` instead of unnecessary component-level `useEffect` fetching
- Implement mutations with `action`, `<Form>`, `useSubmit`, or `useFetcher`
- Fix nested routes, layouts, dynamic params, `<Outlet>`, or outlet context
- Add pending UI with `useNavigation` or fetcher state
- Handle route failures with `ErrorBoundary`
- Diagnose stale route data, incorrect revalidation, or hydration behavior

## Core Workflow

1. **Analyze** - Inspect `package.json`, `app/routes.ts`, `react-router.config.ts`, the target route module, parent routes, and existing tests. Confirm the project's React Router version and Framework Mode setup. Trace the route hierarchy before changing code.

2. **Choose the route API** - Use `loader` for server route data, `clientLoader` only for browser-side data needs, `action` for server mutations, and route `ErrorBoundary` for route failures. Prefer generated `Route.ComponentProps` types in Framework Mode when available.

3. **Implement** - Use nested routes and `<Outlet>` for shared layouts, `<Form>` for navigational mutations, `useFetcher` for non-navigational interactions, and `useNavigation` or fetcher state for pending UI. Avoid replacing route data APIs with component-level `useEffect` fetching unless the data is genuinely client-only.

4. **Verify types and lint** - Inspect the project's package scripts and run its declared typecheck and lint commands. Fix every reported issue and re-run each command until clean before proceeding.

5. **Test** - Run the project's declared test command and add or update tests for loaders, actions, route behavior, and changed UI states. Fix every failure and re-run until clean.

6. **Prove it works** - Run the project's React Router build command or equivalent. Fix all build errors and re-run until clean. Exercise the changed route in development and verify navigation, pending UI, mutations, revalidation, and relevant error boundaries.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic                                                  | Reference                                     | Load When                                                                                |
| ------------------------------------------------------ | --------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Routes, loaders, nested layouts, params, and Outlet    | `references/routing-and-loaders.md`           | Adding routes, loading data, changing route hierarchy, or using params and Outlet        |
| Forms, actions, fetchers, pending UI, and revalidation | `references/forms-actions-and-mutations.md`   | Implementing mutations, forms, fetchers, validation, or revalidation behavior            |
| Error boundaries, testing, builds, and verification    | `references/errors-testing-and-deployment.md` | Handling route errors, writing tests, debugging builds, or verifying production behavior |

## Key Patterns

**Typed route module with a server loader:**

```tsx
import type { Route } from "./+types/product";

export async function loader({ params }: Route.LoaderArgs) {
  const product = await getProduct(params.id);

  if (!product) {
    throw new Response("Not Found", { status: 404 });
  }

  return product;
}

export default function Product({ loaderData }: Route.ComponentProps) {
  return <h1>{loaderData.name}</h1>;
}
```
## Common Mistakes

- Using `useEffect()` for route data instead of loaders.
- Using manual `fetch()` POST requests instead of route actions.
- Using client-side form state when `<Form>` and actions provide the required workflow.
- Missing nested route and `<Outlet>` context when working with child routes.
- Handling route failures inside components instead of route `ErrorBoundary`.
- Mutating client state without allowing route data to revalidate.