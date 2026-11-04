"""Migration 0001: schema e papeis."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SQL = Path(__file__).resolve().parents[1] / "sql" / "0001_schema_e_papeis.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
