Forms, Actions, and Mutations

React Router 7 Framework Mode uses route actions for server-side mutations. Use <Form> for navigation-based submissions and fetcher.Form for mutations that should not navigate.

Route Action

import type { Route } from "./+types/products";
import { redirect } from "react-router";

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const name = formData.get("name");
  const tags = formData.getAll("tags");

  if (typeof name !== "string" || name.trim().length < 3) {
    return { error: "Name must contain at least 3 characters" };
  }

  const validTags = tags.filter(
    (tag): tag is string => typeof tag === "string"
  );

  const product = await createProduct({
    name: name.trim(),
    tags: validTags,
  });

  return redirect(`/products/${product.id}`);
}

Form Submission and Pending UI

import type { Route } from "./+types/products";
import { Form, useNavigation } from "react-router";

export default function Products({ actionData }: Route.ComponentProps) {
  const navigation = useNavigation();
  const submitting = navigation.state === "submitting";

  return (
    <Form method="post">
      <input name="name" placeholder="Product name" />

      <label>
        <input type="checkbox" name="tags" value="react" />
        React
      </label>

      <label>
        <input type="checkbox" name="tags" value="typescript" />
        TypeScript
      </label>

      {actionData?.error && <p role="alert">{actionData.error}</p>}

      <button type="submit" disabled={submitting}>
        {submitting ? "Creating..." : "Create"}
      </button>
    </Form>
  );
}

Non-Navigation Mutation

Use useFetcher() for deletes, favorites, toggles, and inline updates when the URL should not change.

import { useFetcher } from "react-router";

export function DeleteProduct({ id }: { id: string }) {
  const fetcher = useFetcher();
  const busy = fetcher.state !== "idle";

  return (
    <fetcher.Form method="post" action="/products/delete">
      <input type="hidden" name="id" value={id} />

      <button type="submit" disabled={busy}>
        {busy ? "Deleting..." : "Delete"}
      </button>

      {fetcher.data?.error && <p role="alert">{fetcher.data.error}</p>}
    </fetcher.Form>
  );
}

import type { Route } from "./+types/delete";

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const id = formData.get("id");

  if (typeof id !== "string" || !id) {
    return { error: "Product id is required" };
  }

  await deleteProduct(id);
  return { success: true };
}

Programmatic Submission

Use useSubmit() when code needs to trigger a route action.

import { useSubmit } from "react-router";

export function DeleteButton({ id }: { id: string }) {
  const submit = useSubmit();

  function handleDelete() {
    submit(
      { id },
      { method: "post", action: "/products/delete" }
    );
  }

  return <button onClick={handleDelete}>Delete</button>;
}

File Uploads

Use multipart/form-data for file submissions and validate the uploaded file.

import type { Route } from "./+types/upload";
import { Form, redirect } from "react-router";

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const file = formData.get("file");

  if (!(file instanceof File) || file.size === 0) {
    return { error: "A file is required" };
  }

  if (!file.type.startsWith("image/")) {
    return { error: "Only image files are allowed" };
  }

  await saveUploadedFile(file);
  return redirect("/uploads");
}

export default function Upload() {
  return (
    <Form method="post" encType="multipart/form-data">
      <input type="file" name="file" accept="image/*" />
      <button type="submit">Upload</button>
    </Form>
  );
}

Multiple Form Values

Use getAll() when a field can submit multiple values.

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const tags = formData.getAll("tags");

  const validTags = tags.filter(
    (tag): tag is string => typeof tag === "string"
  );

  if (validTags.length === 0) {
    return { error: "Select at least one tag" };
  }

  await saveTags(validTags);
  return redirect("/products");
}

<Form method="post">
  <label>
    <input type="checkbox" name="tags" value="react" />
    React
  </label>

  <label>
    <input type="checkbox" name="tags" value="typescript" />
    TypeScript
  </label>

  <button type="submit">Save</button>
</Form>

Revalidation

After an action completes, React Router automatically revalidates loader data for the affected route hierarchy.

export async function loader() {
  return { products: await getProducts() };
}

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const id = formData.get("id");

  if (typeof id !== "string") {
    return { error: "Invalid id" };
  }

  await updateProduct(id);
  return redirect("/products");
}

Keep loaders as the source of truth. Do not manually refetch after every action when normal revalidation already handles it.

Expected and Unexpected Errors

Return expected validation errors from the action. Handle unexpected failures with an ErrorBoundary.

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const email = formData.get("email");

  if (typeof email !== "string" || !email.includes("@")) {
    return { error: "Enter a valid email" };
  }

  await updateEmail(email);
  return redirect("/account");
}

import type { Route } from "./+types/account";

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <main>
      <h1>Something went wrong</h1>
      <p>{error instanceof Error ? error.message : "Unknown error"}</p>
    </main>
  );
}

Common Mistakes

Fetching route data with useEffect() instead of loaders.

Posting mutations with manual fetch() instead of actions.

Keeping server mutation logic in browser components.

Using <Form> when the mutation should not navigate.

Using useActionData() for fetcher submissions.

Using get() instead of getAll() for repeated fields.

Assuming every FormData value is a string.

Uploading files without multipart/form-data.

Manually refetching data after every action.

Managing pending state with unrelated local state.

Handling unexpected failures only inside normal components.

Verification

A mutation should use a route action, validate FormData, use <Form> or fetcher.Form appropriately, expose pending and expected error state, keep trusted mutation logic on the server, and rely on loader revalidation for refreshed data.

Run the project checks:

npm run typecheck
npm run build

Fix every failure and rerun until clean.