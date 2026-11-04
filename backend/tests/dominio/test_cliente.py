"""Reconhecimento do cliente que volta: telefone + primeiro nome, endereço mascarado."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.dominio.cliente import Anterior, chave, endereco_reconhecido, mascarar

FUSO = ZoneInfo("America/Sao_Paulo")
T = datetime(2026, 10, 1, 15, 0, tzinfo=FUSO)
ACACIAS = {"logradouro": "R. das Acácias", "numero": "150", "bairro": "Jardim Azul"}
IPIRANGA = {"logradouro": "Av. das Palmeiras", "numero": "1000", "bairro": "Bairro Alto"}


def test_chave_telefone_so_digitos_e_primeiro_nome_normalizado():
    assert chave("(11) 99999-1234", "  Ána Paula Souza ") == ("11999991234", "ana")
    assert chave("11 99999 1234", "ana") == chave("(11) 99999-1234", "ANA")


def test_mascara_o_endereco():
    assert mascarar(ACACIAS) == "R. da••• Acácias, 1••, Jardim Azul"
    assert mascarar(IPIRANGA) == "Av. da••• Palmeiras, 1•••, Bairro Alto"


def test_reconhece_pelo_telefone_e_primeiro_nome():
    anteriores = [
        Anterior("11999991234", "Ana Paula Souza", ACACIAS, T),
        Anterior("11999991234", "Carlos", IPIRANGA, T + timedelta(days=3)),
    ]
    assert endereco_reconhecido(anteriores, "(11) 99999-1234", "ana") == ACACIAS
    assert endereco_reconhecido(anteriores, "11999991234", "Carla") is None
    assert endereco_reconhecido(anteriores, "11988887777", "Ana") is None
