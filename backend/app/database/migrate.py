"""Apply Alembic revisions outside the API process.

Run from ``backend`` after ``DATABASE_URL`` is set:

    python -m app.database.migrate
"""

from app.database.database import run_migrations


def main() -> None:
    run_migrations()


if __name__ == "__main__":
    main()
