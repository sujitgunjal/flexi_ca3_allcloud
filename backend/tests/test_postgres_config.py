from sqlalchemy.pool import NullPool

from app.database.database import _create_engine, normalize_database_url


def test_sqlite_url_stays_local_and_file_backed(tmp_path):
    url = normalize_database_url(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")

    assert url.startswith("sqlite:///")
    assert "sslmode" not in url
    engine = _create_engine("sqlite:///:memory:")
    assert engine.dialect.name == "sqlite"
    engine.dispose()


def test_neon_postgres_url_uses_psycopg_and_ssl():
    url = normalize_database_url(
        "postgres://user:secret@ep-example.neon.tech/neondb"
    )

    assert url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url
    assert "secret" in url
    engine = _create_engine("postgresql+psycopg://user:secret@ep-example.neon.tech/neondb")
    assert engine.dialect.name == "postgresql"
    assert isinstance(engine.pool, NullPool)
    engine.dispose()


def test_existing_sslmode_is_preserved():
    url = normalize_database_url(
        "postgresql://user:secret@ep-example.neon.tech/neondb?sslmode=verify-full"
    )

    assert url.startswith("postgresql+psycopg://")
    assert "sslmode=verify-full" in url
    assert "sslmode=require" not in url
