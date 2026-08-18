# Authentication: JWT, Passport, Refresh Flows (NestJS 11)

## The division of labor (source of most confusion)

- `@nestjs/jwt` - signs and verifies tokens. Used by *your* AuthService to
  issue access/refresh tokens at login. It does not guard routes.
- `passport-jwt` + `@nestjs/passport` - request-side validation. A
  `JwtStrategy` extracts + verifies the bearer token; `AuthGuard('jwt')`
  invokes it and attaches the result to `request.user`.
- A typical app uses **both**: `@nestjs/jwt` to mint, passport to check.
  Passport is optional - a plain guard calling `JwtService.verifyAsync` is a
  legitimate lighter-weight choice; pick one mechanism, never both on the same
  route.

## Setup

```typescript
// auth.module.ts
@Module({
  imports: [
    UsersModule,
    PassportModule,
    JwtModule.registerAsync({
      inject: [ConfigService],
      useFactory: (cfg: ConfigService) => ({
        secret: cfg.getOrThrow('JWT_SECRET'),
        signOptions: { expiresIn: '15m', issuer: 'api' },
      }),
    }),
  ],
  providers: [AuthService, JwtStrategy, JwtRefreshStrategy],
  controllers: [AuthController],
})
export class AuthModule {}
```

```typescript
// jwt.strategy.ts
@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy, 'jwt') {
  constructor(cfg: ConfigService) {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      secretOrKey: cfg.getOrThrow('JWT_SECRET'),
      ignoreExpiration: false, // the default, but be explicit
      issuer: 'api',
    });
  }
  // Runs AFTER signature+exp verification. Return value becomes request.user.
  async validate(payload: { sub: string; email: string }) {
    return { userId: payload.sub, email: payload.email };
  }
}
```

Key facts LLMs miss:

- `validate()` only runs if the token already verified. Throwing here (e.g.
  user banned) yields 401. Avoid a DB call here on hot paths - the point of
  JWTs is statelessness; if every request hits the DB, consider sessions.
- The strategy name string (`'jwt'`) must match `AuthGuard('jwt')`. Typos fail
  at runtime as "Unknown authentication strategy".
- Payload conventions: `sub` = user id. Keep the payload minimal; it is
  readable by anyone (base64, not encrypted).

## Global-guard-by-default with @Public escape hatch

Protect everything, opt routes out - safer than remembering `@UseGuards`:

```typescript
export const IS_PUBLIC = 'isPublic';
export const Public = () => SetMetadata(IS_PUBLIC, true);

@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {
  constructor(private reflector: Reflector) { super(); }
  canActivate(ctx: ExecutionContext) {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC, [
      ctx.getHandler(), ctx.getClass(),
    ]);
    return isPublic ? true : super.canActivate(ctx);
  }
}

// app.module.ts - register inside DI so Reflector injects
providers: [{ provide: APP_GUARD, useClass: JwtAuthGuard }]

// usage
@Public() @Post('login') login() {}
```

Current user decorator:

```typescript
export const CurrentUser = createParamDecorator(
  (_: unknown, ctx: ExecutionContext) => ctx.switchToHttp().getRequest().user,
);
```

## Login + refresh token rotation

Access token: short-lived (5-15 min), signed with `JWT_SECRET`. Refresh token:
long-lived (7-30 days), **different secret**, stored server-side **as a hash**,
rotated on every use.

```typescript
@Injectable()
export class AuthService {
  constructor(
    private readonly users: UsersService,
    private readonly jwt: JwtService,
    private readonly cfg: ConfigService,
  ) {}

  async login(email: string, password: string) {
    const user = await this.users.findByEmail(email);
    // Always run the compare: constant-time-ish, no user-enumeration timing leak
    const ok = await argon2.verify(user?.passwordHash ?? DUMMY_HASH, password);
    if (!user || !ok) throw new UnauthorizedException('invalid credentials');
    return this.issueTokens(user);
  }

  private async issueTokens(user: User) {
    const payload = { sub: user.id, email: user.email };
    const [accessToken, refreshToken] = await Promise.all([
      this.jwt.signAsync(payload), // module defaults: 15m, JWT_SECRET
      this.jwt.signAsync(payload, {
        secret: this.cfg.getOrThrow('JWT_REFRESH_SECRET'),
        expiresIn: '7d',
      }),
    ]);
    // store HASH only - a DB leak must not yield usable refresh tokens
    await this.users.setRefreshHash(user.id, await argon2.hash(refreshToken));
    return { accessToken, refreshToken };
  }

  async refresh(userId: string, presentedToken: string) {
    const user = await this.users.findById(userId);
    if (!user?.refreshHash) throw new UnauthorizedException();
    const matches = await argon2.verify(user.refreshHash, presentedToken);
    if (!matches) {
      // Reuse detected (rotated-out token presented): revoke the whole session
      await this.users.setRefreshHash(userId, null);
      throw new UnauthorizedException('refresh token reuse detected');
    }
    return this.issueTokens(user); // rotation: old refresh token is now invalid
  }

  async logout(userId: string) {
    await this.users.setRefreshHash(userId, null);
  }
}
```

Refresh strategy needs the raw token in `validate` - enable
`passReqToCallback`:

```typescript
@Injectable()
export class JwtRefreshStrategy extends PassportStrategy(Strategy, 'jwt-refresh') {
  constructor(cfg: ConfigService) {
    super({
      jwtFromRequest: ExtractJwt.fromBodyField('refreshToken'),
      secretOrKey: cfg.getOrThrow('JWT_REFRESH_SECRET'),
      passReqToCallback: true,
    });
  }
  validate(req: Request, payload: { sub: string }) {
    return { userId: payload.sub, refreshToken: req.body.refreshToken };
  }
}
```

Delivery: for browser clients prefer the refresh token in an
`httpOnly; Secure; SameSite=Strict; Path=/auth/refresh` cookie (then extract
with a cookie extractor, and CSRF-protect the refresh route); body field is
acceptable for native/mobile clients.

## Hard rules

- Hash passwords with argon2id (or bcrypt cost >= 12). Never SHA/MD5, never
  reversible.
- Access and refresh secrets MUST differ, both >= 32 random bytes. Prefer
  RS256/EdDSA keypairs when other services verify tokens.
- Never store raw refresh tokens or log any token. Never put roles you don't
  re-check, or any PII beyond an id/email, in the JWT payload.
- `expiresIn` on sign and `ignoreExpiration: false` on verify - an access
  token without `exp` is a permanent credential.
- Multi-device support: store one hash per session/device (a
  `refresh_sessions` table keyed by token family id in the JWT `jti`), not a
  single column, or logging in on a phone logs out the laptop.

## Debugging 401s on "valid" tokens

1. Different secret between sign and verify (most common - check both async
   factories resolve the same config source).
2. `Authorization: Bearer <token>` header malformed (missing `Bearer `, extra
   quotes) - `fromAuthHeaderAsBearerToken` returns null and passport 401s
   without detail.
3. Clock skew on `exp`/`iat`/`nbf` across services.
4. Strategy not registered in the module's `providers`, or name mismatch with
   `AuthGuard(name)`.
5. `validate()` returned a falsy value - passport treats it as rejection.
