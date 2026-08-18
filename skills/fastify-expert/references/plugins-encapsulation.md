# Plugins, Encapsulation Contexts, and Decorators (Fastify 5)

Everything in Fastify is a plugin. Getting encapsulation wrong is the #1 source of
"my decorator/hook is undefined" bugs. Read the mental model first.

## The encapsulation model

`app.register(plugin)` does **not** run the plugin against `app`. It creates a
**child context** - a prototype-linked copy of the instance. Inside the child:

- The child **sees** everything the parent already has (decorators, hooks, plugins).
- Anything the child adds (decorators, hooks, `setErrorHandler`, content type
  parsers) is visible **only to the child and its descendants** - never to the
  parent or to sibling plugins.

```
root
├── register(dbPlugin)        ← without fp(): app.db only exists inside dbPlugin
├── register(usersRoutes)     ← cannot see app.db (sibling)
└── register(adminRoutes)
      └── addHook('onRequest', requireAdmin)  ← applies ONLY to admin routes: good
```

This is a feature: scoped auth hooks, scoped error handlers, and route prefixes
all rely on it. Break it only deliberately.

## fastify-plugin: breaking encapsulation on purpose

`fp()` marks a plugin so `register()` runs it in the **caller's** context instead
of creating a child. Use it for infrastructure that the whole app must see:
database clients, config, auth utilities, shared hooks.

```ts
// src/plugins/config.ts
import fp from 'fastify-plugin'
import { Type, type Static } from '@sinclair/typebox'
import { Value } from '@sinclair/typebox/value'

const EnvSchema = Type.Object({
  DATABASE_URL: Type.String(),
  JWT_SECRET: Type.String({ minLength: 32 }),
  PORT: Type.Number({ default: 3000 }),
})

declare module 'fastify' {
  interface FastifyInstance { config: Static<typeof EnvSchema> }
}

export default fp(async (app) => {
  const config = Value.Parse(EnvSchema, { ...process.env, PORT: Number(process.env.PORT ?? 3000) })
  app.decorate('config', config)
}, { name: 'config', fastifyVersion: '5.x' })
```

`fp()` options that matter:

- `name` - required in practice; enables `dependencies` checks and better errors.
- `fastifyVersion: '5.x'` - fails fast on a mismatched Fastify major.
- `dependencies: ['config']` - throws at boot if a required plugin was not
  registered first. Use it: it turns silent `undefined` into a clear startup error.

```ts
export default fp(async (app) => {
  app.decorate('db', makeDb(app.config.DATABASE_URL))
}, { name: 'db', dependencies: ['config'] })
```

## When NOT to use fp()

Route plugins. They should stay encapsulated so prefixes, scoped hooks, and
scoped error handlers work:

```ts
// src/app.ts
await app.register(import('./plugins/config.js'))   // fp: global
await app.register(import('./plugins/db.js'))       // fp: global
await app.register(import('./plugins/auth.js'))     // fp: global
await app.register(import('./routes/users.js'), { prefix: '/api/users' })   // plain
await app.register(import('./routes/admin.js'), { prefix: '/api/admin' })   // plain
```

Inside `routes/admin.js` you can `app.addHook('onRequest', app.requireAdmin)`
and it applies to every admin route and nothing else. If you had wrapped the
route plugin in `fp()`, that hook would leak to the entire application.

## Registration order and await

Fastify 5 delays plugin execution until `.ready()` / `.listen()` / `.inject()`,
but **order still matters** for `dependencies` and for reading decorators at
plugin-definition time. Top-level `await app.register(...)` (ESM) keeps ordering
obvious. Never call `app.listen()` before all `register()` calls.

## Decorators and TypeScript declaration merging

Decorators are how you attach anything to Fastify. TypeScript learns about them
via declaration merging - put the `declare module` next to the plugin that
creates the decorator, never in a global `.d.ts` dumping ground:

```ts
declare module 'fastify' {
  interface FastifyInstance {
    db: PrismaClient
    authenticate: (request: FastifyRequest, reply: FastifyReply) => Promise<void>
  }
  interface FastifyRequest {
    user: { sub: string; role: 'user' | 'admin' } | null
  }
}
```

Merges are global to the compilation, so `request.user` typechecks everywhere -
including in encapsulated contexts where the decorator does not exist at
runtime. `dependencies` in `fp()` is your runtime guard for that gap.

### decorateRequest: reference types are shared

The decorator value is set on the request **prototype**. A mutable object is
therefore shared by every request - a data-leak bug, and Fastify 5 warns on it:

```ts
// WRONG: one array shared across all requests
app.decorateRequest('permissions', [])

// RIGHT: decorate with null, assign per-request in a hook
app.decorateRequest('user', null)
app.addHook('onRequest', async (request) => {
  request.user = await resolveUser(request)
})

// Also fine for derived values: a getter (evaluated per access)
app.decorateRequest('ip2', { getter() { return (this as FastifyRequest).headers['x-real-ip'] } })
```

## Plugin function forms

```ts
// async form - do NOT accept or call `done`
const plugin: FastifyPluginAsync<MyOpts> = async (app, opts) => { /* ... */ }

// callback form - MUST call done() exactly once
const plugin: FastifyPluginCallback = (app, opts, done) => { done() }
```

Mixing them (an `async` function that also takes `done`) throws
`FST_ERR_PLUGIN_TIMEOUT` or a promise/callback conflict at boot. Prefer async.
For route plugins with TypeBox, use `FastifyPluginAsyncTypebox` (see
`validation-typebox.md`) so the type provider carries into the plugin.

## Passing and typing plugin options

```ts
interface RateLimitOpts { max: number }

const rateLimit: FastifyPluginAsync<RateLimitOpts> = async (app, opts) => {
  app.addHook('onRequest', makeLimiter(opts.max))
}
await app.register(rateLimit, { max: 100 })
```

`prefix` is handled by Fastify itself and composes: registering a plugin with
`{ prefix: '/v1' }` that itself registers routes under `/users` yields
`/v1/users`. Inside a plugin, `app.prefix` reads the accumulated prefix.

## Autoload (optional but common)

`@fastify/autoload` registers directories of plugins/routes by convention:

```ts
import autoload from '@fastify/autoload'

await app.register(autoload, { dir: join(__dirname, 'plugins') })  // fp-wrapped infra
await app.register(autoload, { dir: join(__dirname, 'routes'), options: { prefix: '/api' } })
```

Autoload respects `fp()` markers: fp-wrapped files load into the parent context,
plain files stay encapsulated. Keep the two directories separate.

## Debugging encapsulation

- `app.hasDecorator('db')` / `app.hasRequestDecorator('user')` - check at runtime.
- `app.printPlugins()` - prints the plugin tree; a decorator lives in the node
  where it was added and everything below it.
- `FST_ERR_DEC_ALREADY_PRESENT` - you registered an fp-wrapped plugin twice, or
  two plugins decorate the same name; guard with `if (!app.hasDecorator('db'))`
  only as a last resort - usually the double registration is the real bug.
- Decorator exists in the type system but is `undefined` at runtime - the plugin
  that creates it is not an ancestor of the code using it. Move the consumer, or
  fp-wrap the provider.
