# Testing and Background Jobs (NestJS 11)

## Unit tests: Test.createTestingModule with overridden providers

Unit-test services against mocked dependencies via the DI container - this
catches wiring mistakes that `new UsersService(mock)` construction hides:

```typescript
describe('UsersService', () => {
  let service: UsersService;
  const prisma = {
    user: { findUnique: jest.fn(), create: jest.fn() },
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    const moduleRef = await Test.createTestingModule({
      providers: [
        UsersService,
        { provide: PrismaService, useValue: prisma }, // token must match the injected one
      ],
    }).compile();
    service = moduleRef.get(UsersService);
  });

  it('maps unique violation to 409', async () => {
    prisma.user.create.mockRejectedValue(
      new Prisma.PrismaClientKnownRequestError('dup', { code: 'P2002', clientVersion: 'x' }),
    );
    await expect(service.register({ email: 'a@b.c', password: 'x'.repeat(12) }))
      .rejects.toBeInstanceOf(ConflictException);
  });
});
```

- Mock at the token the class actually injects. `@Inject(CACHE)` requires
  `{ provide: CACHE, useValue: ... }`, not the class name.
- Request-scoped providers: `moduleRef.get()` throws - use
  `await moduleRef.resolve(TheService)` (returns a per-context instance).
- Guards/interceptors are not executed in unit tests of a controller class;
  calling controller methods directly bypasses the pipeline entirely. Pipeline
  behavior belongs in e2e tests.

## e2e tests: real HTTP through supertest

```typescript
// test/users.e2e-spec.ts
describe('Users (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({ imports: [AppModule] })
      .overrideProvider(MailerService)      // stub externals, keep the rest real
      .useValue({ send: jest.fn() })
      .overrideGuard(ThrottlerGuard)        // guards need overrideGuard, not overrideProvider
      .useValue({ canActivate: () => true })
      .compile();

    app = moduleRef.createNestApplication();
    applyGlobalConfig(app); // SAME helper main.ts uses: pipes, filters, prefix, versioning
    await app.init();
  });

  afterAll(async () => { await app.close(); }); // otherwise Jest hangs on open handles

  it('rejects unknown properties', () =>
    request(app.getHttpServer())
      .post('/users')
      .send({ email: 'a@b.co', password: 'longenough123', admin: true })
      .expect(400));

  it('creates a user', async () => {
    const res = await request(app.getHttpServer())
      .post('/users')
      .send({ email: 'a@b.co', password: 'longenough123' })
      .expect(201);
    expect(res.body).toMatchObject({ email: 'a@b.co' });
    expect(res.body).not.toHaveProperty('passwordHash');
  });
});
```

Bootstrap parity is the #1 e2e footgun: `createNestApplication()` applies
NOTHING from `main.ts`. Extract every `app.useGlobal*`, `setGlobalPrefix`,
`enableVersioning`, cookie/body parser setup into a shared
`applyGlobalConfig(app)` and call it from both `main.ts` and every e2e
bootstrap. Globals registered via `APP_PIPE`/`APP_GUARD` providers are exempt
(they live in the module graph and load automatically - one more reason to
prefer them).

Authenticated requests - log in once, reuse the token:

```typescript
const { body } = await request(app.getHttpServer())
  .post('/auth/login').send({ email, password }).expect(201);
await request(app.getHttpServer())
  .get('/me').set('Authorization', `Bearer ${body.accessToken}`).expect(200);
```

## Real databases in e2e: Testcontainers

Mocked repositories make e2e tests lie. Spin up Postgres per suite:

```typescript
import { PostgreSqlContainer, StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { execSync } from 'node:child_process';

let pg: StartedPostgreSqlContainer;

beforeAll(async () => {
  pg = await new PostgreSqlContainer('postgres:17').start();
  process.env.DATABASE_URL = pg.getConnectionUri();  // BEFORE the testing module compiles
  execSync('npx prisma migrate deploy', { env: process.env });
  // ...then build the testing module as above
}, 120_000); // container pull can exceed the default 5s timeout

afterAll(async () => { await app.close(); await pg.stop(); });
```

Truncate between tests (`TRUNCATE ... RESTART IDENTITY CASCADE`) rather than
recreating the app. Run e2e serially (`maxWorkers: 1` or per-worker
databases) - parallel workers sharing one DB produce flaky, order-dependent
failures.

## BullMQ queues (@nestjs/bullmq)

`@nestjs/bull` (Bull v3) is legacy; NestJS 11 pairs with `@nestjs/bullmq`.

```typescript
// registration
BullModule.forRootAsync({
  inject: [ConfigService],
  useFactory: (cfg: ConfigService) => ({
    connection: { url: cfg.getOrThrow('REDIS_URL') }, // BullMQ: 'connection', not Bull's 'redis'
  }),
}),
BullModule.registerQueue({ name: 'email' }),

// producer
constructor(@InjectQueue('email') private readonly emailQueue: Queue) {}
await this.emailQueue.add('welcome', { userId }, {
  attempts: 3,
  backoff: { type: 'exponential', delay: 1000 },
  removeOnComplete: 1000, removeOnFail: 5000, // unbounded job retention fills Redis
});

// consumer - one class per queue; NAMED jobs are dispatched by a switch, not decorators
@Processor('email', { concurrency: 5 })
export class EmailProcessor extends WorkerHost {
  constructor(private readonly mailer: MailerService) { super(); } // DI works; keep it singleton
  async process(job: Job<{ userId: string }>) {
    switch (job.name) {
      case 'welcome': return this.mailer.sendWelcome(job.data.userId);
      default: throw new Error(`unknown job ${job.name}`);
    }
  }
  @OnWorkerEvent('failed')
  onFailed(job: Job, err: Error) { /* log with job.id, attemptsMade */ }
}
```

BullMQ facts LLMs get wrong:

- `WorkerHost.process()` is the single entry point; the old Bull
  `@Process('name')` per-method decorators do not exist in `@nestjs/bullmq`.
- A thrown error triggers retry per `attempts`; returning normally = success.
  Swallowing errors in try/catch silently marks poison jobs successful.
- Processors run in the main process by default; CPU-heavy work needs
  sandboxed processors (`processor: path-to-file`) or a separate worker app
  sharing the queue module.
- Repeatable jobs: `queue.upsertJobScheduler('nightly', { pattern: '0 3 * * *' }, ...)`
  - the modern scheduler API; old `repeat` options create duplicate schedulers
  on redeploy.

### Testing queue interactions

Unit: assert the producer enqueued -
`{ provide: getQueueToken('email'), useValue: { add: jest.fn() } }`, then call
the processor's `process()` directly with a fake `Job` object. e2e with real
Redis (testcontainers `redis:7`): add a job, then wait on worker events, never
on `setTimeout`:

```typescript
const worker = app.get(EmailProcessor);
await new Promise((resolve, reject) => {
  worker.worker.on('completed', resolve);
  worker.worker.on('failed', (_job, err) => reject(err));
  queue.add('welcome', { userId });
});
```

## Jest config gotchas

- Two configs: unit (`jest` key, `rootDir: src`) and e2e
  (`test/jest-e2e.json`, `testRegex: .e2e-spec.ts$`); `npm test` must not pick
  up e2e specs.
- `ts-jest` + `isolatedModules` for speed; or SWC (`@swc/jest`) - but SWC
  needs `legacyDecorator`/`decoratorMetadata` flags on or DI metadata breaks.
- Open-handle hangs after green tests: missing `app.close()`, un-stopped
  containers, or a live Redis connection from BullMQ - close queues/workers in
  `afterAll`.
