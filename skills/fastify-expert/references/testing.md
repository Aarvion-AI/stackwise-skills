# Testing Fastify 5 with app.inject()

`app.inject()` (light-my-request) dispatches a fake HTTP request through the
full pipeline - routing, hooks, validation, handler, serialization - entirely
in-process. No `listen()`, no port, no `fetch('http://localhost:...')`, no port
collisions in parallel test runs. It also awaits `app.ready()` for you.

## Prerequisite: an app factory

Tests need to build the app with overrides, so `buildApp` must take options and
`server.ts` must be the only file that calls `listen()`:

```ts
// src/app.ts
export interface BuildAppOpts {
  config?: Partial<AppConfig>
  logger?: FastifyServerOptions['logger']
}

export async function buildApp(opts: BuildAppOpts = {}) {
  const app = Fastify({ logger: opts.logger ?? false })
    .setValidatorCompiler(TypeBoxValidatorCompiler)
    .withTypeProvider<TypeBoxTypeProvider>()
  await app.register(configPlugin, { overrides: opts.config })
  await app.register(dbPlugin)
  await app.register(authPlugin)
  await app.register(routes, { prefix: '/api' })
  return app
}
```

If a project calls `listen()` in the same file that builds the app, split it
first - that refactor pays for every test after it.

## Vitest

```ts
// test/users.test.ts
import { describe, it, beforeAll, afterAll, expect } from 'vitest'
import { buildApp } from '../src/app.js'

describe('users', () => {
  let app: Awaited<ReturnType<typeof buildApp>>

  beforeAll(async () => { app = await buildApp({ config: { DATABASE_URL: TEST_DB_URL } }) })
  afterAll(async () => { await app.close() })   // always close: releases db pools

  it('creates a user', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/users',
      payload: { email: 'a@b.co', name: 'Ada' },   // objects auto-JSON + content-type
    })
    expect(res.statusCode).toBe(201)
    expect(res.json()).toMatchObject({ email: 'a@b.co' })
    expect(res.json()).not.toHaveProperty('passwordHash')  // response schema strips it
  })

  it('rejects an invalid payload with the validation shape', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/users', payload: { email: 'nope' } })
    expect(res.statusCode).toBe(400)
    expect(res.json().message).toMatch(/email/)
  })
})
```

Run with `npx vitest run`. Node's built-in runner works identically
(`node --test` on Node 22 with `tsx` or type-stripping):

```ts
import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'

test('GET /healthz', async () => {
  const app = await buildApp()
  after(() => app.close())
  const res = await app.inject({ method: 'GET', url: '/healthz' })
  assert.equal(res.statusCode, 200)
})
```

## inject() surface you actually use

```ts
const res = await app.inject({
  method: 'GET',
  url: '/api/items',
  query: { page: '2', tag: ['a', 'b'] },       // or inline in url
  headers: { 'x-tenant-id': 't1' },
  cookies: { session: 'abc' },
  payload: { any: 'object' },                   // string/Buffer/stream also fine
})

res.statusCode      // number
res.json<T>()       // parsed body (throws on non-JSON)
res.body            // raw string
res.headers         // response headers
res.cookies         // parsed set-cookie array
```

Chained form for readability: `await app.inject().post('/api/users').payload({...}).end()`.

## Testing protected routes

Sign a real token with the app's own jwt - do not mock the auth plugin:

```ts
function authHeader(app: FastifyInstance, payload: TokenPayload) {
  return { authorization: `Bearer ${app.jwt.sign(payload)}` }
}

it('403s a non-admin', async () => {
  const res = await app.inject({
    method: 'DELETE',
    url: '/api/users/123',
    headers: authHeader(app, { sub: 'u1', role: 'user' }),
  })
  expect(res.statusCode).toBe(403)
})
```

The test config just needs the same `JWT_SECRET` the app booted with.

## Database strategy in tests

In order of preference:

1. **Real Postgres via Testcontainers** - `@testcontainers/postgresql` starts a
   throwaway db per suite; run migrations in `beforeAll`, truncate between
   tests. Highest fidelity; the default for anything with nontrivial queries.
2. **A dedicated test database** (`DATABASE_URL` override) with per-test
   truncation - fine on CI runners with a Postgres service.
3. **Swap the db plugin** - because handlers use `app.db`, tests can register a
   fake before routes:

```ts
export async function buildTestApp(db: Partial<FastifyInstance['db']>) {
  const app = Fastify({ logger: false }).withTypeProvider<TypeBoxTypeProvider>()
  await app.register(fp(async (a) => { a.decorate('db', db as FastifyInstance['db']) },
    { name: 'db' }))
  await app.register(authPlugin)
  await app.register(routes, { prefix: '/api' })
  return app
}
```

Avoid `vi.mock('@prisma/client')`-style module mocking - the plugin seam is
cleaner and does not fight ESM.

## Testing a plugin in isolation

```ts
it('db plugin decorates and pings', async () => {
  const app = Fastify({ logger: false })
  await app.register(configPlugin, { overrides: testConfig })
  await app.register(dbPlugin)
  await app.ready()                 // plugins execute here
  expect(app.hasDecorator('db')).toBe(true)
  await app.close()
})
```

`await app.ready()` is required when asserting on the instance without
injecting - plugins have not executed before it.

## Pitfalls

- **Forgetting `app.close()`** - open pg pools keep the event loop alive; the
  runner hangs "after" tests pass. Close in `afterAll`/`after` always.
- **One shared app across test *files* with parallel runners** - each file gets
  its own process in vitest; build one app per file (fast: no port binding),
  not one per test unless tests mutate app state.
- **Asserting on `res.body` for JSON** - use `res.json()`; body is a string.
- **Testing validation by unit-testing schemas** - inject an invalid request
  instead; that also covers the error handler's 400 shape.
- **Spinning up `listen()` to test** - only do this for true e2e (e.g. under
  Playwright); everything else is inject territory.
