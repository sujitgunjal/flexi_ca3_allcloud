from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database.database import (
    Base,
    _create_engine,
    initialize_database,
    test_connection as check_connection,
)
from app.database.models import RequestLog


def test_request_log_database_round_trip():
    test_engine = _create_engine("sqlite:///:memory:")
    try:
        assert check_connection(test_engine)
        initialize_database(test_engine)
        assert "request_logs" in inspect(test_engine).get_table_names()

        with Session(test_engine) as session:
            record = RequestLog(query="What is Docker?", complexity="simple")
            session.add(record)
            session.commit()
            record_id = record.id

        with Session(test_engine) as session:
            retrieved = session.get(RequestLog, record_id)
            assert retrieved is not None
            assert retrieved.query == "What is Docker?"
            assert retrieved.complexity == "simple"
            assert retrieved.selected_model is None
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_database_initialization_adds_optional_cache_columns_to_existing_table():
    test_engine = _create_engine("sqlite:///:memory:")
    try:
        with test_engine.begin() as connection:
            connection.execute(text("CREATE TABLE request_logs (id INTEGER PRIMARY KEY, query TEXT NOT NULL)"))
        initialize_database(test_engine)
        columns = {column["name"] for column in inspect(test_engine).get_columns("request_logs")}
        assert {"cache_key", "cache_lookup_latency_ms"} <= columns
        assert "completed" in columns
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_database_adds_completed_to_legacy_rows_without_data_loss():
    test_engine = _create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(bind=test_engine)
        with test_engine.begin() as connection:
            connection.execute(text("ALTER TABLE request_logs DROP COLUMN completed"))
            connection.execute(
                text("INSERT INTO request_logs (timestamp, query, selected_model) VALUES ('2026-01-01 00:00:00', 'legacy', 'cheap')")
            )

        initialize_database(test_engine)
        with Session(test_engine) as session:
            record = session.query(RequestLog).filter_by(query="legacy").one()
            assert record.selected_model == "cheap"
            assert record.completed is None

            record.completed = True
            session.commit()
            session.refresh(record)
            assert record.completed is True
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
