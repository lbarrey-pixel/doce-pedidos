"""Migration 0003: operador."""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0003_operador.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
