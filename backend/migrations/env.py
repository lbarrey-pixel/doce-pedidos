"""Alembic: migrations em SQL puro (migrations/sql), versão guardada no schema doce."""

import os

from alembic import context
from sqlalchemy import create_engine, text

url = os.environ["MIGRATIONS_DATABASE_URL"]
engine = create_engine(url)

with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS doce"))
    context.configure(connection=conn, version_table_schema="doce")
    with context.begin_transaction():
        context.run_migrations()
