"""Apoio aos testes de integração da loja e do painel: mundo com catálogo, operador e
relógio controlado; roteador falso (sem rede)."""

import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.adaptadores import repositorio_sql as repo
from app.adaptadores.roteador_fake import RoteadorFake
from app.api.auth import VerificadorJWT
from app.dominio.catalogo import ler_cardapio
from app.main import criar_app
from tests.integracao.test_api_base import CHAVE, EMISSOR, token

CARDAPIO = Path(__file__).resolve().parents[2] / "dados" / "cardapio.csv"
FUSO = ZoneInfo("America/Sao_Paulo")
TARDE = datetime(2026, 11, 2, 15, 0, tzinfo=FUSO)
ANA = {"nome": "Ana Paula Souza", "telefone": "(11) 99999-1234"}


class Relogio:
    agora = TARDE

    def __call__(self):
        return self.agora


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def mundo(engine, urls, relogio):
    with engine.begin() as c:
        repo.carregar_catalogo(c, ler_cardapio(CARDAPIO))
        oid = uuid.uuid4()
        c.execute(
            text("INSERT INTO doce.operador (id, nome, papel) VALUES (:id, 'Marina', 'dono')"),
            {"id": oid},
        )
        c.execute(
            text(
                "UPDATE doce.configuracao_loja SET pix_chave = '12345678000195',"
                " whatsapp_negocio = '5511988887777'"
            )
        )
    verificador = VerificadorJWT(chave_publica=CHAVE.public_key(), emissor=EMISSOR)
    app = criar_app(
        engine=engine,
        verificador=verificador,
        relogio=relogio,
        roteador=RoteadorFake(),
    )
    loja = TestClient(app)
    painel = TestClient(app, headers={"Authorization": f"Bearer {token(oid)}"})
    return loja, painel


def vid(engine, produto="Cheesecake de Frutas Vermelhas", tamanho="Fatia"):
    with engine.connect() as c:
        return repo.id_da_variante(c, produto, tamanho)


def produzir(painel, variante, n):
    r = painel.post(
        "/api/v1/painel/estoque/movimentos",
        json={
            "variante_id": variante,
            "tipo": "producao",
            "quantidade": n,
            "para_estado": "pronta",
        },
    )
    assert r.status_code == 200


def saldo(painel, variante):
    corpo = painel.get("/api/v1/painel/estoque").json()
    return next(v["saldo"] for v in corpo["variantes"] if v["id"] == variante)


def pedir(loja, variante, qtd=2, cep="12345-678", numero="220", **extra):
    corpo = {
        "cliente": ANA,
        "recebimento": "entrega",
        "endereco": {"cep": cep, "numero": numero, "complemento": ""},
        "itens": [{"variante_id": variante, "quantidade": qtd}],
        "tipo_entrega": "pronta_entrega",
    } | extra
    return loja.post("/api/v1/loja/pedidos", json=corpo)
