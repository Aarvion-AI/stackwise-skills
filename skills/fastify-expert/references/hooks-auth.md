# Hooks Lifecycle, JWT Auth, Errors, and Logging (Fastify 5)

## Request lifecycle: the exact hook order

```
incoming request
  → onRequest        (no body yet; auth, rate limiting, request-id)
  → preParsing       (raw stream transforms: decompression, size caps)
  → [body parsing]
  → preValidation    (mutate request.body BEFORE schema validation)
  → [schema validation → 400 on failure]
  → preHandler       (body is parsed AND validated; authorization using body)
  → [handler]
  → preSerialization (mutate payload before fast-json-stringify)
  → onSend           (payload is a serialized string/buffer; headers still mutable)
  → onResponse       (response gone; metrics/logging only - cannot change reply)

anywhere on throw → onError → error handler
client abort      → onRequestAbort
timeout           → onTimeout
```

Choosing the hook - the decisions LLMs get wrong:

- **Auth (token verification) → `onRequest`.** The body is not parsed yet, so
  invalid tokens are rejected before any parsing/validation cost. Putting auth
  in `preHandler` wastes work and lets unauthenticated requests hit validation.
- **Authorization that needs the payload → `preHandler`.** Only there is
  `request.body` both parsed and validated.
- **Normalizing input (trim, legacy field renames) → `preValidation`.** After
  parsing, before validation - mutations here are what the schema sees.
- **Metrics/audit → `onResponse`** (has `reply.elapsedTime`); it cannot send
  anything.

Async hooks must **not** take or call `done`. To short-circuit from a hook,
`return reply.code(401).send(...)` - the `return` matters; without it Fastify
continues the chain and you get "Reply was already sent".

Hooks are encapsulated: `addHook` inside a plain route plugin applies only to
that plugin's routes. Route-level hooks accept arrays and run after
instance-level ones: `{ onRequest: [app.authenticate, app.requireAdmin] }`.

## JWT auth with @fastify/jwt

```bash
npm i @fastify/jwt @fastify/sensible
```

```ts
// src/plugins/auth.ts
import fp from 'fastify-plugin'
import fjwt from '@fastify/jwt'
import type { FastifyReply, FastifyRequest } from 'fastify'

export interface TokenPayload { sub: string; role: 'user' | 'admin' }

// @fastify/jwt's own declaration merge: payload = what you sign,
// user = the type of request.user after jwtVerify()
declare module '@fastify/jwt' {
  interface FastifyJWT {
    payload: TokenPayload
    user: TokenPayload
  }
}

declare module 'fastify' {
  interface FastifyInstance {
    authenticate: (request: FastifyRequest, reply: FastifyReply) => Promise<void>
    requireRole: (role: TokenPayload['role']) =>
      (request: FastifyRequest, reply: FastifyReply) => Promise<void>
  }
}

export default fp(async (app) => {
  await app.register(fjwt, {
    secret: app.config.JWT_SECRET,
    sign: { expiresIn: '15m' },
  })

  app.decorate('authenticate', async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      await request.jwtVerify()   // reads Authorization: Bearer, sets request.user
    } catch {
      return reply.unauthorized('invalid or missing token')
    }
  })

  app.decorate('requireRole', (role: TokenPayload['role']) =>
    async (request: FastifyRequest, reply: FastifyReply) => {
      if (request.user.role !== role) return reply.forbidden()
    })
}, { name: 'auth', dependencies: ['config'] })
```

```ts
// login + protected routes (route plugin, NOT fp-wrapped)
app.post('/login', { schema: { body: LoginBody } }, async (request, reply) => {
  const user = await verifyCredentials(app, request.body)      // argon2/bcrypt compare
  if (!user) return reply.unauthorized('bad credentials')
  return { token: app.jwt.sign({ sub: user.id, role: user.role }) }
})

app.get('/me', { onRequest: [app.authenticate] }, async (request) => request.user)

app.delete('/users/:id', {
  onRequest: [app.authenticate, app.requireRole('admin')],
  schema: { params: Type.Object({ id: Type.String() }) },
}, deleteUser)
```

Scoped alternative - protect a whole plugin without listing hooks per route:

```ts
const adminRoutes: FastifyPluginAsyncTypebox = async (app) => {
  app.addHook('onRequest', app.authenticate)
  app.addHook('onRequest', app.requireRole('admin'))
  app.get('/stats', getStats)          // both hooks apply to every route here
}
```

Notes:
- `request.jwtVerify()` / `reply.jwtSign()` are request/reply methods;
  `app.jwt.sign/verify` are the instance versions.
- Refresh tokens: sign with a separate key/namespace
  (`app.register(fjwt, { secret, namespace: 'refresh' })` gives
  `request.refreshJwtVerify()`), store server-side (db/redis) for revocation,
  deliver via `@fastify/cookie` with `httpOnly` + `sameSite`.
- Composing multiple strategies (API key OR JWT): `@fastify/auth` provides
  `app.auth([verifyJwt, verifyApiKey], { relation: 'or' })` as a hook.

## Error handling

### setErrorHandler - one place, per encapsulation context

```ts
app.setErrorHandler((error, request, reply) => {
  // 1. Schema validation failures
  if (error.validation) {
    return reply.code(400).send({
      message: 'validation failed',
      errors: error.validation.map((v) => ({
        path: v.instancePath, message: v.message,
      })),
    })
  }

  // 2. Known application errors carry statusCode
  if (error.statusCode && error.statusCode < 500) {
    return reply.code(error.statusCode).send({ message: error.message })
  }

  // 3. Unknown → log with request context, hide details
  request.log.error({ err: error }, 'unhandled error')
  return reply.internalServerError()
})

app.setNotFoundHandler((request, reply) =>
  reply.code(404).send({ message: `route ${request.method} ${request.url} not found` }))
```

Error handlers are encapsulated too: a `setErrorHandler` inside a route plugin
overrides the root one for that subtree - useful for a legacy-API error shape.
Errors thrown *inside* an error handler fall back to the parent handler.

### @fastify/sensible

Register once (it is fp-wrapped, so it is global):

```ts
await app.register(import('@fastify/sensible'))

reply.notFound('user not found')       // 404 with proper shape
reply.badRequest(); reply.conflict(); reply.unauthorized(); reply.forbidden()
throw app.httpErrors.notFound('user not found')   // throwable from services
app.assert(user, 404, 'user not found')           // assert-style guard
```

Thrown `httpErrors` carry `statusCode`, so the default (or your custom) error
handler maps them correctly. This kills the `reply.code(404).send({...})`
boilerplate and keeps services reply-free.

### Custom domain errors with @fastify/error

```ts
import createError from '@fastify/error'

export const OutOfStock = createError('APP_OUT_OF_STOCK', 'item %s is out of stock', 409)
throw new OutOfStock(itemId)   // .code, .statusCode, printf-formatted message
```

### Rules

- Throw from async handlers/services; never `reply.send(error)` manually.
- Do not throw strings or bare objects - always `Error` subclasses.
- 5xx details never reach the client; log `{ err: error }` (pino serializes
  stack + cause) and return a generic message.
- `onError` hooks observe errors (metrics) but must not send a reply - only the
  error handler replies.

## Pino logging and request correlation

Fastify's logger *is* pino - never bolt on winston/console.log:

```ts
const app = Fastify({
  logger: {
    level: process.env.LOG_LEVEL ?? 'info',
    redact: ['req.headers.authorization', 'req.headers.cookie', '*.password'],
    transport: process.env.NODE_ENV === 'development'
      ? { target: 'pino-pretty' }        // dev only: pretty-printing is slow
      : undefined,                        // prod: raw JSON to stdout
  },
  genReqId: (req) =>                      // honor upstream correlation ids
    (req.headers['x-request-id'] as string) ?? crypto.randomUUID(),
  requestIdHeader: false,                 // we handle the header in genReqId
  requestIdLogLabel: 'reqId',
})
// echo the id back so clients/load balancers can correlate
app.addHook('onSend', async (request, reply) => {
  reply.header('x-request-id', request.id)
})
```

Fastify 5 gotcha: a **custom pino instance** goes in `loggerInstance`, not
`logger` (`logger` accepts only options/boolean in v5).

Always log through `request.log`, never `app.log`, inside request handling -
it is a child logger already carrying `reqId`, so every line from one request
correlates automatically:

```ts
app.post('/orders', { schema }, async (request, reply) => {
  request.log.info({ sku: request.body.sku }, 'creating order')   // includes reqId
  ...
})
```

Services that need logging should accept `request.log` (a `FastifyBaseLogger`)
as a parameter rather than importing a global logger - correlation survives the
call chain. For per-route noise control: `app.get('/healthz', { logLevel: 'silent' }, ...)`.
