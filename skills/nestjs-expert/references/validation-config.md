# Validation, Configuration, and OpenAPI (NestJS 11)

## ValidationPipe + class-validator (the default stack)

Install: `class-validator class-transformer`. Register once, globally:

```typescript
// main.ts
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,             // strip properties without decorators
  forbidNonWhitelisted: true,  // 400 instead of silently stripping
  transform: true,             // plain object -> class instance; enables coercion
  transformOptions: { enableImplicitConversion: false }, // keep coercion explicit
}));
```

Or via DI so the pipe can be configured from ConfigService:
`providers: [{ provide: APP_PIPE, useClass: ValidationPipe }]`.

DTO rules that actually bite:

```typescript
export class CreateUserDto {
  @IsEmail()
  email!: string;

  @IsString()
  @MinLength(12)
  password!: string;

  @IsOptional()               // allows the field to be absent - validators still run when present
  @IsInt()
  @Type(() => Number)         // query/params arrive as strings; coerce explicitly
  age?: number;

  @ValidateNested({ each: true })
  @Type(() => AddressDto)     // REQUIRED for nested validation - without @Type, nested objects are NOT validated
  @IsArray()
  addresses!: AddressDto[];
}
```

- Decorators are per-property. An undecorated property is stripped by
  `whitelist` (add `@Allow()` to keep it un-validated).
- DTOs must be `class`es. Interfaces/types erase at runtime - the pipe sees
  metatype `Object` and skips validation entirely.
- `@Query()` and `@Param()` values are strings; without `@Type(() => Number)`
  (or implicit conversion), `@IsInt()` fails on `"5"`.
- Update DTOs: `export class UpdateUserDto extends PartialType(CreateUserDto) {}` -
  import `PartialType` from `@nestjs/swagger` (keeps OpenAPI metadata), not
  `@nestjs/mapped-types`, if swagger is in use.

## Zod pipes (the typed alternative)

class-validator duplicates types (class + decorators). Zod derives the static
type from the schema. Trade-off: no decorator metadata, so `@nestjs/swagger`
cannot introspect it - pair with `nestjs-zod` (v5+, Zod 4) which patches
`createZodDto` classes into swagger.

```typescript
import { z } from 'zod';
import { createZodDto, ZodValidationPipe } from 'nestjs-zod';

const CreateUserSchema = z.object({
  email: z.email(),                       // Zod 4: top-level, not z.string().email()
  password: z.string().min(12),
  age: z.coerce.number().int().optional(), // coercion lives in the schema
});
export class CreateUserDto extends createZodDto(CreateUserSchema) {}

// global registration
providers: [{ provide: APP_PIPE, useClass: ZodValidationPipe }]

// controller - identical shape to class-validator usage
@Post() create(@Body() dto: CreateUserDto) {} // dto is the inferred Zod type
```

Choosing: existing codebase's lib wins. Greenfield: Zod if the team already
uses it (shared schemas with frontend, tRPC-style typing); class-validator if
heavy `@nestjs/swagger` decorator usage or the CLI plugin matters. Do not mix
both pipes globally.

## ConfigModule + env validation

Fail at bootstrap, not at first request. Two supported approaches:

**Joi schema:**

```typescript
ConfigModule.forRoot({
  isGlobal: true,
  cache: true,
  validationSchema: Joi.object({
    NODE_ENV: Joi.string().valid('development', 'production', 'test').required(),
    PORT: Joi.number().default(3000),
    DATABASE_URL: Joi.string().uri().required(),
    JWT_SECRET: Joi.string().min(32).required(),
  }),
  validationOptions: { allowUnknown: true, abortEarly: false },
})
```

**Zod via `validate` (no extra dependency if Zod is already present):**

```typescript
const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'production', 'test']),
  PORT: z.coerce.number().default(3000),
  DATABASE_URL: z.url(),
  JWT_SECRET: z.string().min(32),
});
export type Env = z.infer<typeof EnvSchema>;

ConfigModule.forRoot({
  isGlobal: true,
  validate: (config) => EnvSchema.parse(config), // throws with all issues listed
})
```

Consumption - always `getOrThrow`, typed:

```typescript
constructor(private readonly config: ConfigService<Env, true>) {}
// ...
const url = this.config.getOrThrow('DATABASE_URL', { infer: true }); // string
```

## Namespaced config with registerAs

For grouped config, `registerAs` gives a typed token injectable without
ConfigService string keys:

```typescript
// config/database.config.ts
export default registerAs('database', () => ({
  url: process.env.DATABASE_URL!,        // the ONLY place process.env is read
  poolSize: parseInt(process.env.DB_POOL_SIZE ?? '10', 10),
}));

// registration
ConfigModule.forRoot({ isGlobal: true, load: [databaseConfig] })

// injection - fully typed, no magic strings
constructor(
  @Inject(databaseConfig.KEY)
  private readonly db: ConfigType<typeof databaseConfig>,
) {}
```

Validate namespaces too: run the schema inside the factory and throw on error,
since `validationSchema` only covers flat `process.env`.

## Config load-order pitfalls

- **`process.env` at module decorator evaluation time is too early** when using
  `.env` files: decorators evaluate at import, before `ConfigModule.forRoot`
  loads the file. Symptoms: `JwtModule.register({ secret: process.env.JWT_SECRET })`
  gets `undefined`. Fix: always use the async variant with DI:

```typescript
JwtModule.registerAsync({
  inject: [ConfigService],
  useFactory: (cfg: ConfigService) => ({
    secret: cfg.getOrThrow('JWT_SECRET'),
    signOptions: { expiresIn: '15m' },
  }),
})
```

- `envFilePath: ['.env.local', '.env']` - first file wins per variable; real
  environment variables always override file values.
- `ignoreEnvFile: true` in production images; inject env via the platform.
- Secrets do not belong in `.env` committed files; wire cloud secret managers
  in the `load` factories (keep the resolution async-capable with
  `ConfigModule.forFeature` + async factories).
- `cache: true` freezes reads; do not mutate `process.env` at runtime and
  expect ConfigService to see it (tests: use `ConfigModule` overrides instead).

## Error shape

ValidationPipe (class-validator) 400 body:

```json
{ "statusCode": 400, "message": ["email must be an email"], "error": "Bad Request" }
```

To customize globally, pass `exceptionFactory` to the pipe rather than
string-parsing messages in a filter:

```typescript
new ValidationPipe({
  exceptionFactory: (errors) =>
    new BadRequestException(
      errors.map((e) => ({ field: e.property, issues: Object.values(e.constraints ?? {}) })),
    ),
})
```

## OpenAPI from DTOs (@nestjs/swagger)

```typescript
// main.ts
const config = new DocumentBuilder()
  .setTitle('API').setVersion('1.0')
  .addBearerAuth()               // pairs with @ApiBearerAuth() on controllers
  .build();
SwaggerModule.setup('docs', app, () => SwaggerModule.createDocument(app, config));
```

Two ways to get DTO fields into the spec - pick ONE:

1. **CLI plugin (preferred)** - in `nest-cli.json`:
   `"compilerOptions": { "plugins": ["@nestjs/swagger"] }`. It infers
   `@ApiProperty` from TypeScript types and class-validator decorators, so DTOs
   stay clean. Caveats: only works on files matching `*.dto.ts` / `*.entity.ts`
   by default (configurable via `dtoFileNameSuffix`), and only through the Nest
   CLI build - plain `tsc` or unconfigured SWC builds silently emit an empty
   schema.
2. **Manual `@ApiProperty()`** on every field when the plugin is not in play.

Decorators that still matter even with the plugin:

```typescript
@ApiTags('users')
@ApiBearerAuth()
@Controller('users')
export class UsersController {
  @Post()
  @ApiOperation({ summary: 'Register a user' })
  @ApiCreatedResponse({ type: UserResponseDto })   // response types are NEVER inferred
  @ApiConflictResponse({ description: 'email already registered' })
  create(@Body() dto: CreateUserDto): Promise<UserResponseDto> {}
}
```

- Response DTOs must be classes referenced in `@Api*Response({ type })` -
  return-type inference does not reach the spec, and `Promise<T>` erases.
- Generics/unions need `@ApiExtraModels` + `getSchemaPath` with `oneOf`.
- `PartialType`/`PickType`/`OmitType` must come from `@nestjs/swagger` (not
  `@nestjs/mapped-types`) or derived DTOs lose their swagger metadata.
- Zod DTOs: `nestjs-zod`'s `createZodDto` classes are patched into swagger via
  its `cleanupOpenApiDoc` helper; without it Zod schemas produce empty models.
