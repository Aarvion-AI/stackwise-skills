# Async SQLAlchemy 2.0 with FastAPI

SQLAlchemy 2.0 style only: `Mapped` / `mapped_column` declarative models, `select()` statements, async engine + sessions. No legacy `Query` API, no `declarative_base()`.

## Engine and session factory

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)

engine = create_async_engine(
    settings.database_url,          # postgresql+asyncpg://... or sqlite+aiosqlite://...
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,   # critical: objects stay usable after commit
)
```

- Driver must be async: `asyncpg` for Postgres, `aiosqlite` for SQLite. A sync driver URL (`postgresql://`) fails at first use.
- `expire_on_commit=False` is essential in FastAPI: after `commit()`, the default would expire all attributes, and the next attribute access triggers a lazy refresh - which under async raises `MissingGreenlet` once the response serializer touches the object.
- One engine per process, created at startup (see lifespan below), disposed at shutdown.

## Per-request session dependency

```python
from collections.abc import AsyncIterator
from typing import Annotated
from fastapi import Depends

async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session

DbDep = Annotated[AsyncSession, Depends(get_db)]
```

Commit explicitly in the endpoint/service. If you prefer commit-per-request, wrap the yield:

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

Never share one session across requests or store it on `app.state` - sessions are not concurrency-safe.

## Lifespan wiring

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # engine created at import or here; dispose on shutdown either way
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

Use Alembic for schema migrations. `Base.metadata.create_all` is acceptable only in tests:

```python
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

## Models - 2.0 declarative style

```python
from datetime import datetime
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    orders: Mapped[list["Order"]] = relationship(back_populates="user")

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    note: Mapped[str | None]          # Optional annotation -> nullable column

    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship()
```

`Mapped[str]` is NOT NULL; `Mapped[str | None]` is nullable. Type and nullability come from the annotation, not from `mapped_column` args.

## Queries

```python
from sqlalchemy import select

# One by primary key
user = await db.get(User, user_id)

# One by filter
result = await db.execute(select(User).where(User.email == email))
user = result.scalar_one_or_none()

# Many, ordered + paginated
result = await db.execute(
    select(Order)
    .where(Order.user_id == user_id)
    .order_by(Order.id.desc())
    .limit(limit)
    .offset(offset)
)
orders = result.scalars().all()
```

- `.scalars()` unwraps single-entity rows; forgetting it gives `Row` tuples that break Pydantic validation.
- `scalar_one_or_none()` for at-most-one; `scalar_one()` when absence is a bug.
- Insert/update/delete flow: `db.add(obj)` / mutate attributes / `await db.delete(obj)`, then `await db.commit()`. Use `await db.refresh(obj)` only when you need server-generated values not covered by `expire_on_commit=False` semantics (e.g. server defaults on insert).

## Relationship loading - the MissingGreenlet minefield

Implicit lazy loading requires IO, and async sessions forbid implicit IO. Accessing an unloaded relationship (often inside `response_model` serialization, after the handler returned) raises `MissingGreenlet` or `StatementError`. Always load eagerly in the query:

```python
from sqlalchemy.orm import joinedload, selectinload

# Collections: selectinload (second SELECT ... IN, no row explosion)
stmt = select(User).options(selectinload(User.orders).selectinload(Order.items))

# Many-to-one / one-to-one: joinedload (single JOIN)
stmt = select(Order).options(joinedload(Order.user))
```

Rules of thumb:
- `selectinload` for `list[...]` relationships, `joinedload` for scalar ones.
- Chain loaders for nested depth; each level you serialize must be loaded.
- Alternative: mark the relationship `lazy="raise"` in the model to fail fast in dev instead of at serialization time.
- If you only need a couple of columns, select them directly instead of loading whole entities.

## Concurrency

One `AsyncSession` handles one operation at a time. Never do this:

```python
# WRONG: same session used concurrently
a, b = await asyncio.gather(db.execute(stmt1), db.execute(stmt2))
```

Run them sequentially on one session, or give each coroutine its own session from the factory.

## Blocking-driver escape hatch

If a codebase is stuck on a sync driver, do not call it inside `async def`. Either declare the endpoint `def` (FastAPI threadpools it) or migrate to the async driver - don't wrap sync sessions in `run_in_executor` ad hoc per query.
