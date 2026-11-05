"""Mensagem do pedido para o WhatsApp da loja."""

from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app.dominio.mensagem import mensagem_do_pedido, url_whatsapp

FUSO = ZoneInfo("America/Sao_Paulo")


def test_texto_com_numero_itens_endereco_telefone_total_e_horario():
    texto = mensagem_do_pedido(
        numero=42,
        itens=[("Bolo de Pote Red Velvet · Individual", 2)],
        cliente_nome="Ana",
        telefone="11900000001",
        endereco="R. das Acácias, 150 — Jardim Azul",
        total_centavos=5380,
        entrega_a_partir_de=datetime(2026, 11, 2, 15, 40, tzinfo=FUSO),
    )
    for trecho in (
        "Pedido nº 42",
        "2× Bolo de Pote Red Velvet · Individual",
        "Ana",
        "11900000001",
        "R. das Acácias, 150",
        "R$ 53,80",
        "15h40",
    ):
        assert trecho in texto


def test_retirada_sem_endereco():
    texto = mensagem_do_pedido(
        numero=7,
        itens=[("X", 1)],
        cliente_nome="Bia",
        telefone="11",
        endereco=None,
        total_centavos=1990,
        entrega_a_partir_de=datetime(2026, 11, 2, 15, 10, tzinfo=FUSO),
    )
    assert "Retirada na loja" in texto


def test_url_wa_me_codificada():
    url = url_whatsapp("+55 (11) 90000-0002", "Olá & tchau")
    partes = urlparse(url)
    assert partes.netloc == "wa.me" and partes.path == "/5511900000002"
    assert parse_qs(partes.query)["text"] == ["Olá & tchau"]


def test_observacao_do_cliente_vai_na_mensagem():
    base = dict(
        numero=8,
        itens=[("X", 1)],
        cliente_nome="Bia",
        telefone="11",
        endereco="Av. das Palmeiras, 6690 — Jardim Botânico",
        total_centavos=1990,
        entrega_a_partir_de=datetime(2026, 11, 2, 15, 10, tzinfo=FUSO),
    )
    texto = mensagem_do_pedido(**base, observacao="Hospital, entregar para Maria na recepção")
    assert "Obs.: Hospital, entregar para Maria na recepção" in texto
    assert "Obs." not in mensagem_do_pedido(**base)
