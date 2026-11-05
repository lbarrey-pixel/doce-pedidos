"""Migration 0007: pagamento online (colunas do pedido, link, confirmação, tarifas)."""

from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0007_pagamento_online.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))
