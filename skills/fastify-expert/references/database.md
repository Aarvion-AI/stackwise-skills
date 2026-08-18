# Database Integration: Prisma, Drizzle, pg (Fastify 5)

One pattern fits all three clients: an fp-wrapped plugin that creates the
client, decorates the instance, and tears down in `onClose`. Handlers reach the
db as `app.db` / `request.server.db` - never import a client singleton from a
module (it dodges lifecycle management and makes tests unable to swap it).

## The plugin shape (applies to every client)

```ts
import fp from 'fastify-plugin'

export default fp(async (app) => {
  const db = await makeClient(app.config.DATABASE_URL)
  app.decorate('db', db)
  app.addHook('onClose', async () => { await db.close() })  // runs on app.close()
}, { name: 'db', dependencies: ['config'] })
```

`onClose` hooks run LIFO when `app.close()` is called - Fastify stops accepting
connections, drains in-flight requests, then closes the db. That is your whole
graceful shutdown story; wire signals once:

```ts
// src/server.ts
const app = await buildApp()
const closeListeners = ['SIGINT', 'SIGTERM'].map((signal) =>
  process.on(signal, async () => {
    await app.close()
    process.exit(0)
  }))
await app.listen({ port: app.config.PORT, host: '0.0.0.0' })
```

(Or use the `close-with-grace` package, which also catches uncaught exceptions.)

## Prisma

```ts
// src/plugins/db.ts
import fp from 'fastify-plugin'
import { PrismaClient } from '@prisma/client'

declare module 'fastify' {
  interface FastifyInstance { db: PrismaClient }
}

export default fp(async (app) => {
  const db = new PrismaClient({
    log: [{ emit: 'event', level: 'query' }],
  })
  db.$on('query', (e) => app.log.debug({ query: e.query, ms: e.duration }, 'prisma'))
  await db.$connect()                       // fail fast at boot, not on first request
  app.decorate('db', db)
  app.addHook('onClose', async () => { await db.$disconnect() })
}, { name: 'db', dependencies: ['config'] })
```

Usage and the transaction pattern:

```ts
app.post('/orders', { schema }, async (request, reply) => {
  const order = await app.db.$transaction(async (tx) => {
    const order = await tx.order.create({ data: request.body })
    await tx.inventory.update({
      where: { sku: request.body.sku },
      data: { qty: { decrement: request.body.qty } },
    })
    return order
  })
  reply.code(201)
  return order
})
```

Map Prisma known errors in the error handler, not per-route:

```ts
import { Prisma } from '@prisma/client'

app.setErrorHandler((error, request, reply) => {
  if (error instanceof Prisma.PrismaClientKnownRequestError) {
    if (error.code === 'P2002') return reply.conflict('duplicate value')   // unique violation
    if (error.code === 'P2025') return reply.notFound()                    // record not found
  }
  /* ...fall through to generic handling... */
})
```

## Drizzle (node-postgres driver)

```ts
import fp from 'fastify-plugin'
import { drizzle, type NodePgDatabase } from 'drizzle-orm/node-postgres'
import { Pool } from 'pg'
import * as schema from '../db/schema.js'

declare module 'fastify' {
  interface FastifyInstance { db: NodePgDatabase<typeof schema> }
}

export default fp(async (app) => {
  const pool = new Pool({ connectionString: app.config.DATABASE_URL, max: 10 })
  await pool.query('select 1')              // fail fast
  const db = drizzle(pool, { schema })
  app.decorate('db', db)
  app.addHook('onClose', async () => { await pool.end() })
}, { name: 'db', dependencies: ['config'] })
```

```ts
import { eq } from 'drizzle-orm'
import { users } from '../db/schema.js'

app.get('/users/:id', { schema }, async (request, reply) => {
  const [user] = await app.db.select().from(users).where(eq(users.id, request.params.id))
  if (!user) return reply.notFound()
  return user
})

// transaction
await app.db.transaction(async (tx) => {
  await tx.insert(orders).values(order)
  await tx.update(inventory).set({ qty: sql`${inventory.qty} - ${qty}` }).where(...)
})
```

Keep TypeBox as the HTTP boundary even though Drizzle infers row types - derive
API schemas by hand or via `drizzle-typebox`; never expose table types directly
as response contracts.

## Plain pg (@fastify/postgres or raw Pool)

```ts
await app.register(import('@fastify/postgres'), {
  connectionString: app.config.DATABASE_URL,
})

app.get('/users/:id', { schema }, async (request, reply) => {
  const { rows } = await app.pg.query('select id, email from users where id = $1',
    [request.params.id])
  if (!rows[0]) return reply.notFound()
  return rows[0]
})

// transaction helper: acquires, BEGIN/COMMIT/ROLLBACK, releases
await app.pg.transact(async (client) => {
  await client.query('insert into orders ...')
  await client.query('update inventory ...')
})
```

If you use a raw `Pool` instead, the golden rule: `pool.query()` for one-shot
queries; for transactions `const client = await pool.connect()` and **always**
`client.release()` in `finally` - leaked clients exhaust the pool and hang the
app at exactly `max` concurrent transactions.

## Health checks

```ts
app.get('/healthz', { logLevel: 'silent' }, async (request, reply) => {
  try {
    await app.db.$queryRaw`select 1`        // prisma; pool.query('select 1') otherwise
    return { status: 'ok' }
  } catch {
    return reply.code(503).send({ status: 'db unavailable' })
  }
})
```

## Rules of thumb

- **Connect (or ping) at boot** so a bad `DATABASE_URL` fails deploy, not the
  first user request.
- **Pool sizing**: total connections = pool max × instance count; keep pool max
  modest (10-20) and let Postgres breathe. Serverless/edge needs a proxy
  (pgBouncer, Prisma Accelerate, Neon pooling) - not a bigger pool.
- **Migrations run in CI/CD** (`prisma migrate deploy`, `drizzle-kit migrate`),
  never inside the app process at startup in multi-instance deployments.
- **No per-request clients.** One pool per process, created in the plugin.
- **Repository/service layers** receive the client (or `app`) as an argument -
  keeps them testable and free of Fastify imports.
