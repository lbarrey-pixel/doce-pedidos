"""Migration 0004: pedidos e movimentos."""

from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0004_pedidos_e_movimentos.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
