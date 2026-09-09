Errors, Testing, and Deployment

React Router 7 route errors should be handled at the route boundary. Test loaders, actions, and route behavior with the router's testing utilities, then verify the production build before deployment.

Route ErrorBoundary

Use a route-level ErrorBoundary for unexpected loader, action, and rendering failures.

import type { Route } from "./+types/products";

export function ErrorBoundary({
  error,
}: Route.ErrorBoundaryProps) {
  return (
    <main>
      <h1>Something went wrong</h1>
      <p>
        {error instanceof Error
          ? error.message
          : "Unknown error"}
      </p>
    </main>
  );
}

Verify:

npm run typecheck

Fix all reported issues and rerun until clean.

Do not catch every exception in the component just to render an error message. Let unexpected route failures reach the route error boundary.

Expected Action Errors

Use returned action data for expected validation failures caused by user input.

import type { Route } from "./+types/products";
import { Form } from "react-router";

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const name = formData.get("name");

  if (typeof name !== "string" || !name.trim()) {
    return { error: "Name is required" };
  }

  await createProduct({ name: name.trim() });
  return { success: true };
}

export default function ProductForm({
  actionData,
}: Route.ComponentProps) {
  return (
    <Form method="post">
      <input name="name" />

      {actionData?.error && (
        <p role="alert">{actionData.error}</p>
      )}

      <button type="submit">Create</button>
    </Form>
  );
}

Verify:

npm run typecheck

Fix all reported issues and rerun until clean.

Keep expected validation failures separate from unexpected exceptions.

Loader Error Boundary

A loader failure can be handled by the same route-level boundary.

import type { Route } from "./+types/products";

export async function loader({ params }: Route.LoaderArgs) {
  const product = await getProduct(params.productId);

  if (!product) {
    throw new Response("Product not found", {
      status: 404,
    });
  }

  return { product };
}

export function ErrorBoundary({
  error,
}: Route.ErrorBoundaryProps) {
  return (
    <main>
      <h1>Unable to load product</h1>
      <p>
        {error instanceof Error
          ? error.message
          : "Product could not be loaded"}
      </p>
    </main>
  );
}

Verify:

npm run typecheck

Fix all reported issues and rerun until clean.

Do not duplicate loader error handling across every child component.

Testing Route Components

Components that use React Router APIs need router context in tests. createRoutesStub can provide that context.

import { createRoutesStub } from "react-router";
import { render, screen } from "@testing-library/react";
import Product from "./Product";

test("renders product data", () => {
  const Stub = createRoutesStub([
    {
      path: "/products/:productId",
      Component: Product,
      loader: () => ({
        product: {
          id: "1",
          name: "Keyboard",
        },
      }),
    },
  ]);

  render(
    <Stub initialEntries={["/products/1"]} />
  );

  expect(
    screen.getByText("Keyboard")
  ).toBeInTheDocument();
});

Verify:

npm test

Fix failing tests and rerun until clean.

Use route-level integration or end-to-end tests when the behavior depends on actual loaders, actions, redirects, or navigation.

Testing Actions

Test action validation and successful mutations as separate cases.

import { action } from "./route";

test("rejects missing name", async () => {
  const request = new Request("http://localhost/products", {
    method: "POST",
    body: new URLSearchParams(),
  });

  const result = await action({
    request,
    params: {},
    context: {},
  } as any);

  expect(result).toEqual({
    error: "Name is required",
  });
});

Verify:

npm test

Fix failures and rerun until clean.

Test Mutations and Revalidation

A mutation test should cover the result that matters to the user: validation, success, redirect, or updated data.

test("creates a product", async () => {
  const request = new Request("http://localhost/products", {
    method: "POST",
    body: new URLSearchParams({
      name: "Keyboard",
    }),
  });

  const result = await action({
    request,
    params: {},
    context: {},
  } as any);

  expect(result).toBeDefined();
});

For full route behavior, prefer an integration or end-to-end test that submits the form and verifies the resulting UI.

Verify:

npm test

Fix failures and rerun until clean.

Build Verification

Before deployment, create a production build using the project's configured scripts.

npm run build

If the build fails, fix every reported issue and rerun until it passes.

If the project exposes a start or preview command, run the production output locally and verify a representative route:

npm run start

Use the script actually defined by the project rather than assuming a framework-specific command.

Deployment Checks

Before deploying:

Confirm the production build passes.

Confirm required environment variables are configured.

Keep server-only secrets out of browser modules.

Confirm actions can reach their database or API dependencies.

Verify a representative loader, form submission, redirect, and error boundary.

Run:

npm run typecheck
npm test
npm run build

Fix every failure and rerun until all checks pass.

Common Mistakes

Catching unexpected route failures inside every component instead of using ErrorBoundary.

Returning successful mutation data when the user should be redirected.

Treating validation errors as unexpected application crashes.

Testing router-dependent components without router context.

Testing only rendering while ignoring loaders, actions, redirects, and mutation behavior.

Introducing a second test framework when the repository already has one.

Deploying without running the production build.

Exposing server-only secrets through browser modules.

Assuming the deployment environment has the same environment variables as local development.

Verifying only the happy path and never testing invalid input or route failures.

Final Verification

Run the project's checks before completing the change:

npm run typecheck
npm test
npm run build

Fix every failure and rerun until all checks pass.