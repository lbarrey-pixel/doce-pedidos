"""Apoio aos testes do pagamento online: gateway falso injetado em `criar_app` (sem rede),
mundo com gateway e atalhos para aviso, pagamento e pedido."""

import pytest
from sqlalchemy import text

from app.portas.pagamento import Conferencia, GatewayIndisponivel, LinkCriado, codigo_do_aviso
from tests.integracao.apoio import montar_mundo, pedir, produzir, vid

URL_EXTERNA = "https://api.doceatelie.example"
ORIGENS = "https://app.doceatelie.example,https://outro.doceatelie.example"
AVISO = "/api/v1/gateway/checkout/aviso"
NAO_PAGO = Conferencia(False, False, 0, 0, 1, "")


class GatewayFalso:
    """Cumpre `GatewayDePagamento`. `pagar` diz o que a conferência vai responder."""

    segredo = "segredo-falso-de-teste"

    def __init__(self) -> None:
        self.links: list[dict] = []
        self.conferencias: list[tuple[str, str, str]] = []
        self.respostas: dict[str, Conferencia] = {}
        self.falha_link = False
        self.falha_conferir = False

    def criar_link(self, pedido_id, numero, valor_centavos, valido_ate, redirect_url, webhook_url):
        if self.falha_link:
            raise GatewayIndisponivel("gateway-links: HTTP 500")
        self.links.append(
            {
                "pedido_id": pedido_id,
                "numero": numero,
                "valor_centavos": valor_centavos,
                "valido_ate": valido_ate,
                "redirect_url": redirect_url,
                "webhook_url": webhook_url,
            }
        )
        url = f"https://pagar.doceatelie.example/{pedido_id}/{len(self.links)}"
        return LinkCriado(url=url, resposta={"url": url})

    def conferir(self, pedido_id, transaction_nsu, slug):
        if self.falha_conferir:
            raise GatewayIndisponivel("gateway-conferencia: HTTP 502")
        self.conferencias.append((pedido_id, transaction_nsu, slug))
        return self.respostas.get(transaction_nsu, NAO_PAGO)

    def codigo_do_aviso(self, pedido_id):
        return codigo_do_aviso(self.segredo, pedido_id)

    def pagar(self, nsu, total, *, metodo="pix", parcelas=1, pago=None, cobrado=None):
        self.respostas[nsu] = Conferencia(
            True, True, total if cobrado is None else cobrado, pago or total, parcelas, metodo
        )


@pytest.fixture
def gateway():
    return GatewayFalso()


@pytest.fixture
def mundo_gateway(engine, urls, relogio, gateway, monkeypatch):
    monkeypatch.setenv("CORS_ORIGENS", ORIGENS)
    loja, painel = montar_mundo(engine, relogio, gateway=gateway, url_externa=URL_EXTERNA)
    return loja, painel, gateway


def aviso(loja, gateway, pedido_id, nsu, *, slug="slug-1", codigo=None, **corpo):
    """O que o gateway posta no webhook; o código certo vem do segredo do servidor."""
    c = gateway.codigo_do_aviso(pedido_id) if codigo is None else codigo
    return loja.post(
        f"{AVISO}?c={c}",
        json={"order_nsu": pedido_id, "transaction_nsu": nsu, "invoice_slug": slug} | corpo,
    )


def volta(loja, pedido_id, nsu, slug="slug-1"):
    """A volta do cliente ao app com os dados da URL de retorno."""
    return loja.post(
        f"/api/v1/loja/pedidos/{pedido_id}/conferir",
        json={"transaction_nsu": nsu, "slug": slug},
    )


def pedido_com_link(loja, painel, engine, produzido=5, qtd=2, **extra):
    """Pronta entrega carregada e um pedido de 2 cheesecakes (R$ 53,80) com o link criado."""
    v = vid(engine)
    produzir(painel, v, produzido)
    r = pedir(loja, v, qtd=qtd, **extra)
    assert r.status_code == 201, r.json()
    return v, r.json()


def confirmacoes(engine, pedido_id=None):
    with engine.connect() as c:
        return [
            (r.resultado, r.origem)
            for r in c.execute(
                text(
                    "SELECT resultado, origem FROM doce.confirmacao_pagamento"
                    " WHERE (CAST(:p AS text) IS NULL OR pedido_id::text = :p) ORDER BY id"
                ),
                {"p": pedido_id},
            )
        ]


def vendas_baixadas(engine, variante) -> int:
    with engine.connect() as c:
        return c.execute(
            text(
                "SELECT coalesce(sum(quantidade), 0)::int FROM doce.movimento"
                " WHERE tipo = 'venda' AND variante_id::text = :v"
            ),
            {"v": variante},
        ).scalar_one()
