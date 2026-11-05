"""A migration do pagamento online aplica sobre o schema anterior sem perder pedidos e deixa
o banco no formato esperado (a aplicação do zero é exercitada por toda a suíte de integração)."""

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.integracao.conftest import ADMIN, BACKEND


@pytest.fixture
def banco_na_0006():
    if not ADMIN:
        pytest.skip("TEST_ADMIN_DATABASE_URL não definida")
    nome = f"doce_m_{uuid.uuid4().hex[:8]}"
    admin = create_engine(ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nome}"'))
    dono = make_url(ADMIN).set(database=nome)
    env = os.environ | {"MIGRATIONS_DATABASE_URL": dono.render_as_string(hide_password=False)}

    def alembic(alvo: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", alvo], cwd=BACKEND, env=env, check=True
        )

    alembic("0006")
    yield create_engine(dono), alembic
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))


def test_migration_0007_preserva_pedidos_e_acrescenta_o_novo_formato(banco_na_0006):
    engine, alembic = banco_na_0006
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO doce.pedido (canal, subtotal_centavos, total_centavos,"
                " forma_pagamento, estado) VALUES ('app', 5380, 5380, 'pix_manual', 'pago')"
            )
        )
    alembic("head")
    with engine.begin() as c:
        antigo = c.execute(
            text("SELECT forma_pagamento, parcelas, pago_apos_expirar FROM doce.pedido")
        ).one()
        assert tuple(antigo) == ("pix_manual", None, False)
        tarifas = c.execute(
            text("SELECT tarifa_cartao_bps, tarifa_pix_bps FROM doce.configuracao_loja")
        ).one()
        assert tuple(tarifas) == (420, 0)
        c.execute(
            text(
                "INSERT INTO doce.pedido (canal, subtotal_centavos, total_centavos,"
                " forma_pagamento, estado) VALUES ('app', 100, 100, 'cartao', 'pago')"
            )
        )
    with pytest.raises(DBAPIError), engine.begin() as c:  # forma desconhecida continua barrada
        c.execute(
            text(
                "INSERT INTO doce.pedido (canal, subtotal_centavos, total_centavos,"
                " forma_pagamento, estado) VALUES ('app', 100, 100, 'dinheiro', 'pago')"
            )
        )


def test_indice_do_nsu_barra_o_mesmo_pagamento_duas_vezes(banco_na_0006):
    engine, alembic = banco_na_0006
    alembic("head")
    inserir = (
        "INSERT INTO doce.confirmacao_pagamento (origem, resultado, transaction_nsu)"
        " VALUES ('aviso', :r, 'nsu-1')"
    )
    with engine.begin() as c:
        c.execute(text(inserir), {"r": "confirmado"})
        c.execute(text(inserir), {"r": "repetido"})  # repetido não gasta o nsu
        c.execute(text(inserir), {"r": "repetido"})
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text(inserir), {"r": "confirmado"})
