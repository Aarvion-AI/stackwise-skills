# Dependency Injection, Lifespan, and Background Work

## Annotated dependencies - the only style to write

FastAPI 0.115+ code uses `Annotated` everywhere. The old default-value style (`db: AsyncSession = Depends(get_db)`) still works but can't be reused as a type alias and confuses defaults with injection. Write:

```python
from typing import Annotated
from fastapi import Depends, Header, Query

async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session

DbDep = Annotated[AsyncSession, Depends(get_db)]

@router.get("/items")
async def list_items(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
): ...
```

Define each `XDep` alias once next to its provider and import it; don't restate `Annotated[..., Depends(...)]` at every call site.

## Sync vs async dependencies

- `async def` dependency → awaited on the event loop. Never block inside it.
- `def` dependency → run in the threadpool. Fine for CPU-light sync work; each one costs a threadpool hop, so don't make hot, trivial dependencies sync without reason.
- Same rule applies to endpoints: `async def` only if the body awaits; otherwise plain `def`.

## Yield dependencies (setup/teardown)

Code after `yield` runs after the response is sent - cleanup, not response mutation:

```python
async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- Exceptions raised by the endpoint propagate into the dependency at the `yield` point - that's how the rollback branch triggers. Re-raise; swallowing the exception turns errors into confusing 500s.
- An `HTTPException` raised *after* `yield` is too late to change the response.

## Chained and parameterized dependencies

Dependencies compose - a dependency can depend on others, and FastAPI caches each dependency per request (same provider called once per request, shared by everyone who depends on it):

```python
async def get_current_user(db: DbDep, token: TokenDep) -> User: ...
CurrentUser = Annotated[User, Depends(get_current_user)]

async def get_current_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    return user
AdminUser = Annotated[User, Depends(get_current_admin)]
```

For parameterized dependencies, use a callable class:

```python
class RateLimit:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute

    async def __call__(self, request: Request) -> None:
        ...  # raise HTTPException(429) when exceeded

@router.post("/expensive", dependencies=[Depends(RateLimit(per_minute=5))])
async def expensive(): ...
```

`dependencies=[...]` (route or router level) runs guards whose return value you don't need. Router-level example:

```python
router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_admin)])
```

Set `Depends(provider, use_cache=False)` only when you genuinely need a fresh instance per injection point.

## Lifespan - startup/shutdown state

`@app.on_event("startup"/"shutdown")` is deprecated. Use the lifespan context manager, and share long-lived resources via `app.state`:

```python
from contextlib import asynccontextmanager
import httpx

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=10)
    app.state.engine = create_async_engine(get_settings().database_url)
    yield
    await app.state.http.aclose()
    await app.state.engine.dispose()

app = FastAPI(lifespan=lifespan)
```

Access state through a dependency so tests can override it:

```python
def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http

HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]
```

Build one shared `httpx.AsyncClient` at startup - creating a client per request throws away connection pooling.

Note: lifespan does NOT run under plain `httpx.AsyncClient(transport=ASGITransport(app=app))` in tests - see `references/testing.md` for the `LifespanManager`/fixture pattern.

## BackgroundTasks vs a real task queue

`BackgroundTasks` runs your callable in-process after the response is sent:

```python
from fastapi import BackgroundTasks

@router.post("/signup", status_code=201)
async def signup(data: SignupIn, db: DbDep, background: BackgroundTasks):
    user = await create_user(db, data)
    background.add_task(send_welcome_email, user.email)
    return user
```

Use `BackgroundTasks` only when ALL of these hold:
- Losing the task on crash/redeploy is acceptable (no durability, no retries).
- It finishes in seconds (it occupies the worker; long tasks starve throughput).
- It doesn't need the request's DB session (the session closes with the request - the task must open its own).

Otherwise use a real queue - arq or Celery with Redis, or SQS + a worker - for anything durable, retried, scheduled, or long-running (report generation, billing, media processing). The endpoint enqueues a job id and returns 202.

Don't fire-and-forget with bare `asyncio.create_task` inside endpoints: unreferenced tasks can be garbage-collected mid-flight and exceptions vanish. If you must, hold a reference and add a done-callback that logs failures.

## Middleware vs dependencies

- Cross-cutting, every-request, no route knowledge → middleware (CORS, gzip, request-id, timing).
- Anything needing route context, path params, or the DB → dependency.
- Prefer pure-ASGI middleware over `BaseHTTPMiddleware` subclasses; `BaseHTTPMiddleware` adds overhead and historically breaks streaming and background-task edge cases.
