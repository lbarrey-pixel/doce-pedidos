"""API base: saúde, formato de erro e acesso do operador ao painel."""

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.auth import VerificadorJWT
from app.main import criar_app

CHAVE = ec.generate_private_key(ec.SECP256R1())
OUTRA = ec.generate_private_key(ec.SECP256R1())
EMISSOR = "https://auth.example.com/auth/v1"


def token(sub, chave=CHAVE, exp=None, aud="authenticated"):
    agora = int(time.time())
    return jwt.encode(
        {"sub": str(sub), "aud": aud, "iss": EMISSOR, "exp": exp or agora + 600, "iat": agora},
        chave,
        algorithm="ES256",
    )


@pytest.fixture
def cliente(engine):
    verificador = VerificadorJWT(chave_publica=CHAVE.public_key(), emissor=EMISSOR)
    return TestClient(criar_app(engine=engine, verificador=verificador))


@pytest.fixture
def operador(engine):
    oid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO doce.operador (id, nome, ativo) VALUES (:id, 'Marina', true)"),
            {"id": oid},
        )
    return oid


def test_saude(cliente):
    r = cliente.get("/api/v1/saude")
    assert r.status_code == 200 and r.json() == {"ok": True, "banco": True}


def test_rota_inexistente_no_formato_de_erro(cliente):
    r = cliente.get("/api/v1/nao-existe")
    assert r.status_code == 404
    assert set(r.json()) == {"erro", "mensagem"} and r.json()["erro"] == "nao_encontrado"


def test_painel_sem_token(cliente):
    r = cliente.get("/api/v1/painel/eu")
    assert r.status_code == 401 and r.json()["erro"] == "nao_autenticado"


def test_painel_com_operador_ativo(cliente, operador):
    r = cliente.get("/api/v1/painel/eu", headers={"Authorization": f"Bearer {token(operador)}"})
    assert r.status_code == 200 and r.json() == {
        "id": str(operador),
        "nome": "Marina",
        "trocar_senha": False,
        "papel": "operador",
    }


@pytest.mark.parametrize("caso", ["assinatura_errada", "expirado", "audiencia_errada", "lixo"])
def test_token_invalido(cliente, operador, caso):
    t = {
        "assinatura_errada": lambda: token(operador, chave=OUTRA),
        "expirado": lambda: token(operador, exp=int(time.time()) - 10),
        "audiencia_errada": lambda: token(operador, aud="anon"),
        "lixo": lambda: "abc.def.ghi",
    }[caso]()
    r = cliente.get("/api/v1/painel/eu", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 401


def test_usuario_que_nao_e_operador_ou_inativo(cliente, engine, operador):
    r = cliente.get("/api/v1/painel/eu", headers={"Authorization": f"Bearer {token(uuid.uuid4())}"})
    assert r.status_code == 403 and r.json()["erro"] == "sem_acesso"
    with engine.begin() as c:
        c.execute(text("UPDATE doce.operador SET ativo = false"))
    r = cliente.get("/api/v1/painel/eu", headers={"Authorization": f"Bearer {token(operador)}"})
    assert r.status_code == 403


def test_log_do_httpx_desligado_para_nao_gravar_url():
    """A URL de serviços externos pode levar dado do cliente; nunca vai para o log."""
    import logging

    from app import main  # noqa: F401

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
