"""Migration 0002: catalogo e estoque."""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0002_catalogo_e_estoque.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
