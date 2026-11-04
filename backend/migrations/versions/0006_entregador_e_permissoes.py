"""Migration 0006: entregador e permissoes."""

from pathlib import Path

from alembic import op

revision = "0006"
down_revision = "0005"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0006_entregador_e_permissoes.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
