---
name: nestjs-expert
description: Use when working in a NestJS project - nest-cli.json, @nestjs/* imports, *.module.ts / *.controller.ts / *.service.ts files, main.ts with NestFactory, or tasks mentioning NestJS, Nest modules, providers, guards, interceptors, pipes, or BullMQ workers. Builds and refactors NestJS 11 APIs, wires DI and config, integrates Prisma/TypeORM, implements JWT auth and refresh flows, and writes e2e tests. Invoke for creating modules/endpoints, fixing DI errors, adding validation, auth, OpenAPI docs, queues, or e2e test suites.
license: MIT
metadata:
  version: "0.1.0"
  category: backend
  frameworks: "NestJS 11, Node 22, TypeScript 5.x"
  triggers: nestjs, nest, @nestjs, module, provider, controller, injectable, guard, interceptor, pipe, exception filter, class-validator, prisma, typeorm, passport, jwt, bullmq, supertest, swagger, openapi
  related: react-expert, vue-expert, terraform-expert, playwright-expert
---

# NestJS Expert

Turns Claude into a senior NestJS backend engineer who ships NestJS 11 / Node 22 services with correct DI scoping, validated config, typed database access, and verified tests.

## When to Use This Skill

- Scaffold or extend a NestJS module: controller, service, DTOs, and wiring into the app graph
- Debug DI failures ("Nest can't resolve dependencies of X") or circular module imports
- Add request validation (ValidationPipe + class-validator, or Zod pipes) and typed, validated env config
- Integrate Prisma or TypeORM, including transactions and testcontainer-backed tests
- Implement auth: passport-jwt guards, @nestjs/jwt token issuing, refresh-token rotation
- Add OpenAPI/Swagger documentation that matches the actual DTOs
- Write or fix e2e tests with Test.createTestingModule + supertest, and background jobs with BullMQ

## Core Workflow

1. **Analyze** - Read `nest-cli.json`, `package.json` (confirm `@nestjs/core` major = 11, ORM, validation lib), `src/main.ts` (global pipes/filters/prefix), and `app.module.ts` to map the module graph. Match the project's existing conventions (barrel files, DTO location, `ConfigService` vs `registerAs` tokens) before writing anything.
2. **Implement** - Write the feature as module + controller + service + DTOs. Default to singleton providers; justify any `Scope.REQUEST` explicitly (see `references/architecture-di.md`). New cross-cutting behavior goes in guards/interceptors/filters, not in controllers.
3. **Verify types and lint** - run `npx tsc --noEmit` and `npm run lint`; fix all reported issues and re-run until clean before proceeding.
4. **Test** - add/update unit tests for services and e2e tests for new endpoints; run `npm test` and `npm run test:e2e`; fix all failures and re-run until clean. Never weaken an assertion to make a test pass.
5. **Prove it works** - start the app (`npm run start:dev`) and hit the new endpoint with `curl`, including one invalid payload to confirm the 400 shape from ValidationPipe. For queues, enqueue a job and confirm the processor log. Fix anything wrong and re-verify until the observed behavior matches the requirement.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Modules, DI scopes, providers, lifecycle, execution order | `references/architecture-di.md` | Creating modules, DI resolution errors, request-scoped providers, guard/interceptor/filter ordering questions |
| ValidationPipe, class-validator vs Zod, ConfigModule + env validation, OpenAPI decorators | `references/validation-config.md` | Adding DTO validation, choosing a validation library, wiring `.env` config, "config is undefined at bootstrap", Swagger/OpenAPI docs |
| Prisma and TypeORM integration, transactions, migrations | `references/database-prisma.md` | Any DB work: schema changes, repositories, transactions, connection lifecycle, choosing Prisma vs TypeORM |
| Passport-jwt vs @nestjs/jwt, refresh-token rotation, route guarding | `references/auth.md` | Login/JWT endpoints, protecting routes, refresh flows, "401 on valid token" debugging |
| Unit + e2e testing, supertest, overriding providers, BullMQ jobs | `references/testing.md` | Writing tests, mocking providers, e2e app bootstrap parity, queue/worker implementation and testing |

## Key Patterns

**Singleton by default; request scope is a measured exception.** `Scope.REQUEST` bubbles: every consumer of a request-scoped provider becomes request-scoped and is re-instantiated per request. For "who is the current user" style needs, prefer `AsyncLocalStorage` (via `nestjs-cls`) or pass context explicitly:

```typescript
@Injectable() // singleton - no scope option
export class AuditService {
  constructor(private readonly cls: ClsService) {}
  log(action: string) {
    this.cls.get('userId'); // per-request data without per-request instantiation
  }
}
```

**Global ValidationPipe with the three flags that matter** (in `main.ts`):

```typescript
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,            // strip unknown properties
  forbidNonWhitelisted: true, // 400 on unknown properties
  transform: true,            // plain body -> DTO instance, enables @Type coercion
}));
```

**Custom providers use tokens, not strings scattered inline:**

```typescript
export const REDIS = Symbol('REDIS');

@Module({
  providers: [{ provide: REDIS, useFactory: (cfg: ConfigService) => new Redis(cfg.getOrThrow('REDIS_URL')), inject: [ConfigService] }],
  exports: [REDIS],
})
export class RedisModule {}
// consumer: constructor(@Inject(REDIS) private readonly redis: Redis) {}
```

**e2e tests must mirror production bootstrap** - apply the same global pipes/filters the real `main.ts` applies, or e2e tests pass while production rejects:

```typescript
const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
app = moduleRef.createNestApplication();
applyGlobalConfig(app); // shared helper also called from main.ts
await app.init();
```

## Common Mistakes

- **Marking providers `Scope.REQUEST` for convenience.** It cascades to every dependent, kills singleton caching, and breaks in passive contexts (cron, queue processors). Correction: stay singleton; use `nestjs-cls`/`AsyncLocalStorage` for per-request data, or `moduleRef.resolve()` with a `ContextId` when you truly need per-request instances.
- **Assuming providers are visible app-wide.** A provider is injectable only inside its module unless `exports`-ed and the consumer `imports` that module. "Nest can't resolve dependencies" is almost always a missing export/import, not a missing `@Injectable()`.
- **Wrong mental model of execution order.** Request path: middleware → guards → interceptors (pre) → pipes → handler → interceptors (post, reverse registration order) → exception filters. Guards run *before* interceptors, so an interceptor cannot run for a request a guard rejected; filters catch errors from all of the preceding stages except middleware.
- **ValidationPipe without `whitelist`/`transform`.** Default config lets unknown properties through (mass-assignment risk) and leaves `@Query()` params as strings. Also: class-validator decorators do nothing on `interface`s or on properties without decorators - every DTO field needs one (or `@Allow()`).
- **Reading `process.env` directly in providers.** Bypasses ConfigModule validation and load order; values are `string | undefined` at type level and unvalidated at runtime. Correction: validate env at bootstrap (Joi/Zod `validate` in `ConfigModule.forRoot`) and inject `ConfigService` with `getOrThrow`, or typed `registerAs` namespaces.
- **Passport confusion: `@nestjs/jwt` and `passport-jwt` are not alternatives for the same job.** `@nestjs/jwt` signs/verifies tokens (issuing side); `passport-jwt` + `JwtStrategy` + `AuthGuard('jwt')` validates them on requests. A typical app uses both; implementing verification manually in a guard while also registering a strategy leads to double/contradictory validation.
- **Storing raw refresh tokens, or not rotating them.** Store only a hash, rotate on every refresh, and revoke the family on reuse detection. See `references/auth.md`.
- **`@Body() body: any` plus manual checks instead of DTOs.** Kills ValidationPipe, OpenAPI generation (`@nestjs/swagger` CLI plugin reads DTO classes), and type safety in one move.
