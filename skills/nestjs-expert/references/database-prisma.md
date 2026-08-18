# Database Integration: Prisma and TypeORM (NestJS 11)

## Choosing

- **Prisma** (default for greenfield): schema-first, generated typed client,
  best-in-class migrations (`prisma migrate`), no decorators/entities. Weaker
  at: dynamic queries, DB-specific SQL (use `$queryRaw` / typedSQL).
- **TypeORM**: entity classes with decorators, `@nestjs/typeorm` first-party
  module, repository pattern, better for gradual/legacy schemas and dynamic
  QueryBuilder work. Weaker at: migration ergonomics, type safety of raw
  results.
- Match the existing project. Do not introduce a second ORM.

## Prisma integration

There is no official `@nestjs/prisma`; the pattern is a service extending the
generated client:

```typescript
// prisma/prisma.service.ts
import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    super({ log: ['warn', 'error'] });
  }
  async onModuleInit() { await this.$connect(); }
  async onModuleDestroy() { await this.$disconnect(); }
}

// prisma/prisma.module.ts
@Global()
@Module({ providers: [PrismaService], exports: [PrismaService] })
export class PrismaModule {}
```

Notes:

- Prisma 6+ generates the client via `prisma generate`; CI must run it before
  `tsc` (`postinstall` script or explicit build step).
- Do NOT make PrismaService request-scoped for multi-tenancy; use one client
  per tenant cached in a singleton map, or RLS with `$extends`.
- `enableShutdownHooks` gymnastics from old docs are obsolete - Prisma 5+ no
  longer hijacks `beforeExit`; `onModuleDestroy` + `app.enableShutdownHooks()`
  is sufficient.

Usage in services - inject the service, keep queries in the service layer:

```typescript
@Injectable()
export class UsersService {
  constructor(private readonly prisma: PrismaService) {}

  findByEmail(email: string) {
    return this.prisma.user.findUnique({ where: { email } });
  }

  async register(dto: CreateUserDto) {
    try {
      return await this.prisma.user.create({ data: dto });
    } catch (e) {
      if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002') {
        throw new ConflictException('email already registered'); // unique violation
      }
      throw e;
    }
  }
}
```

Map Prisma errors to HTTP in the service or a dedicated exception filter -
never let `PrismaClientKnownRequestError` leak as a 500 with internals.
Common codes: `P2002` unique constraint, `P2025` record not found (throw
`NotFoundException`), `P2003` FK violation.

### Prisma transactions

```typescript
// interactive transaction - the tx client MUST be used inside, not this.prisma
async transferCredits(fromId: string, toId: string, amount: number) {
  return this.prisma.$transaction(async (tx) => {
    const from = await tx.user.update({
      where: { id: fromId }, data: { credits: { decrement: amount } },
    });
    if (from.credits < 0) throw new BadRequestException('insufficient credits');
    return tx.user.update({ where: { id: toId }, data: { credits: { increment: amount } } });
  }, { isolationLevel: 'Serializable' });
}
```

Cross-service transactions: pass the `tx` client down as a parameter, or adopt
`@nestjs-cls/transactional` (CLS-propagated transactions) - do not create a
request-scoped "current transaction" provider.

### Migrations

- Dev: `npx prisma migrate dev --name add_users` (creates + applies + regenerates).
- Prod/CI: `npx prisma migrate deploy` (applies committed migrations only, never
  generates). Never run `migrate dev` or `db push` against production.

## TypeORM integration

```typescript
// app.module.ts
TypeOrmModule.forRootAsync({
  inject: [ConfigService],
  useFactory: (cfg: ConfigService) => ({
    type: 'postgres',
    url: cfg.getOrThrow('DATABASE_URL'),
    autoLoadEntities: true,   // picks up forFeature() entities - avoids stale entity arrays
    synchronize: false,       // NEVER true outside local scratch DBs - drops/alters prod tables
    migrationsRun: false,     // run migrations via CLI/CD step, not app boot
  }),
}),

// users.module.ts
@Module({
  imports: [TypeOrmModule.forFeature([User])],
  providers: [UsersService],
})
export class UsersModule {}

// users.service.ts
@Injectable()
export class UsersService {
  constructor(@InjectRepository(User) private readonly users: Repository<User>) {}

  findByEmail(email: string) {
    return this.users.findOne({ where: { email } });
  }
}
```

Entity essentials (TypeORM 0.3.x):

```typescript
@Entity('users')
export class User {
  @PrimaryGeneratedColumn('uuid') id!: string;
  @Column({ unique: true }) email!: string;
  @Column({ select: false }) passwordHash!: string;   // excluded by default; addSelect to read
  @ManyToOne(() => Org, (o) => o.users, { onDelete: 'CASCADE' }) org!: Org;
  @CreateDateColumn() createdAt!: Date;
}
```

- Relations are lazy-less by default in 0.3: nothing loads unless
  `relations: { org: true }` or a QueryBuilder join is specified.
- `findOne` requires a `where`; passing an id directly was removed in 0.3
  (`findOneBy({ id })` is the shorthand).

### TypeORM transactions

Repository methods ignore ambient transactions - you must use the
transactional manager:

```typescript
constructor(private readonly dataSource: DataSource) {}

async transfer(fromId: string, toId: string, amount: number) {
  return this.dataSource.transaction('SERIALIZABLE', async (manager) => {
    const repo = manager.getRepository(Account);
    await repo.decrement({ id: fromId }, 'balance', amount);
    await repo.increment({ id: toId }, 'balance', amount);
  });
}
```

Migrations: `typeorm migration:generate -d src/data-source.ts src/migrations/AddUsers`
against a separate `DataSource` file (the Nest module config is not reusable by
the CLI); commit generated migrations and review the SQL - `generate` can emit
destructive drops on renamed columns.

## Connection lifecycle and pooling

- One pool per app instance; size = `min(expected_concurrency, db_limit / instances)`.
  Prisma: `connection_limit` in the URL; TypeORM: `extra: { max: 10 }`.
- Serverless (Lambda/Cloud Run scale-to-many): use a pooler (pgBouncer, RDS
  Proxy, Prisma Accelerate); direct pools exhaust Postgres connections.
- Health checks: `@nestjs/terminus` - `PrismaHealthIndicator` /
  `TypeOrmHealthIndicator` wired into `/health`, not hand-rolled `SELECT 1`
  controllers.
