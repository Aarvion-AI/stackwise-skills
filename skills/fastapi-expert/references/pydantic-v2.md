# Pydantic v2 for FastAPI

Pydantic 2.x only. Every v1 idiom here is listed so you can recognize and replace it - never write the v1 form in new code.

## v1 → v2 API map

| v1 (do not write) | v2 |
|---|---|
| `obj.dict()` | `obj.model_dump()` |
| `obj.json()` | `obj.model_dump_json()` |
| `Model.parse_obj(data)` | `Model.model_validate(data)` |
| `Model.parse_raw(json_str)` | `Model.model_validate_json(json_str)` |
| `Model.from_orm(db_obj)` | `Model.model_validate(db_obj)` + `from_attributes=True` |
| `Model.construct(...)` | `Model.model_construct(...)` |
| `obj.copy(update=...)` | `obj.model_copy(update=...)` |
| `Model.schema()` | `Model.model_json_schema()` |
| `Model.update_forward_refs()` | `Model.model_rebuild()` |
| `class Config:` | `model_config = ConfigDict(...)` |
| `@validator("f")` | `@field_validator("f")` |
| `@root_validator` | `@model_validator(mode="before"/"after")` |
| `Field(..., regex=...)` | `Field(pattern=...)` |
| `__fields__` | `model_fields` |
| `Optional[X]` meaning "not required" | Optional no longer implies a default; write `x: X \| None = None` |

## Model basics

```python
from pydantic import BaseModel, ConfigDict, Field, EmailStr, SecretStr

class UserBase(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=80)

class UserCreate(UserBase):
    password: SecretStr  # repr shows '**********'; use .get_secret_value()

class UserUpdate(BaseModel):
    # PATCH model: everything optional, distinguish "absent" from "null"
    email: EmailStr | None = None
    display_name: str | None = None

class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
```

PATCH handler - only apply fields the client actually sent:

```python
@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(user_id: int, data: UserUpdate, db: DbDep) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    await db.commit()
    return user
```

`exclude_unset` (not sent) vs `exclude_none` (sent as null) vs `exclude_defaults` - pick deliberately; `exclude_unset=True` is almost always what PATCH means.

## ConfigDict - the settings that matter

```python
class StrictIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",            # reject unknown fields (default is "ignore")
        str_strip_whitespace=True,
        frozen=True,               # immutable + hashable
    )

class OrmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # required for ORM reads
```

`extra="forbid"` on input models catches client typos as 422s instead of silently dropping fields.

## Validators

```python
from pydantic import field_validator, model_validator

class Signup(BaseModel):
    email: EmailStr
    password: str
    password_confirm: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()

    @model_validator(mode="after")
    def passwords_match(self) -> "Signup":
        if self.password != self.password_confirm:
            raise ValueError("passwords do not match")
        return self
```

- `@field_validator` is a classmethod; decorate with `@classmethod` under it.
- `mode="before"` receives raw input (good for coercing messy data); default `mode="after"` receives parsed values.
- `@model_validator(mode="after")` receives `self` and must return it. `mode="before"` is a classmethod receiving the raw dict.
- Raise `ValueError` (FastAPI turns it into a 422); never raise `HTTPException` inside a validator.

## Custom serialization

```python
from pydantic import field_serializer

class Event(BaseModel):
    when: datetime

    @field_serializer("when")
    def ser_when(self, v: datetime) -> str:
        return v.isoformat(timespec="seconds")
```

`model_dump()` returns Python objects (`datetime` stays `datetime`); `model_dump(mode="json")` returns JSON-safe primitives. FastAPI's `response_model` handles JSON mode for you - reach for `mode="json"` only when serializing manually.

## Annotated types and reusable constraints

```python
from typing import Annotated
from pydantic import StringConstraints, AfterValidator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$", max_length=64)]

def must_be_future(v: datetime) -> datetime:
    if v <= datetime.now(UTC):
        raise ValueError("must be in the future")
    return v

FutureDt = Annotated[datetime, AfterValidator(must_be_future)]

class Campaign(BaseModel):
    slug: Slug
    starts_at: FutureDt
```

## Discriminated unions (tagged payloads)

```python
from typing import Literal
from pydantic import Field

class CardPayment(BaseModel):
    kind: Literal["card"]
    card_token: str

class BankPayment(BaseModel):
    kind: Literal["bank"]
    iban: str

Payment = Annotated[CardPayment | BankPayment, Field(discriminator="kind")]

class CheckoutRequest(BaseModel):
    payment: Payment
```

Without the discriminator, unions try each member in order - slower and error messages are worse.

## TypeAdapter - validate non-model types

```python
from pydantic import TypeAdapter

users_adapter = TypeAdapter(list[UserRead])
users = users_adapter.validate_python(rows)      # list of ORM rows -> list[UserRead]
```

Build adapters once at module level; constructing a `TypeAdapter` per call is a hot-path cost.

## Settings with pydantic-settings

`pydantic-settings` is a separate package (`uv add pydantic-settings`); `BaseSettings` no longer lives in pydantic core.

```python
from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="APP_", extra="ignore"
    )
    database_url: str                    # reads APP_DATABASE_URL
    jwt_secret: SecretStr
    jwt_ttl_seconds: int = 900
    debug: bool = False

@lru_cache
def get_settings() -> Settings:
    return Settings()

SettingsDep = Annotated[Settings, Depends(get_settings)]
```

Inject settings via `Depends(get_settings)` rather than importing a module-level instance - tests can then override it with `app.dependency_overrides[get_settings]`. Nested models read env vars with a `__` delimiter (`APP_DB__HOST`) when you set `env_nested_delimiter="__"`.

## Error shape

Validation failures return HTTP 422 with `{"detail": [{"type", "loc", "msg", "input", ...}]}`. Don't hand-roll a competing error format for validation; reserve custom exception handlers for domain errors.
