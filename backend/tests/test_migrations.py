import threading

from sqlalchemy import create_engine, inspect

from app.database import database
from app.database.database import initialize_database, run_migrations, upgrade_schema


def test_postgresql_initialization_does_not_run_migrations(monkeypatch):
    calls = []
    monkeypatch.setattr(database, "upgrade_schema", lambda: calls.append("upgrade"))
    engine = create_engine("postgresql+psycopg://user:secret@127.0.0.1:5432/neondb")

    try:
        initialize_database(engine)
    finally:
        engine.dispose()

    assert engine.dialect.name == "postgresql"
    assert calls == []


def test_metrics_request_path_does_not_upgrade_postgresql(monkeypatch):
    from app.services import metrics_service

    upgrades = []
    postgres = create_engine("postgresql+psycopg://user:secret@127.0.0.1:5432/neondb")
    monkeypatch.setattr(database, "upgrade_schema", lambda: upgrades.append("upgrade"))

    def initialize_without_request_migration(database_engine=None):
        initialize_database(postgres if database_engine is None else database_engine)

    class Session:
        def add(self, _record):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def refresh(self, record):
            record.id = 1

        def close(self):
            return None

    monkeypatch.setattr(metrics_service, "initialize_database", initialize_without_request_migration)
    monkeypatch.setattr(metrics_service, "SessionLocal", lambda: Session())

    try:
        record = metrics_service.log_request({"query": "How does Redis expire a key?"})
    finally:
        postgres.dispose()

    assert record.id == 1
    assert upgrades == []


def test_postgres_migration_uses_advisory_lock_around_upgrade(monkeypatch):
    statements = []

    class Connection:
        def execute(self, statement, params=None):
            statements.append((str(statement), params))

        def commit(self):
            statements.append(("commit", None))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Engine:
        class dialect:
            name = "postgresql"

        def connect(self):
            return Connection()

    monkeypatch.setattr(database, "engine", Engine())
    monkeypatch.setattr(database, "upgrade_schema", lambda: statements.append(("upgrade", None)))

    run_migrations()

    rendered = [item[0] for item in statements]
    assert rendered.index("SELECT pg_advisory_lock(:key)") < rendered.index("upgrade")
    assert rendered.index("upgrade") < rendered.index("SELECT pg_advisory_unlock(:key)")
    assert statements[0][1] == {"key": database.POSTGRES_ADVISORY_LOCK_KEY}


def test_concurrent_upgrades_do_not_raise_proxy_keyerror(monkeypatch, tmp_path):
    database_path = tmp_path / "migrate.db"
    monkeypatch.setattr(
        database,
        "DATABASE_URL",
        f"sqlite:///{database_path.as_posix()}",
    )
    errors = []

    def run():
        try:
            upgrade_schema()
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {"request_logs", "request_trace_events", "alembic_version"} <= names
