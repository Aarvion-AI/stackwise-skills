# Auth: OAuth2 Password Flow + JWT

Standard setup: clients POST credentials to `/auth/token` (form-encoded, per OAuth2), receive a short-lived JWT access token, and send it as `Authorization: Bearer <token>`.

Dependencies: `uv add pyjwt pwdlib[argon2] python-multipart` (python-multipart is required for the OAuth2 form; passlib[bcrypt] is the older alternative to pwdlib).

## Password hashing

```python
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()   # argon2id

def hash_password(plain: str) -> str:
    return password_hash.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)
```

Never store plaintext, never use fast hashes (sha256/md5) for passwords, never log passwords or tokens. Bcrypt note if using passlib: bcrypt truncates input at 72 bytes.

## JWT create/decode

```python
from datetime import UTC, datetime, timedelta
import jwt  # PyJWT

ALGORITHM = "HS256"

def create_access_token(subject: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)

def decode_token(token: str, settings: Settings) -> dict:
    # raises jwt.InvalidTokenError (incl. ExpiredSignatureError) on any failure
    return jwt.decode(
        token, settings.jwt_secret.get_secret_value(), algorithms=[ALGORITHM]
    )
```

- Always pass `algorithms=[...]` explicitly on decode - omitting it or trusting the token header enables algorithm-confusion attacks.
- `exp` is verified by PyJWT automatically when present; always set it. Keep access tokens short (15 min or less) if you add refresh tokens.
- JWTs are signed, NOT encrypted - anyone can read claims. `sub` (user id) and scopes only; no emails, names, or secrets in claims.
- Secret comes from settings (`SecretStr`), never a literal in code.

## Token endpoint

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["auth"])

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/token", response_model=TokenOut)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbDep,
    settings: SettingsDep,
) -> TokenOut:
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form.password, user.hashed_password):
        # same message for both cases: don't reveal which one failed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(access_token=create_access_token(str(user.id), settings))
```

`OAuth2PasswordRequestForm` reads form fields `username`/`password` - clients must send `application/x-www-form-urlencoded`, not JSON. Sending JSON here is the classic mistake (yields 422 on `username`).

## Current-user dependency

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
TokenDep = Annotated[str, Depends(oauth2_scheme)]

async def get_current_user(token: TokenDep, db: DbDep, settings: SettingsDep) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, settings)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exc
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]

@router.get("/users/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> User:
    return user
```

Status-code semantics: missing/invalid credentials → 401 with `WWW-Authenticate: Bearer`; authenticated but not allowed → 403. `OAuth2PasswordBearer` returns 401 by itself when the header is absent (set `auto_error=False` only for optional-auth endpoints, then handle `token: str | None`).

`tokenUrl` is what makes the Swagger UI "Authorize" button work - it must match the actual token route path (relative, no leading slash).

## Roles and scopes

Simple role gate - layer a dependency on top of `CurrentUser`:

```python
async def get_current_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

AdminUser = Annotated[User, Depends(get_current_admin)]
```

OAuth2 scopes, when roles aren't enough - put a `scopes` claim in the token and check with `SecurityScopes`:

```python
from fastapi import Security
from fastapi.security import SecurityScopes

async def get_user_with_scopes(
    security_scopes: SecurityScopes, token: TokenDep, db: DbDep, settings: SettingsDep
) -> User:
    payload = decode_token(token, settings)
    token_scopes = set(payload.get("scopes", []))
    if not set(security_scopes.scopes) <= token_scopes:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions",
            headers={"WWW-Authenticate": f'Bearer scope="{security_scopes.scope_str}"'},
        )
    return await load_user(db, payload["sub"])

@router.delete("/items/{item_id}")
async def delete_item(
    user: Annotated[User, Security(get_user_with_scopes, scopes=["items:write"])],
    item_id: int,
): ...
```

Use `Security(...)` (not `Depends`) when passing scopes.

## Refresh tokens, briefly

If sessions must outlive the access token: issue an opaque, random refresh token (store its hash server-side with expiry + user id), return it alongside the access token, add `/auth/refresh` that validates it, rotates it (invalidate the old one), and mints a new access token. Do not implement refresh as "a JWT with a longer exp" without server-side revocation - you lose the ability to log users out.

## Checklist

- [ ] Argon2/bcrypt hashing; no plaintext anywhere including logs
- [ ] `exp` + `iat` in every token; decode with pinned `algorithms`
- [ ] 401 + `WWW-Authenticate` for bad credentials; 403 for insufficient rights
- [ ] Identical error for unknown-user vs wrong-password
- [ ] Secret from settings/env; different per environment
- [ ] Token endpoint consumes form data, not JSON
