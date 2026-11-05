"""O simulador respeita o mesmo contrato da porta: é o que os testes de integração e a
demonstração usam no lugar do gateway de verdade."""

from datetime import UTC, datetime

import pytest

from app.adaptadores.gateway_simulado import GatewaySimulado
from app.portas.pagamento import Conferencia, GatewayDePagamento, GatewayIndisponivel

PEDIDO = "2f6f1a52-5a3b-4a0c-9f43-0a8c5c7f3b11"
VALIDO_ATE = datetime(2026, 11, 4, 21, 40, tzinfo=UTC)


def gateway_com_link(valor=5380):
    g = GatewaySimulado()
    g.criar_link(PEDIDO, 1, valor, VALIDO_ATE, None, None)
    return g


def test_cumpre_a_porta_e_o_link_usa_o_dominio_ficticio():
    g = GatewaySimulado()
    assert isinstance(g, GatewayDePagamento)
    link = g.criar_link(PEDIDO, 1, 5380, VALIDO_ATE, None, None)
    assert link.url == f"https://doceatelie.example/pagar/{PEDIDO}"


def test_pix_paga_o_valor_cobrado():
    g = gateway_com_link()
    nsu, slug = g.pagar(PEDIDO, "pix")
    assert g.conferir(PEDIDO, nsu, slug) == Conferencia(True, True, 5380, 5380, 1, "pix")


def test_cartao_parcelado_soma_juros_ao_valor_pago():
    g = gateway_com_link(10_000)
    nsu, slug = g.pagar(PEDIDO, "credit_card", 3)
    c = g.conferir(PEDIDO, nsu, slug)
    assert (c.amount, c.paid_amount, c.installments) == (10_000, 10_400, 3)


def test_pagamento_desconhecido_ou_de_outro_pedido_nao_confirma():
    g = gateway_com_link()
    nsu, slug = g.pagar(PEDIDO)
    assert g.conferir(PEDIDO, "nsu-que-nao-existe", slug).paid is False
    assert g.conferir("outro-pedido", nsu, slug).paid is False
    assert g.conferir(PEDIDO, nsu, "slug-errado").paid is False


def test_fora_do_ar_vira_gateway_indisponivel():
    g = gateway_com_link()
    g.fora_do_ar = True
    with pytest.raises(GatewayIndisponivel):
        g.criar_link(PEDIDO, 1, 5380, VALIDO_ATE, None, None)
    with pytest.raises(GatewayIndisponivel):
        g.conferir(PEDIDO, "n", "s")
