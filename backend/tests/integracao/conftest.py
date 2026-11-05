"""Postgres local com as migrations aplicadas.

Precisa de TEST_ADMIN_DATABASE_URL apontando para um Postgres onde se pode criar banco
(ex.: postgresql+psycopg://postgres@localhost:5432/postgres). Sem ela, os testes
de integração são pulados. A API roda como doce_api, igual em produção.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN = os.environ.get("TEST_ADMIN_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items):
    for item in items:
        if "integracao" in str(item.fspath):
            item.add_marker(pytest.mark.integracao)


@pytest.fixture(scope="session")
def urls():
    if not ADMIN:
        pytest.skip("TEST_ADMIN_DATABASE_URL não definida")
    nome = f"doce_t_{uuid.uuid4().hex[:8]}"
    admin = create_engine(ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nome}"'))
    dono = make_url(ADMIN).set(database=nome)
    env = os.environ | {"MIGRATIONS_DATABASE_URL": dono.render_as_string(hide_password=False)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True
    )
    senha = os.environ.get("TEST_DOCE_API_SENHA")
    if senha:  # só no CI; localmente o Postgres de teste usa trust
        with create_engine(dono, isolation_level="AUTOCOMMIT").connect() as c:
            literal = c.execute(text("SELECT quote_literal(:s)"), {"s": senha}).scalar_one()
            c.execute(text(f"ALTER ROLE doce_api PASSWORD {literal}"))
    api = dono.set(username="doce_api", password=senha)
    yield {"dono": dono, "api": api}
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))


@pytest.fixture
def engine(urls):
    """Engine como doce_api; tabelas limpas antes de cada teste."""
    dono = create_engine(urls["dono"])
    with dono.begin() as c:
        c.execute(
            text(
                "TRUNCATE doce.movimento, doce.item_pedido, doce.pedido, doce.saldo, doce.variante,"
                " doce.produto, doce.categoria, doce.entregador, doce.operador CASCADE"
            )
        )
        # Configuração da loja volta ao padrão da migration: um teste não vaza para o outro.
        c.execute(text("DELETE FROM doce.configuracao_loja"))
        c.execute(text("INSERT INTO doce.configuracao_loja (id) VALUES (1)"))
    dono.dispose()
    # Sessão em UTC, como no CI e no Supabase: o fuso do Postgres local não esconde erro de
    # data sem conversão para Campinas .
    eng = create_engine(urls["api"], pool_size=5, connect_args={"options": "-c timezone=UTC"})
    yield eng
    eng.dispose()


from tests.integracao.apoio import mundo, relogio  # noqa: E402, F401  (fixtures compartilhadas)
from tests.integracao.apoio_pagamento import gateway, mundo_gateway  # noqa: E402, F401
