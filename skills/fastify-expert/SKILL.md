---
name: fastify-expert
description: Use when building or debugging Fastify services - files importing fastify, fastify-plugin, @fastify/* packages, or @sinclair/typebox; projects with a Fastify app factory, route plugins, or app.inject() tests; mentions of Fastify 5, encapsulation, decorators, hooks, TypeBox type provider, @fastify/jwt, or pino logging. Builds typed REST APIs, wires plugins and encapsulation correctly, adds JSON Schema validation and JWT auth, integrates Prisma/Drizzle/pg, writes inject-based tests. Invoke for new routes/plugins, schema-first request typing, auth flows, error handling, database wiring, and test suites.
license: MIT
metadata:
  version: "0.1.0"
  category: backend
  frameworks: "Fastify 5.x, Node.js 22 (LTS), TypeScript 5.x, TypeBox 0.34+, Pino 9"
  triggers: fastify, fastify-plugin, fastify.register, encapsulation, decorateRequest, TypeBox, type provider, preHandler, onRequest hook, @fastify/jwt, setErrorHandler, @fastify/sensible, app.inject, pino, fast-json-stringify
  related: react-expert, vue-expert, nestjs-expert, terraform-expert, playwright-expert
---

# Fastify Expert

Turns Claude into a senior Node.js backend engineer who ships Fastify 5 services on Node 22 with schema-first TypeScript, correct plugin encapsulation, and inject-based tests - and who never smuggles Express idioms into a Fastify codebase.

## When to Use This Skill

- Scaffold a Fastify 5 service or add route plugins to an existing one
- Structure plugins and decide where `fastify-plugin` is (and is not) needed
- Define request/response schemas with the TypeBox type provider so handler types are inferred, not hand-written
- Add JWT authentication (`@fastify/jwt`) and per-route authorization via hooks
- Wire Prisma, Drizzle, or `pg` behind a decorated, lifecycle-managed plugin
- Centralize error handling with `setErrorHandler` and `@fastify/sensible`
- Write tests with `app.inject()` (no port binding) and fix failing ones
- Fix Express-isms: `app.use` middleware, `res.send`, monkey-patched request objects

## Core Workflow

1. **Analyze** - read `package.json` (confirm `fastify` is 5.x and which `@fastify/*` plugins exist), the app factory (`buildApp`/`app.ts`), how plugins are registered (manual vs `@fastify/autoload`), the type provider in use, and `tsconfig.json`. Match the existing plugin layout and naming before writing anything. Note which decorators already exist and where their `declare module 'fastify'` merges live.
2. **Implement** - write features as plugins: `FastifyPluginAsyncTypebox` for encapsulated route plugins, `fastify-plugin` only for cross-cutting infrastructure (db, auth, config). Define every route's `schema` (body, querystring, params, response) with TypeBox and let the type provider infer handler types. Async handlers return the payload; never mix `reply.send()` with a returned value.
3. **Verify types/lint** - run `npx tsc --noEmit`, then the project's linter (`npx eslint .` or `npm run lint`); fix all reported issues and re-run until clean before proceeding. Do not paper over type errors with `as any` on request/reply - fix the schema or the declaration merge instead.
4. **Test** - write or update tests using the app factory + `app.inject()` (see `references/testing.md`); run the project's test command (`npx vitest run` or `node --test`); fix every failure and re-run until all tests pass.
5. **Prove it works** - start the app (`npm run dev` or `node --run dev`), hit the changed routes with `curl`, including one invalid payload to confirm the 400 validation shape and one unauthorized request to confirm the 401. Check the response actually contains the fields you expect - the response schema silently drops unlisted fields. Fix and re-verify until live behavior matches the spec.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Plugin system, encapsulation contexts, fastify-plugin, decorators + declaration merging | `references/plugins-encapsulation.md` | Creating/registering any plugin; a decorator or hook is "undefined" in another file; deciding whether to use `fp()`; typing `fastify.x` or `request.x` |
| TypeBox type provider, schema-first validation, response serialization | `references/validation-typebox.md` | Writing any route schema; typing handlers from schemas; shared schemas/$ref; fields missing from responses; validation error shapes |
| Hooks lifecycle, @fastify/jwt auth, error handling, pino + request correlation | `references/hooks-auth.md` | Choosing onRequest vs preValidation vs preHandler; adding login/protected routes; role checks; centralizing errors; configuring logging or request ids |
| Prisma / Drizzle / pg integration and lifecycle | `references/database.md` | Wiring any database client; connection pooling; graceful shutdown; transactions per request; health checks |
| Testing with app.inject(), test app factories, auth/db in tests | `references/testing.md` | Writing or fixing any test; testing protected routes; overriding db/config for tests; testing plugins in isolation |

## Key Patterns

**Route plugin with TypeBox - types are inferred from the schema, never hand-annotated:**

```ts
import { Type } from '@sinclair/typebox'
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox'

const usersRoutes: FastifyPluginAsyncTypebox = async (app) => {
  app.post('/users', {
    schema: {
      body: Type.Object({ email: Type.String({ format: 'email' }), name: Type.String() }),
      response: { 201: Type.Object({ id: Type.String(), email: Type.String() }) },
    },
  }, async (request, reply) => {
    const { email, name } = request.body   // typed from the schema
    const user = await app.db.user.create({ data: { email, name } })
    reply.code(201)
    return user                            // serialized by the 201 schema
  })
}
export default usersRoutes
```

**Infrastructure plugin - `fp()` breaks encapsulation on purpose, with declaration merging:**

```ts
import fp from 'fastify-plugin'
import { PrismaClient } from '@prisma/client'

declare module 'fastify' {
  interface FastifyInstance { db: PrismaClient }
}

export default fp(async (app) => {
  const db = new PrismaClient()
  await db.$connect()
  app.decorate('db', db)
  app.addHook('onClose', async () => { await db.$disconnect() })
}, { name: 'db', fastifyVersion: '5.x' })
```

**Auth as a decorated onRequest hook, applied per route - not global middleware:**

```ts
app.decorate('authenticate', async (request: FastifyRequest, reply: FastifyReply) => {
  try { await request.jwtVerify() }
  catch { return reply.unauthorized('invalid or missing token') }
})

app.get('/me', { onRequest: [app.authenticate] }, async (request) => request.user)
```

## Common Mistakes

- **Registering a decorator in a plain plugin and using it elsewhere.** `register()` creates a child encapsulation context; decorators and hooks added there are invisible to siblings and the parent. Wrap infrastructure plugins in `fp()` - but do *not* reflexively wrap route plugins, which should stay encapsulated (that is how per-prefix hooks and scoped auth work).
- **Express idioms.** There is no `app.use(middleware)` in Fastify 5 without `@fastify/middie` (avoid it); use hooks and plugins. `res.send`/`res.json`/`res.status` do not exist - return the payload from an async handler or use `reply.code().send()`, never both (returning a value *and* calling `reply.send` causes "Reply was already sent" / hung requests).
- **Hand-writing handler types or validating in the handler.** Declare `schema` and let the TypeBox type provider infer `request.body`/`query`/`params`. Manual `zod.parse` inside handlers duplicates work and skips fast-json-stringify serialization.
- **Response schema surprises.** `response: { 200: ... }` is a serializer, not documentation - any property not in the schema is silently stripped from the response. If a field "disappears", the response schema is missing it.
- **Wrong hook for auth.** JWT verification belongs in `onRequest` (body not yet parsed - cheap rejects); use `preHandler` only when authorization needs the parsed body. `preValidation` is for mutating the raw request before schema validation, not for auth.
- **Decorating requests with mutable objects.** `app.decorateRequest('user', { ... })` shares one object across all requests. Decorate with `null` and assign per-request in a hook.
- **v4 idioms in a v5 codebase.** Node 20+ is required (target 22); `request.routerPath` is gone (use `request.routeOptions.url`); custom logger instances go in `loggerInstance`, not `logger`; `reply.redirect(url, code)` takes the URL first.
- **Testing over HTTP.** Do not `listen()` and fetch `localhost` in tests - `app.inject()` dispatches requests in-process with no port binding, and it awaits `ready()` for you.
