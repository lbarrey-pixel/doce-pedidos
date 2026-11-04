"""Verificação do JWT: chave pública (produção/testes) e segredo HS256 (desenvolvimento)."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.api.auth import VerificadorJWT
from app.api.erros import ErroDeNegocio
from app.main import _verificador_do_ambiente

SEGREDO = "segredo-de-desenvolvimento-com-32-bytes!"
CHAVE = ec.generate_private_key(ec.SECP256R1())
EMISSOR = "https://auth.example.com/auth/v1"


def _claims(**extra):
    agora = int(time.time())
    return {"sub": "u1", "aud": "authenticated", "exp": agora + 600, "iat": agora} | extra


def test_segredo_hs256_aceita_token_valido():
    token = jwt.encode(_claims(), SEGREDO, algorithm="HS256")
    assert VerificadorJWT(segredo=SEGREDO).sub(token) == "u1"


@pytest.mark.parametrize(
    "token",
    [
        jwt.encode(_claims(), "outro-segredo-com-32-bytes-ou-mais!!", algorithm="HS256"),
        jwt.encode(_claims(aud="anon"), SEGREDO, algorithm="HS256"),
        jwt.encode(_claims(exp=int(time.time()) - 5), SEGREDO, algorithm="HS256"),
        jwt.encode(_claims(), CHAVE, algorithm="ES256"),
        "lixo",
    ],
)
def test_segredo_hs256_recusa_token_invalido(token):
    with pytest.raises(ErroDeNegocio) as e:
        VerificadorJWT(segredo=SEGREDO).sub(token)
    assert e.value.status == 401


def test_chave_publica_nao_aceita_hs256_assinado_com_a_propria_chave():
    # ataque clássico de confusão de algoritmo: HS256 usando a chave pública como segredo
    verificador = VerificadorJWT(chave_publica=CHAVE.public_key(), emissor=EMISSOR)
    forjado = jwt.encode(_claims(iss=EMISSOR), SEGREDO, algorithm="HS256")
    with pytest.raises(ErroDeNegocio):
        verificador.sub(forjado)


def test_segredo_nao_combina_com_chave_publica():
    with pytest.raises(ValueError):
        VerificadorJWT(segredo=SEGREDO, chave_publica=CHAVE.public_key())


def test_ambiente_escolhe_o_modo(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        _verificador_do_ambiente()
    monkeypatch.setenv("JWT_SECRET", SEGREDO)
    assert _verificador_do_ambiente().segredo == SEGREDO
    monkeypatch.setenv("SUPABASE_URL", "https://auth.example.com")
    assert _verificador_do_ambiente().jwks_url.endswith("/.well-known/jwks.json")
