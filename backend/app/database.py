import contextlib
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    echo=settings.is_dev,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Plain session for platform-schema queries (users, orgs, cloud accounts)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _org_schema(org_slug: str) -> str:
    return "org_" + org_slug.replace("-", "_")


async def get_tenant_db(org_slug: str) -> AsyncGenerator[AsyncSession, None]:
    """Session with schema_translate_map routing org_tenant → org_{slug}.

    Uses engine.execution_options() to create a sub-engine that applies
    schema_translate_map at the engine level, ensuring ALL ORM queries on the
    session inherit the translation — not just Core-level connection.execute() calls.
    """
    real_schema = _org_schema(org_slug)
    # engine.execution_options() returns a proxied engine; every connection and
    # every query compiled through it will have schema_translate_map applied.
    tenant_engine = engine.execution_options(
        schema_translate_map={"org_tenant": real_schema}
    )
    async with AsyncSession(tenant_engine, expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Sync counterparts, for use in Celery tasks (which run outside the async
# event loop, not through FastAPI's dependency injection) ──────────────────────

_sync_engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", ""))


@contextlib.contextmanager
def sync_tenant_session(org_slug: str) -> Generator[Session, None, None]:
    """Sync counterpart to get_tenant_db(). Uses schema_translate_map, NOT `SET
    search_path` — our ORM models declare `schema="org_tenant"` literally (see
    models/org.py), so every query SQLAlchemy compiles is already schema-qualified
    as `org_tenant.foo`; `SET search_path` only affects *unqualified* references
    and silently does nothing here. schema_translate_map is the only thing that
    actually remaps `org_tenant` → the real `org_{slug}` schema at compile time.
    """
    real_schema = _org_schema(org_slug)
    tenant_engine = _sync_engine.execution_options(
        schema_translate_map={"org_tenant": real_schema}
    )
    session = Session(tenant_engine, expire_on_commit=False)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextlib.contextmanager
def sync_platform_session() -> Generator[Session, None, None]:
    """Sync session for platform-schema queries (users, orgs, cloud accounts) —
    no translation needed since `platform` is already the schema's real name."""
    session = Session(_sync_engine, expire_on_commit=False)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
