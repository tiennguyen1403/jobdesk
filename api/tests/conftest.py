"""Shared pytest fixtures: an isolated DB transaction per test and a wired-up client.

Each test runs inside a single database transaction that is rolled back when the
test finishes, so nothing it writes ever persists — not between tests and not
into the dev database. The session joins that transaction with a SAVEPOINT, so
even a ``commit()`` in the code under test only releases the savepoint; the outer
``rollback()`` still undoes everything.

The schema is built once from the SQLAlchemy metadata via ``create_all`` (fast,
and idempotent against an already-migrated dev DB) rather than through Alembic.
A real PostgreSQL database is required because the models use Postgres-only
column types (JSONB, ARRAY, native ENUM) — point ``DATABASE_URL`` at a throwaway
database in CI. Tests stay hermetic: no network to Upwork/Anthropic.
"""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — imported so every model registers on Base.metadata
from app.config import settings
from app.db import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """A session-wide engine with the schema created once from the ORM metadata."""
    eng = create_engine(settings.database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    """A session whose work is rolled back when the test finishes."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """A TestClient whose ``get_db`` dependency yields the test's rolled-back session."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
