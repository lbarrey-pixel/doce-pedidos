"""API de estoque do painel: saldos, lançamentos do operador e descongelamento."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.adaptadores import repositorio_sql as repo
from app.api.auth import VerificadorJWT
from app.dominio.catalogo import ler_cardapio
from app.main import criar_app
from tests.integracao.test_api_base import CHAVE, EMISSOR, token

CARDAPIO = Path(__file__).resolve().parents[2] / "dados" / "cardapio.csv"
T0 = datetime(2026, 10, 30, 17, 0, tzinfo=UTC)  # 14h em São Paulo


class Relogio:
    def __init__(self) -> None:
        self.agora = T0

    def __call__(self) -> datetime:
        return self.agora


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def api(engine, relogio):
    with engine.begin() as c:
        repo.carregar_catalogo(c, ler_cardapio(CARDAPIO))
        oid = uuid.uuid4()
        c.execute(text("INSERT INTO doce.operador (id, nome) VALUES (:id, 'Marina')"), {"id": oid})
    verificador = VerificadorJWT(chave_publica=CHAVE.public_key(), emissor=EMISSOR)
    cliente = TestClient(criar_app(engine=engine, verificador=verificador, relogio=relogio))
    cliente.headers["Authorization"] = f"Bearer {token(oid)}"
    cliente.operador = str(oid)
    return cliente


def vid(engine, produto, tamanho):
    with engine.connect() as c:
        return repo.id_da_variante(c, produto, tamanho)


def item(estoque, variante_id):
    return next(v for v in estoque["variantes"] if v["id"] == variante_id)


def mover(api, variante_id, tipo, quantidade, **extra):
    return api.post(
        "/api/v1/painel/estoque/movimentos",
        json={"variante_id": variante_id, "tipo": tipo, "quantidade": quantidade} | extra,
    )


def test_exige_operador(engine):
    verificador = VerificadorJWT(chave_publica=CHAVE.public_key(), emissor=EMISSOR)
    cliente = TestClient(criar_app(engine=engine, verificador=verificador))
    assert cliente.get("/api/v1/painel/estoque").status_code == 401


def test_estoque_lista_o_cardapio_com_controle_e_preco(api, engine):
    corpo = api.get("/api/v1/painel/estoque").json()
    assert len(corpo["variantes"]) == 15
    coca = item(corpo, vid(engine, "Refrigerante de Guaraná", "Lata 350 ml"))
    assert coca["controle_estoque"] == "reserva" and coca["preco_centavos"] == 890
    assert coca["categoria"] == "Bebidas" and coca["saldo"]["reserva"] == 0
    assert set(coca["saldo"]) == {"pronta", "separada", "congelada", "descongelando", "reserva"}


def test_producao_com_autor_e_hora(api, engine):
    v = vid(engine, "Torta de Limão", "Fatia")
    assert mover(api, v, "producao", 3, para_estado="pronta").status_code == 200
    r = mover(api, v, "producao", 2, para_estado="congelada")
    assert r.status_code == 200 and r.json()["saldo"]["congelada"] == 2
    saldo = item(api.get("/api/v1/painel/estoque").json(), v)["saldo"]
    assert (saldo["pronta"], saldo["congelada"]) == (3, 2)
    with engine.connect() as c:
        autores = c.execute(text("SELECT DISTINCT autor, criado_em FROM doce.movimento")).all()
    assert autores == [(api.operador, T0)]


def test_descongelamento_vira_pronta_sozinho(api, engine, relogio):
    v = vid(engine, "Cheesecake de Frutas Vermelhas", "Fatia")
    mover(api, v, "producao", 2, para_estado="congelada")
    assert mover(api, v, "inicio_descongelamento", 1).status_code == 200
    relogio.agora = T0 + timedelta(hours=1)
    v1 = item(api.get("/api/v1/painel/estoque").json(), v)
    assert (v1["saldo"]["descongelando"], v1["saldo"]["pronta"]) == (1, 0)
    assert v1["descongelando"] == [
        {"quantidade": 1, "pronta_as": (T0 + timedelta(hours=2)).isoformat()}
    ]
    relogio.agora = T0 + timedelta(hours=2)
    v2 = item(api.get("/api/v1/painel/estoque").json(), v)
    assert (v2["saldo"]["congelada"], v2["saldo"]["descongelando"], v2["saldo"]["pronta"]) == (
        1,
        0,
        1,
    )
    assert v2["descongelando"] == []


def test_descongelamento_vencido_conta_antes_de_uma_perda(api, engine, relogio):
    v = vid(engine, "Cheesecake de Frutas Vermelhas", "Fatia")
    mover(api, v, "producao", 1, para_estado="congelada")
    mover(api, v, "inicio_descongelamento", 1)
    relogio.agora = T0 + timedelta(hours=3)
    r = mover(api, v, "perda", 1, de_estado="pronta", motivo="caiu")
    assert r.status_code == 200


def test_movimento_acima_da_pronta_entrega_e_recusado(api, engine):
    v = vid(engine, "Bolo de Pote Red Velvet", "Individual")
    mover(api, v, "producao", 1, para_estado="pronta")
    r = mover(api, v, "perda", 2, de_estado="pronta", motivo="caiu")
    assert r.status_code == 422
    assert r.json()["erro"] == "falta_estoque"
    assert r.json()["variante_id"] == v and r.json()["disponivel"] == 1
    assert item(api.get("/api/v1/painel/estoque").json(), v)["saldo"]["pronta"] == 1


def test_bebida_entrada_e_transferencia(api, engine):
    coca = vid(engine, "Refrigerante de Guaraná", "Lata 350 ml")
    assert mover(api, coca, "entrada", 12, para_estado="reserva").status_code == 200
    r = mover(api, coca, "transferencia", 6)
    assert r.status_code == 200
    assert (r.json()["saldo"]["reserva"], r.json()["saldo"]["pronta"]) == (6, 6)


@pytest.mark.parametrize(
    ("produto", "tamanho", "corpo"),
    [
        (
            "Refrigerante de Guaraná",
            "Lata 350 ml",
            {"tipo": "producao", "para_estado": "congelada"},
        ),
        ("Brownie de Nozes", "Unidade", {"tipo": "entrada", "para_estado": "pronta"}),
        ("Brownie de Nozes", "Unidade", {"tipo": "fim_descongelamento"}),
        ("Brownie de Nozes", "Unidade", {"tipo": "venda", "de_estado": "pronta"}),
        ("Brownie de Nozes", "Unidade", {"tipo": "perda", "de_estado": "pronta"}),
        ("Brownie de Nozes", "Unidade", {"tipo": "producao"}),
    ],
)
def test_movimento_invalido(api, engine, produto, tamanho, corpo):
    r = mover(api, vid(engine, produto, tamanho), quantidade=1, **corpo)
    assert r.status_code == 422 and r.json()["erro"] == "movimento_invalido"


def test_ajuste_e_perda_com_motivo(api, engine):
    v = vid(engine, "Brownie de Nozes", "Unidade")
    mover(api, v, "producao", 5, para_estado="pronta")
    assert mover(api, v, "ajuste", 1, de_estado="pronta", motivo="contagem").status_code == 200
    assert mover(api, v, "perda", 1, de_estado="pronta", motivo="caiu").status_code == 200
    r = mover(api, v, "ajuste", 9, de_estado="pronta", motivo="contagem")
    assert r.status_code == 422 and r.json()["erro"] == "falta_estoque"
    assert item(api.get("/api/v1/painel/estoque").json(), v)["saldo"]["pronta"] == 3


def test_movimento_so_com_variante_do_cardapio(api):
    r = mover(api, str(uuid.uuid4()), "producao", 1, para_estado="pronta")
    assert r.status_code == 422 and r.json()["erro"] == "variante_desconhecida"
