# Schema-First Validation with TypeBox (Fastify 5)

Fastify validates with JSON Schema (Ajv 8) and serializes responses with
fast-json-stringify. TypeBox writes JSON Schema that doubles as the TypeScript
type - one source of truth, zero hand-written request types.

## Setup

```bash
npm i @sinclair/typebox @fastify/type-provider-typebox
```

```ts
// src/app.ts
import Fastify from 'fastify'
import { TypeBoxTypeProvider, TypeBoxValidatorCompiler } from '@fastify/type-provider-typebox'

export function buildApp() {
  const app = Fastify({ logger: true })
    .setValidatorCompiler(TypeBoxValidatorCompiler)   // optional: TypeBox's compiler, faster + format support
    .withTypeProvider<TypeBoxTypeProvider>()
  return app
}
```

`withTypeProvider` is a **type-level** cast on the returned instance - it does
nothing at runtime. Two consequences:

1. You must use the *returned* instance (chain it as above).
2. The provider does **not** flow into plugins typed as plain
   `FastifyPluginAsync`. Use the dedicated type:

```ts
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox'

const routes: FastifyPluginAsyncTypebox = async (app) => {
  // request.body / query / params are inferred from schemas here
}
```

## Route schemas: all four inputs plus response

```ts
import { Type } from '@sinclair/typebox'

const CreateUserBody = Type.Object({
  email: Type.String({ format: 'email' }),
  name: Type.String({ minLength: 1, maxLength: 100 }),
  role: Type.Union([Type.Literal('user'), Type.Literal('admin')], { default: 'user' }),
})

const UserReply = Type.Object({
  id: Type.String({ format: 'uuid' }),
  email: Type.String(),
  name: Type.String(),
  createdAt: Type.String({ format: 'date-time' }),
})

app.post('/users', {
  schema: {
    body: CreateUserBody,
    response: { 201: UserReply, 409: Type.Object({ message: Type.String() }) },
  },
}, async (request, reply) => {
  // request.body: { email: string; name: string; role: 'user' | 'admin' }
  const user = await app.db.user.create({ data: request.body })
  reply.code(201)
  return user
})

app.get('/users/:id', {
  schema: {
    params: Type.Object({ id: Type.String({ format: 'uuid' }) }),
    querystring: Type.Object({
      include: Type.Optional(Type.Array(Type.String())),
      page: Type.Number({ minimum: 1, default: 1 }),   // coerced from the string "2"
    }),
    headers: Type.Object({ 'x-tenant-id': Type.String() }),
    response: { 200: UserReply },
  },
}, async (request) => {
  request.params.id       // string (uuid-validated)
  request.query.page      // number - Ajv/TypeBox coerce querystring scalars
  return app.db.user.findUniqueOrThrow({ where: { id: request.params.id } })
})
```

Extract a standalone type when a service layer needs it:

```ts
import type { Static } from '@sinclair/typebox'
type CreateUser = Static<typeof CreateUserBody>
```

## Response schemas are serializers, not docs

`response: { 200: ... }` compiles a fast-json-stringify serializer - typically
2-5x faster than `JSON.stringify` on hot paths. The critical behavior:

- **Properties not in the schema are silently stripped.** This is the built-in
  defense against leaking `passwordHash`, and the cause of "my field vanished".
  When a response field is missing, fix the response schema.
- A value that cannot satisfy the schema (e.g. `Date` where `Type.String()` is
  declared without a format) throws at serialization time, producing a 500.
  `format: 'date-time'` serializes `Date` instances correctly.
- Status keys can be exact (`200`), ranges (`'2xx'`), or `default`. An
  unlisted status code skips schema serialization entirely.

Return the raw entity and let the schema shape it - do not hand-pick fields in
the handler *and* maintain a schema.

## Shared schemas and $ref

Register once, reference everywhere (also feeds `@fastify/swagger`):

```ts
app.addSchema({ $id: 'User', ...UserReply })   // spread keeps TypeBox metadata

app.get('/users', {
  schema: { response: { 200: Type.Array(Type.Ref('User')) } },
}, listUsers)
```

`addSchema` is encapsulated like everything else - add shared schemas in an
fp-wrapped plugin (or the root) so all route plugins can `Type.Ref` them.
`FST_ERR_SCH_ALREADY_PRESENT` means the same `$id` was added twice.

## Validation errors: shape and customization

A failed validation short-circuits to a 400 before your handler runs:

```json
{
  "statusCode": 400,
  "code": "FST_ERR_VALIDATION",
  "error": "Bad Request",
  "message": "body/email must match format \"email\""
}
```

- Per-property messages: `Type.String({ format: 'email', errorMessage: 'must be a valid email' })`
  requires `ajv-errors` when using the Ajv compiler; the TypeBox compiler reads
  TypeBox's own error messages.
- To reshape all validation errors, handle `error.validation` in
  `setErrorHandler` (see `hooks-auth.md`) or set `schemaErrorFormatter`.
- `attachValidation: true` on a route puts the error on `request.validationError`
  instead of auto-replying - rarely what you want; prefer the error handler.

## Ajv configuration (only when using the default Ajv compiler)

```ts
const app = Fastify({
  ajv: {
    customOptions: { removeAdditional: 'all', coerceTypes: 'array', useDefaults: true },
    plugins: [import('ajv-formats')],   // 'email', 'uuid', 'date-time' formats
  },
})
```

Defaults in Fastify 5: `coerceTypes: 'array'`, `useDefaults: true`,
`removeAdditional: true` on body schemas. `ajv-formats` is required for string
formats with Ajv; the `TypeBoxValidatorCompiler` supports TypeBox formats
without it. Pick one compiler per app and stay consistent.

## Common failure modes

- **`request.body` is `unknown`/`any`** - the plugin is typed `FastifyPluginAsync`
  instead of `FastifyPluginAsyncTypebox`, or the route is registered on an
  instance captured *before* `withTypeProvider`.
- **Schema compiles but every request 400s with "must be object"** - sending
  form data or missing `content-type: application/json`; Fastify only parses
  JSON by default. Register `@fastify/formbody` or `@fastify/multipart` if needed.
- **Optional vs nullable** - `Type.Optional(Type.String())` means the key may be
  absent; `Type.Union([Type.String(), Type.Null()])` means explicit `null`.
  Prisma nullable columns need the union on responses or serialization throws.
- **Reusing one mega-schema for create and update** - build a base object and
  derive: `Type.Partial(CreateUserBody)` for PATCH, `Type.Omit`/`Type.Pick` for
  variants. Do not hand-copy schemas.
- **Validating in the handler with another library** - duplicated work, wrong
  error shape, and no serialization speedup. If a project standardizes on Zod,
  use `fastify-type-provider-zod` app-wide instead of mixing per-route.
