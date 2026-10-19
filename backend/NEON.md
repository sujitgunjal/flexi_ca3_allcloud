# Neon PostgreSQL on Vercel

Local development keeps using SQLite at `backend/data/app.db` when `DATABASE_URL` is unset. Production uses Neon through `DATABASE_URL`.

## Neon

1. Create a Neon project and database.
2. Copy the pooled connection string. The host contains `-pooler`, which is the serverless endpoint.
3. The string may start with `postgres://` or `postgresql://`. The app rewrites it to `postgresql+psycopg://` and adds `sslmode=require` when that parameter is missing.

## Vercel

Set this environment variable on the backend project. Do not commit the value.

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST-pooler.REGION.aws.neon.tech/DBNAME?sslmode=require
```

The API applies Alembic migrations during startup. A failed connection or migration stops startup instead of being ignored. You can also apply them once from `backend` before the first deploy:

```powershell
$env:DATABASE_URL = "<neon pooled connection string>"
..\.venv\Scripts\python.exe -m alembic upgrade head
```

## Tables

`alembic/versions/20261019_0001_request_logs.py` creates `request_logs` and `request_trace_events`, including cache, context, quality, and `completed` columns.

SQLite upgrades for existing local files still run through `initialize_database()`.
