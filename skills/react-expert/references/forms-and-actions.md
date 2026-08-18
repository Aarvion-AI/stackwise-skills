# Forms, Server Actions, and Mutations

## Server actions are public endpoints

Every exported function in a `"use server"` file (or with an inline directive) becomes a POST endpoint reachable by anyone who finds its ID. Therefore every action must:

1. **Authenticate/authorize inside the action** - never trust that the UI gated it.
2. **Validate input with a schema** - `FormData` is attacker-controlled.
3. Return serializable data only.

```ts
// app/posts/actions.ts
"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth"; // module imports "server-only"

const createPostSchema = z.object({
  title: z.string().min(1).max(200),
  body: z.string().min(1),
});

export type ActionState = {
  error?: string;
  fieldErrors?: Record<string, string[]>;
};

export async function createPost(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const session = await getSession();
  if (!session) return { error: "Not signed in" };

  const parsed = createPostSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return { fieldErrors: parsed.error.flatten().fieldErrors };
  }

  const post = await db.post.create({
    data: { ...parsed.data, authorId: session.userId },
  });

  revalidatePath("/posts");
  redirect(`/posts/${post.id}`); // throws - must be OUTSIDE try/catch
}
```

`redirect()` and `notFound()` work by throwing; wrapping them in `try/catch` swallows the control flow. Put them after the try block, or rethrow with `unstable_rethrow`.

## `useActionState` (React 19)

Replaces the removed ReactDOM `useFormState`. Import from `react`:

```tsx
"use client";
import { useActionState } from "react";
import { createPost, type ActionState } from "./actions";

export function PostForm() {
  const [state, formAction, isPending] = useActionState<ActionState, FormData>(
    createPost,
    {},
  );
  return (
    <form action={formAction}>
      <input name="title" aria-invalid={!!state.fieldErrors?.title} />
      {state.fieldErrors?.title && <p role="alert">{state.fieldErrors.title[0]}</p>}
      <textarea name="body" />
      <button disabled={isPending}>{isPending ? "Publishing…" : "Publish"}</button>
      {state.error && <p role="alert">{state.error}</p>}
    </form>
  );
}
```

Notes:

- The action signature gains a first `prevState` parameter when used with `useActionState` - a plain `<form action={serverAction}>` (no hook) takes only `(formData)`.
- `isPending` from the tuple covers the whole form. For a submit button shared across forms, `useFormStatus` (from `react-dom`) must be called in a **child component of the `<form>`**, not in the component that renders the form:

```tsx
"use client";
import { useFormStatus } from "react-dom";
export function SubmitButton({ children }: { children: React.ReactNode }) {
  const { pending } = useFormStatus();
  return <button disabled={pending}>{pending ? "…" : children}</button>;
}
```

- React 19 resets uncontrolled form fields after a successful action submit. Keep user input on validation failure by echoing values back in the returned state and setting `defaultValue={state.values?.title}`.
- Progressive enhancement: `<form action={serverAction}>` submits even before hydration. Keep field `name`s meaningful and avoid requiring JS-only state for the happy path.

## Binding arguments

Hidden inputs work but are user-editable. For trusted values (IDs the user shouldn't change), prefer `bind` - bound arguments are encrypted/signed by Next:

```tsx
// server component
import { updatePost } from "./actions";
const updateWithId = updatePost.bind(null, post.id);
return <EditForm action={updateWithId} />;
// action: export async function updatePost(id: string, prev: State, formData: FormData)
```

Still authorize inside the action - bind prevents tampering, not replay by another signed-in user.

## Non-form invocation

Actions are just async functions on the client; call them from handlers wrapped in a transition so you get pending state and non-blocking UI:

```tsx
"use client";
import { useTransition } from "react";
import { deletePost } from "./actions";

function DeleteButton({ id }: { id: string }) {
  const [isPending, startTransition] = useTransition();
  return (
    <button
      disabled={isPending}
      onClick={() =>
        startTransition(async () => {
          const res = await deletePost(id);
          if (res?.error) toast.error(res.error);
        })
      }
    >
      Delete
    </button>
  );
}
```

Do not call server actions in `useEffect` for data **reads** - actions run serially (POST, no caching); reads belong in Server Components or TanStack Query.

## Optimistic updates with `useOptimistic`

```tsx
"use client";
import { useOptimistic } from "react";
import { addTodo } from "./actions";

export function Todos({ todos }: { todos: Todo[] }) {
  const [optimisticTodos, addOptimistic] = useOptimistic(
    todos,
    (current, newTitle: string) => [
      ...current,
      { id: "tmp", title: newTitle, pending: true },
    ],
  );

  async function formAction(formData: FormData) {
    const title = formData.get("title") as string;
    addOptimistic(title);          // must be inside an action/transition
    await addTodo(title);          // revalidatePath in the action refreshes real data
  }

  return (
    <form action={formAction}>
      <input name="title" />
      <ul>
        {optimisticTodos.map((t) => (
          <li key={t.id} style={{ opacity: t.pending ? 0.5 : 1 }}>{t.title}</li>
        ))}
      </ul>
    </form>
  );
}
```

The optimistic state automatically reverts to the canonical prop once the action settles and the route revalidates. Calling `addOptimistic` outside a transition/action warns and won't revert correctly.

## Revalidation after writes

- `revalidatePath("/posts")` - refresh a route's cached data.
- `revalidateTag("posts")` - refresh every fetch tagged `{ next: { tags: ["posts"] } }`; prefer tags when multiple routes show the data.
- Returning fresh data from the action and calling `router.refresh()` client-side is the fallback when the write happens outside Next's cache model.
- With TanStack Query in the mix, also `queryClient.invalidateQueries({ queryKey: [...] })` in the mutation's `onSuccess` - `revalidatePath` does not touch the Query cache.

## Error handling contract

Return errors as data (as in the schema example) for expected failures - thrown errors from actions surface to the nearest `error.tsx` boundary and lose field-level detail. Reserve throws for unexpected/fatal errors. Never leak internal error messages: log the original, return a generic string.
