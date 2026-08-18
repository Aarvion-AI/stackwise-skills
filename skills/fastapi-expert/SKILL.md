---
name: fastapi-expert
description: Use when building or debugging FastAPI services - files importing fastapi, pydantic, or sqlalchemy.ext.asyncio; projects with pyproject.toml using uv/ruff/mypy; mentions of FastAPI, Pydantic v2, APIRouter, Depends, async endpoints, OAuth2/JWT auth, or pytest with httpx. Builds REST APIs, migrates Pydantic v1 to v2 idioms, wires async SQLAlchemy 2.0, adds auth and settings, writes async tests. Invoke for new endpoints, request/response schema design, dependency injection, lifespan/background tasks, auth flows, and test suites.
license: MIT
metadata:
  version: "0.1.0"
  category: backend
  frameworks: "FastAPI 0.115+, Pydantic 2.x, SQLAlchemy 2.0 (async), Python 3.12+"
  triggers: fastapi, pydantic, BaseModel, APIRouter, Depends, async endpoint, uvicorn, sqlalchemy async, oauth2, jwt, pydantic-settings, httpx AsyncClient
  related: react-expert, vue-expert, terraform-expert, playwright-expert
---

# FastAPI Expert

Turns Claude into a senior Python backend engineer who ships FastAPI 0.115+ services with Pydantic v2 idioms, async SQLAlchemy 2.0, and a uv/ruff/mypy toolchain.

## When to Use This Skill

- Scaffold a new FastAPI service or add routers/endpoints to an existing one
- Design request/response schemas with Pydantic v2 (validators, ConfigDict, serialization)
- Wire async SQLAlchemy 2.0 sessions, models, and eager-loading into endpoints
- Add authentication (OAuth2 password flow + JWT) and per-route authorization
- Migrate Pydantic v1 patterns (`.dict()`, `@validator`, `class Config`) to v2
- Write async test suites with httpx `AsyncClient` and dependency overrides
- Configure settings, lifespan startup/shutdown, and background work

## Core Workflow

1. **Analyze** - read `pyproject.toml` (dependency versions, tool config for ruff/mypy/pytest), the app factory / `main.py`, existing routers, and the session/settings modules. Match the project's layout (routers vs. flat, repository layer vs. inline queries) before writing anything. Confirm Pydantic is v2 and SQLAlchemy is 2.0 async - never mix v1 idioms in.
2. **Implement** - write endpoints with `Annotated` dependencies, Pydantic v2 schemas (separate `Create`/`Update`/`Read` models), and `async def` only where the body actually awaits. Register new routers on the app. Prefer editing existing modules over new files.
3. **Verify lint/format** - run `uv run ruff check . && uv run ruff format --check .`; fix all reported issues and re-run until clean.
4. **Verify types** - run `uv run mypy .`; fix all reported issues and re-run until clean. Do not silence errors with blanket `# type: ignore` - fix the types.
5. **Test** - write or update pytest tests using httpx `AsyncClient` with `ASGITransport` and `app.dependency_overrides` for DB/auth (see `references/testing.md`). Run `uv run pytest -q`; fix every failure and re-run until all tests pass.
6. **Prove it works** - start the app (`uv run uvicorn app.main:app --reload` or `uv run fastapi dev`), hit the changed endpoints with `curl` (including one invalid payload to confirm the 422 shape), and check `/docs` renders the new routes. Fix anything broken and re-verify until the live behavior matches the spec.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Pydantic v2 schemas, validators, serialization | `references/pydantic-v2.md` | Writing/changing any BaseModel; migrating v1 code; custom validation or serialization; settings via pydantic-settings |
| Async SQLAlchemy 2.0 engine, sessions, queries | `references/async-sqlalchemy.md` | Any DB model, session wiring, query, relationship loading, or `MissingGreenlet`/lazy-load errors |
| Dependency injection, lifespan, background tasks | `references/dependencies-di.md` | Writing Depends chains, yield dependencies, app startup/shutdown state, BackgroundTasks vs. task queue decisions |
| OAuth2 password flow + JWT auth | `references/auth.md` | Login/token endpoints, protected routes, password hashing, current-user dependencies, scopes/roles |
| pytest + httpx AsyncClient testing | `references/testing.md` | Writing or fixing tests, dependency overrides, test DB fixtures, async test config |

## Key Patterns

**Pydantic v2 schema trio with ORM reads** (never `.from_orm()` / `class Config`):

```python
from pydantic import BaseModel, ConfigDict, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr

user = UserRead.model_validate(db_user)          # not User.from_orm(db_user)
payload = user.model_dump(mode="json")           # not user.dict()
```

**Annotated dependencies, aliased once, reused everywhere:**

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

@router.post("/items", status_code=201, response_model=ItemRead)
async def create_item(data: ItemCreate, db: DbDep, user: CurrentUser) -> Item:
    ...
```

**Lifespan context instead of deprecated `@app.on_event`:**

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = create_async_engine(settings.database_url)
    yield
    await app.state.engine.dispose()

app = FastAPI(lifespan=lifespan)
```

**Async query with eager loading (no lazy loads after await):**

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

result = await db.execute(
    select(Order).options(selectinload(Order.items)).where(Order.user_id == user.id)
)
orders = result.scalars().all()
```

## Common Mistakes

- **Pydantic v1 idioms in v2 code** - `.dict()`, `.json()`, `parse_obj()`, `from_orm()`, `@validator`, `class Config`, `update_forward_refs()`. Use `model_dump()`, `model_dump_json()`, `model_validate()`, `@field_validator` / `@model_validator`, `ConfigDict`, `model_rebuild()`. Mixing generations breaks silently or at import time.
- **Blocking calls inside `async def` endpoints** - sync DB drivers, `requests`, `time.sleep` block the event loop for every request. Either make the call truly async or declare the endpoint `def` so FastAPI runs it in the threadpool.
- **Lazy-loading relationships after the session context** - async SQLAlchemy raises `MissingGreenlet` on implicit IO. Eager-load with `selectinload`/`joinedload` in the query, and create the session factory with `expire_on_commit=False` so committed objects stay readable.
- **One global session or `Depends(get_db)` at import time** - sessions must be per-request via a yield dependency; a shared session breaks under concurrency and leaks transactions.
- **`BackgroundTasks` for heavy or must-not-lose work** - it runs in-process after the response; a crash or deploy loses it. Use it for fire-and-forget (emails, cache warm); use a task queue (arq/Celery/SQS worker) for retries, long jobs, or anything durable.
- **Auth details wrong** - storing plain or fast-hashed passwords (use bcrypt/argon2 via passlib or pwdlib), putting sensitive data in JWT claims, no `exp` check, or returning 403 instead of 401 with `WWW-Authenticate: Bearer` on missing credentials.
- **Tests using `TestClient` for an async app with overrides left dirty** - use httpx `AsyncClient(transport=ASGITransport(app=app))`, set `app.dependency_overrides` in fixtures, and always clear them in teardown so tests stay isolated.
