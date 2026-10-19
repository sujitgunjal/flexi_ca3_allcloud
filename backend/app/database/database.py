"""SQLite locally, Neon PostgreSQL when DATABASE_URL is set."""

import os
import threading
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    """Base class for application ORM models."""


def _default_database_url() -> str:
    database_path = Path(__file__).resolve().parents[2] / "data" / "app.db"
    return f"sqlite:///{database_path.as_posix()}"


def normalize_database_url(database_url: str) -> str:
    """Use the psycopg driver and require SSL for hosted PostgreSQL."""

    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        return database_url
    if "sslmode" not in url.query:
        url = url.update_query_pairs([*url.query.items(), ("sslmode", "require")])
    return url.render_as_string(hide_password=False)


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", _default_database_url()))
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _create_engine(database_url: str | URL) -> Engine:
    if isinstance(database_url, str):
        database_url = normalize_database_url(database_url)
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    if url.drivername == "sqlite":
        if url.database in (None, ":memory:"):
            return create_engine(url, connect_args={"check_same_thread": False})
        # Ensure the parent directory exists for file-backed SQLite databases.
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    if url.drivername.startswith("postgresql"):
        # NullPool suits Vercel: each invocation opens and closes its own connection.
        return create_engine(url, poolclass=NullPool, pool_pre_ping=True)
    return create_engine(url)


engine = _create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_schema_lock = threading.Lock()
# Stable session lock so two deploy processes cannot apply revisions together.
POSTGRES_ADVISORY_LOCK_KEY = 202610190001


def initialize_database(database_engine: Engine = engine) -> None:
    """Create SQLite tables for local development and tests.

    PostgreSQL schema changes are not applied here. Request handlers call this
    function, and Alembic's EnvironmentContext proxy is process-global:
    overlapping upgrades delete ``config`` or ``script`` and raise KeyError in
    ``_remove_proxy``. Apply Neon revisions with ``python -m app.database.migrate``.
    """
    if database_engine.dialect.name == "postgresql":
        return

    # Import registers model tables on Base.metadata without coupling app startup.
    from app.database import models  # noqa: F401

    Base.metadata.create_all(bind=database_engine)
    # ``create_all`` intentionally leaves existing tables alone. Add only the
    # optional observation columns introduced after the initial schema.
    columns = {column["name"] for column in inspect(database_engine).get_columns("request_logs")}
    with database_engine.begin() as connection:
        if "cache_key" not in columns:
            connection.execute(text("ALTER TABLE request_logs ADD COLUMN cache_key VARCHAR(256)"))
        if "cache_lookup_latency_ms" not in columns:
            connection.execute(text("ALTER TABLE request_logs ADD COLUMN cache_lookup_latency_ms FLOAT"))
        if "context_before_tokens" not in columns:
            connection.execute(text("ALTER TABLE request_logs ADD COLUMN context_before_tokens INTEGER"))
        if "context_after_tokens" not in columns:
            connection.execute(text("ALTER TABLE request_logs ADD COLUMN context_after_tokens INTEGER"))
        if "context_reduction_percent" not in columns:
            connection.execute(text("ALTER TABLE request_logs ADD COLUMN context_reduction_percent FLOAT"))
        if "completed" not in columns:
            connection.execute(text("ALTER TABLE request_logs ADD COLUMN completed BOOLEAN"))


def upgrade_schema() -> None:
    """Apply Alembic revisions once at a time in this process."""

    with _schema_lock:
        _apply_alembic_upgrade()


def run_migrations() -> None:
    """Apply revisions outside the API. PostgreSQL callers wait on one lock."""

    if engine.dialect.name == "postgresql":
        _migrate_postgres()
        return
    upgrade_schema()


def _migrate_postgres() -> None:
    with engine.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:key)"),
            {"key": POSTGRES_ADVISORY_LOCK_KEY},
        )
        connection.commit()
        try:
            upgrade_schema()
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": POSTGRES_ADVISORY_LOCK_KEY},
            )
            connection.commit()


def _apply_alembic_upgrade() -> None:
    """Apply Alembic migrations. Failures propagate to the caller."""

    from alembic import command
    from alembic.config import Config

    configuration = Config(str(BACKEND_ROOT / "alembic.ini"))
    configuration.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # Alembic treats % as ConfigParser interpolation.
    configuration.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(configuration, "head")


def test_connection(database_engine: Engine = engine) -> bool:
    """Return whether a simple SQL query can be executed."""
    with database_engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
