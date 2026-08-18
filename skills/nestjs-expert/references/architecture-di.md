# Architecture and Dependency Injection (NestJS 11)

## Module visibility rules

A provider is injectable only within the module that declares it, unless exported.
The consumer module must import the exporting module. `@Injectable()` alone does
nothing for visibility.

```typescript
@Module({
  providers: [UsersService, UsersRepository], // UsersRepository stays private
  exports: [UsersService],                    // only this crosses module boundaries
})
export class UsersModule {}

@Module({
  imports: [UsersModule], // required to inject UsersService here
  providers: [OrdersService],
})
export class OrdersModule {}
```

- Re-export a whole module to forward its exports: `exports: [UsersModule]`.
- `@Global()` modules are visible everywhere after a single import in the root
  module. Reserve for true cross-cutting infra (config, logging). Overuse makes
  the dependency graph invisible.
- "Nest can't resolve dependencies of X (?, Y)" - the `?` position names the
  missing token. Fix order: (1) is it provided anywhere, (2) is it exported,
  (3) does the consumer's module import the exporter, (4) token mismatch
  (interface types erase - use a class or `@Inject(TOKEN)`).

## Custom providers

```typescript
export const CACHE = Symbol('CACHE');

@Module({
  providers: [
    { provide: CACHE, useClass: RedisCache },              // swap implementations
    { provide: 'API_URL', useValue: 'https://api.local' }, // constants
    {
      provide: HttpAgent,
      useFactory: (cfg: ConfigService) => new HttpAgent(cfg.getOrThrow('TIMEOUT')),
      inject: [ConfigService],
    },
    { provide: LegacyToken, useExisting: CACHE },          // alias, same instance
  ],
  exports: [CACHE],
})
export class InfraModule {}
```

Interfaces cannot be injection tokens (erased at runtime). Use `Symbol` or an
abstract class as the token; abstract classes double as the type.

## Provider scopes and the request-scope cost

| Scope | Instances | When |
|-------|-----------|------|
| `DEFAULT` | one per app | Always, unless proven otherwise |
| `REQUEST` | one per request | Provider genuinely needs per-request state AND alternatives ruled out |
| `TRANSIENT` | one per injection site | Stateful helpers where sharing is a bug (e.g. a logger with a mutable context prefix) |

Request scope **bubbles up**: if `UsersService` injects a request-scoped
provider, `UsersService` becomes request-scoped, and so does its controller -
the whole chain is re-instantiated on every request. Costs:

- Garbage-collection and construction overhead on every request in the chain.
- Passive contexts (cron jobs, BullMQ processors, event handlers) have no
  request, so resolution throws unless you use `ContextIdFactory` manually.
- `OnModuleInit` etc. do not fire per request.

Escape hatches, in order of preference:

1. **`nestjs-cls` / `AsyncLocalStorage`** - per-request data in singleton
   providers. This is the default answer to "current user/tenant in a service".

```typescript
// app.module.ts
ClsModule.forRoot({
  middleware: { mount: true, setup: (cls, req) => cls.set('tenantId', req.headers['x-tenant-id']) },
})
// any singleton service
constructor(private readonly cls: ClsService) {}
getTenant() { return this.cls.get('tenantId'); }
```

2. **Durable providers** - request-scoped but memoized per tenant via a custom
   `ContextIdStrategy`; use for multi-tenant connection pools.
3. **Manual resolution** for the rare true per-request instance:

```typescript
const contextId = ContextIdFactory.getByRequest(request);
const service = await this.moduleRef.resolve(ReportBuilder, contextId);
```

`REQUEST` injection: `@Inject(REQUEST) private readonly req: Request` - only
inside providers that are already request-scoped.

## Circular dependencies

Prefer refactoring: extract the shared piece into a third module both import.
If unavoidable, `forwardRef` must appear on **both** sides:

```typescript
// users.module.ts                            // auth.module.ts
imports: [forwardRef(() => AuthModule)]       imports: [forwardRef(() => UsersModule)]
// and in the providers:
constructor(@Inject(forwardRef(() => AuthService)) private auth: AuthService) {}
```

Barrel files (`index.ts`) are a common hidden cause - an import cycle through a
barrel produces `undefined` tokens at decorator evaluation time
("Nest cannot create the X instance ... is undefined"). Import concrete files
in module definitions, not barrels.

## Lifecycle hooks

Order at startup: `OnModuleInit` (per module, children first) →
`OnApplicationBootstrap` → app listens. Shutdown (requires
`app.enableShutdownHooks()` in `main.ts`, needed for SIGTERM in containers):
`OnModuleDestroy` → `BeforeApplicationShutdown` → `OnApplicationShutdown`.

```typescript
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  async onModuleInit() { await this.$connect(); }
  async onModuleDestroy() { await this.$disconnect(); }
}
```

## Request pipeline execution order

```
incoming request
  → middleware            (Express/Fastify layer; runs even for 404s within prefix)
  → guards                (global → controller → route; first false/throw = 403/thrown)
  → interceptors, pre     (global → controller → route)
  → pipes                 (global → controller → route → param; param pipes last)
  → route handler
  → interceptors, post    (REVERSE order - route → controller → global)
  → exception filters     (route → controller → global; first matching filter wins)
→ response
```

Consequences LLMs get wrong:

- A guard rejection means interceptors never ran - do not put "always log the
  request" logic in an interceptor; use middleware.
- Pipes run **after** guards: a guard reading `request.body` sees the raw,
  unvalidated payload.
- Exception filters do not catch middleware errors (those hit the framework's
  error layer), but do catch guard/interceptor/pipe/handler errors.
- Post-interceptors run in reverse registration order - a global timing
  interceptor wraps everything, so it observes time spent in inner interceptors.
- `APP_GUARD` / `APP_INTERCEPTOR` / `APP_FILTER` / `APP_PIPE` providers register
  globals **inside DI** (unlike `app.useGlobal*` which cannot inject deps):

```typescript
providers: [{ provide: APP_GUARD, useClass: JwtAuthGuard }] // guard can inject services
```

## Dynamic modules

For configurable infra modules, implement the async options pattern (or extend
`ConfigurableModuleBuilder` which generates it):

```typescript
export class QueueModule {
  static forRootAsync(options: {
    useFactory: (...args: any[]) => QueueOptions;
    inject?: any[];
    imports?: any[];
  }): DynamicModule {
    return {
      module: QueueModule,
      imports: options.imports ?? [],
      providers: [
        { provide: QUEUE_OPTIONS, useFactory: options.useFactory, inject: options.inject ?? [] },
        QueueService,
      ],
      exports: [QueueService],
    };
  }
}
```

`forRoot`/`forRootAsync` = configure once in the root; `forFeature` = register
per-module resources (entities, queues); `register` = per-consumer config.
