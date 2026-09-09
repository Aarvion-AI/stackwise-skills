# Routing and Loaders

React Router 7 Framework Mode uses route configuration and route modules for URL matching, nested layouts, server data loading, and route-level errors.

## Define routes

```tsx
import {
  type RouteConfig,
  index,
  route,
} from "@react-router/dev/routes";

export default [
  index("./home.tsx"),
  route("products", "./products.tsx"),
  route("products/:productId", "./product.tsx"),
] satisfies RouteConfig;
```

Use `:param` for dynamic segments.

## Nested routes with Outlet

```tsx
import { Outlet } from "react-router";

export default function DashboardLayout() {
  return (
    <main>
      <nav>Dashboard</nav>
      <Outlet />
    </main>
  );
}
```

Use `<Outlet />` to render the matching child route. Keep shared layouts in the route hierarchy instead of manually checking the pathname.

## Generated route types

```tsx
import type { Route } from "./+types/product";

export async function loader({ params }: Route.LoaderArgs) {
  if (!params.productId) {
    throw new Response("Missing product ID", { status: 400 });
  }

  const product = await getProduct(params.productId);

  if (!product) {
    throw new Response("Product not found", { status: 404 });
  }

  return { product };
}

export default function Product({ loaderData }: Route.ComponentProps) {
  return <h1>{loaderData.product.name}</h1>;
}
```

Prefer generated `Route.*` types for route arguments and component props.

## Load data with loader

```tsx
import type { Route } from "./+types/products";

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const query = url.searchParams.get("q") ?? "";

  return {
    query,
    products: await searchProducts(query),
  };
}

export default function Products({ loaderData }: Route.ComponentProps) {
  return (
    <main>
      <h1>Products</h1>
      <p>{loaderData.query}</p>
      {loaderData.products.map((product) => (
        <article key={product.id}>{product.name}</article>
      ))}
    </main>
  );
}
```

Use `loader` for server-owned data required by a route.

## Avoid useEffect for route data

Avoid fetching route-owned data in a component:

```tsx
useEffect(() => {
  fetch("/api/products")
    .then((response) => response.json())
    .then(setProducts);
}, []);
```

Prefer a route loader:

```tsx
export async function loader() {
  return {
    products: await getProducts(),
  };
}
```

Loaders keep route data connected to navigation, errors, and revalidation.

## Read dynamic parameters

For:

```tsx
route("products/:productId", "./product.tsx")
```

access the parameter through the loader:

```tsx
export async function loader({ params }: Route.LoaderArgs) {
  const productId = params.productId;

  if (!productId) {
    throw new Response("Missing product ID", { status: 400 });
  }

  return {
    product: await getProduct(productId),
  };
}
```

Do not manually parse `window.location.pathname`.

## Use URL search parameters

```tsx
export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const page = Number(url.searchParams.get("page") ?? "1");

  if (!Number.isInteger(page) || page < 1) {
    throw new Response("Invalid page", { status: 400 });
  }

  return {
    page,
    products: await getProducts(page),
  };
}
```

Use search parameters for filters, pagination, and sorting that should persist in the URL.

## Use clientLoader for browser-only data

```tsx
import type { Route } from "./+types/profile";

export async function clientLoader({
  params,
}: Route.ClientLoaderArgs) {
  const response = await fetch(`/api/profile/${params.userId}`);

  if (!response.ok) {
    throw new Response("Profile request failed", {
      status: response.status,
    });
  }

  return response.json();
}

export default function Profile({ loaderData }: Route.ComponentProps) {
  return <h1>{loaderData.name}</h1>;
}
```

Use `clientLoader` only when the data genuinely requires browser-side behavior.

## Redirect from a loader

```tsx
import { redirect } from "react-router";
import type { Route } from "./+types/account";

export async function loader({ request }: Route.LoaderArgs) {
  const user = await getCurrentUser(request);

  if (!user) {
    throw redirect("/login");
  }

  return { user };
}
```

Use loader redirects for server-side access decisions.

## Protect server-only data

```tsx
export async function loader() {
  const record = await getPrivateRecord();

  return {
    id: record.id,
    name: record.name,
    status: record.status,
  };
}
```

Never return credentials, private API keys, session secrets, or other server-only values through loader data.

## Pending navigation

```tsx
import { useNavigation } from "react-router";

export function NavigationStatus() {
  const navigation = useNavigation();

  if (navigation.state === "idle") {
    return null;
  }

  return <p role="status">Loading...</p>;
}
```
Use `useNavigation` for navigation pending UI.

## Route-level errors

```tsx
import type { Route } from "./+types/product";

export function ErrorBoundary({
  error,
}: Route.ErrorBoundaryProps) {
  return (
    <main>
      <h1>Something went wrong</h1>
      <p>
        {error instanceof Error
          ? error.message
          : "Unable to load this page."}
      </p>
    </main>
  );
}
```tsx
import type { Route } from "./+types/products";

export function shouldRevalidate({
  defaultShouldRevalidate,
}: Route.ShouldRevalidateFunctionArgs) {
  return defaultShouldRevalidate;
}
```

Prefer the default revalidation behavior unless there is a specific reason to change it.