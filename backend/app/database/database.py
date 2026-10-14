"""SQLite and SQLAlchemy setup for request logging."""

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Base class for application ORM models."""


def _default_database_url() -> str:
    database_path = Path(__file__).resolve().parents[2] / "data" / "app.db"
    return f"sqlite:///{database_path.as_posix()}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())


def _create_engine(database_url: str | URL) -> Engine:
    url = make_url(database_url)
    if url.drivername == "sqlite":
        if url.database in (None, ":memory:"):
            return create_engine(url, connect_args={"check_same_thread": False})
        # Ensure the parent directory exists for file-backed SQLite databases.
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = _create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def initialize_database(database_engine: Engine = engine) -> None:
    """Create tables for all imported application models."""
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


def test_connection(database_engine: Engine = engine) -> bool:
    """Return whether a simple SQL query can be executed."""
    with database_engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
