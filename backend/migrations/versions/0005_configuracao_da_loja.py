"""Migration 0005: configuracao da loja."""

from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0005_configuracao_da_loja.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
