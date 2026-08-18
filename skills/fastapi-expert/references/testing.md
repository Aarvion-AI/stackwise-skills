# Testing FastAPI: pytest + httpx AsyncClient

Async app → async tests. Skip `fastapi.testclient.TestClient` (sync wrapper) and drive the ASGI app directly with httpx.

Dependencies: `uv add --dev pytest pytest-asyncio httpx aiosqlite asgi-lifespan`

## pytest config

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"                     # every async test runs without @pytest.mark decoration
asyncio_default_fixture_loop_scope = "session"
testpaths = ["tests"]
```

With `asyncio_mode = "auto"` you never write `@pytest.mark.asyncio`. If the project uses strict mode instead, every async test and fixture needs the marker - match the existing config.

`anyio` note: FastAPI's docs sometimes show `@pytest.mark.anyio`. Pick ONE plugin (pytest-asyncio or anyio) for the whole suite; mixing them causes "no event loop" and duplicate-run weirdness.

## Client fixture

```python
# tests/conftest.py
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app

@pytest.fixture
async def client():
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
```

- `ASGITransport` calls the app in-process - no server, no ports, no network.
- `AsyncClient(app=app)` was removed in httpx 0.27+; the `transport=` form is the only correct one.
- `LifespanManager` (asgi-lifespan package) runs startup/shutdown; plain ASGITransport does NOT trigger lifespan, so `app.state` resources would be missing. If your app has no lifespan needs in tests, you can drop it.

## Test database fixture (SQLite in-memory)

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db

@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,        # one shared in-memory DB across connections
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
```

`StaticPool` + `check_same_thread=False` is mandatory for in-memory SQLite - without it each connection gets a fresh empty database. For Postgres-specific SQL (JSONB, arrays), test against real Postgres (testcontainers or a CI service) instead of SQLite.

## Dependency overrides

Override providers by the ORIGINAL function object used in `Depends(...)`:

```python
@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()      # ALWAYS clear - leaked overrides poison other tests
```

Auth override - skip the token dance for non-auth tests:

```python
from app.auth import get_current_user
from app.models import User

@pytest.fixture
def as_user(client, db_session):
    def _as(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        return client
    yield _as
    app.dependency_overrides.pop(get_current_user, None)
```

Gotchas:
- The dict key must be the exact function imported from the app module. Overriding a copy or a differently-imported symbol silently does nothing.
- Settings injected via `Depends(get_settings)` override the same way; if `get_settings` is `@lru_cache`d and you construct settings directly in tests, remember `get_settings.cache_clear()` where needed.
- Sub-dependencies of an overridden dependency are not called - override the outermost one you want to fake.

## Writing the tests

```python
async def test_create_item(client, db_session):
    resp = await client.post("/items", json={"name": "widget", "price": 5})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "widget"
    assert "id" in body

async def test_create_item_invalid(client):
    resp = await client.post("/items", json={"name": ""})
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "name") in locs

async def test_requires_auth(client):
    resp = await client.get("/users/me")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"

async def test_login_form_encoded(client, seeded_user):
    resp = await client.post(
        "/auth/token",
        data={"username": seeded_user.email, "password": "s3cret"},  # data=, not json=
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
```

Conventions:
- Assert status code first, then the body shape. For 422s assert the `loc` you expect, not the full message text (messages change across Pydantic versions).
- OAuth2 token endpoint takes `data=` (form), everything else `json=`.
- Test the failure paths (401/403/404/409/422) with the same care as the happy path - that's where handlers are usually wrong.

## Mocking outbound HTTP

For a shared `httpx.AsyncClient` on `app.state`, either override its accessor dependency with a client whose transport is `httpx.MockTransport(handler)`, or use the `respx` library to intercept by URL. Never let tests hit real external services.

## Running

```bash
uv run pytest -q                  # full suite
uv run pytest tests/test_items.py -q -x   # one file, stop at first failure
uv run pytest -q -k "login"       # filter by name
```

Run the suite after every change and fix failures until it's fully green before handing work back.
