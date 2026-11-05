"""Adaptador do gateway de checkout (docs/contracts/gateway-checkout.md, ADR 0006): corpo e
cabeçalho do que sai, leitura do que volta e a chave fora de log e de erro. Sem rede: respx
intercepta o httpx."""

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.adaptadores.gateway_checkout import GatewayCheckout
from app.portas.pagamento import (
    Conferencia,
    GatewayDePagamento,
    GatewayIndisponivel,
    codigo_do_aviso,
)

BASE = "https://gateway.example/api"
CHAVE = "chave-secreta-de-teste-123"
SEGREDO = "segredo-do-aviso-de-teste"
PEDIDO = "2f6f1a52-5a3b-4a0c-9f43-0a8c5c7f3b11"
VALIDO_ATE = datetime(2026, 11, 4, 21, 40, tzinfo=ZoneInfo("America/Sao_Paulo"))
URL_PAGAMENTO = "https://checkout.example/doceatelie/abc123"


@pytest.fixture
def gateway():
    return GatewayCheckout(BASE, CHAVE, SEGREDO, cliente=httpx.Client())


def criar(gateway, **mudanca):
    dados = {
        "pedido_id": PEDIDO,
        "numero": 152,
        "valor_centavos": 5380,
        "valido_ate": VALIDO_ATE,
        "redirect_url": f"https://doceatelie.example/pedido/{PEDIDO}",
        "webhook_url": "https://api.doceatelie.example/api/v1/gateway/checkout/aviso?c=xyz",
    }
    return gateway.criar_link(**(dados | mudanca))


def test_cumpre_a_porta(gateway):
    assert isinstance(gateway, GatewayDePagamento)


@respx.mock
def test_criar_link_manda_exatamente_o_corpo_e_o_cabecalho_e_le_a_url(gateway):
    rota = respx.post(f"{BASE}/links").respond(json={"url": URL_PAGAMENTO, "slug": "abc123"})
    link = criar(gateway)
    assert link.url == URL_PAGAMENTO
    assert link.resposta == {"url": URL_PAGAMENTO, "slug": "abc123"}
    pedido = rota.calls.last.request
    assert pedido.headers["Authorization"] == f"Bearer {CHAVE}"
    assert json.loads(pedido.content) == {
        "order_nsu": PEDIDO,
        "items": [{"quantity": 1, "price": 5380, "description": "Pedido nº 152 · Doce Ateliê"}],
        "redirect_url": f"https://doceatelie.example/pedido/{PEDIDO}",
        "webhook": {
            "url": "https://api.doceatelie.example/api/v1/gateway/checkout/aviso?c=xyz",
            "events": ["paid", "canceled", "refunded"],
        },
        "options": {
            "single_payment": True,
            "valid_until": "2026-11-04T21:40:00-03:00",
            "payment_methods_enabled": ["credit_card", "pix"],
            "assured_installments": 0,
        },
    }


@respx.mock
def test_corpo_sem_dado_do_cliente_final(gateway):
    rota = respx.post(f"{BASE}/links").respond(json={"url": URL_PAGAMENTO})
    criar(gateway)
    corpo = json.loads(rota.calls.last.request.content)
    assert "customer" not in corpo and "address" not in corpo


@respx.mock
def test_sem_redirect_e_sem_webhook_os_dois_saem_do_corpo(gateway):
    rota = respx.post(f"{BASE}/links").respond(json={"url": URL_PAGAMENTO})
    criar(gateway, redirect_url=None, webhook_url=None)
    corpo = json.loads(rota.calls.last.request.content)
    assert "redirect_url" not in corpo and "webhook" not in corpo


@respx.mock
def test_aceita_a_url_na_chave_link(gateway):
    respx.post(f"{BASE}/links").respond(json={"link": URL_PAGAMENTO})
    assert criar(gateway).url == URL_PAGAMENTO


@respx.mock
def test_criar_link_com_500_vira_gateway_indisponivel(gateway):
    respx.post(f"{BASE}/links").respond(500, json={"erro": "x"})
    with pytest.raises(GatewayIndisponivel):
        criar(gateway)


@respx.mock
def test_criar_link_com_tempo_esgotado_vira_gateway_indisponivel(gateway):
    respx.post(f"{BASE}/links").mock(side_effect=httpx.ReadTimeout("demorou"))
    with pytest.raises(GatewayIndisponivel):
        criar(gateway)


@respx.mock
@pytest.mark.parametrize(
    "resposta",
    [{}, {"slug": "sem-url"}, {"url": ""}, {"url": "http://inseguro.example/pagar"}, ["lista"]],
)
def test_resposta_sem_url_valida_vira_gateway_indisponivel(gateway, resposta):
    respx.post(f"{BASE}/links").respond(json=resposta)
    with pytest.raises(GatewayIndisponivel):
        criar(gateway)


@respx.mock
def test_resposta_que_nao_e_json_vira_gateway_indisponivel(gateway):
    respx.post(f"{BASE}/links").respond(200, content=b"<html>erro</html>")
    with pytest.raises(GatewayIndisponivel):
        criar(gateway)


@respx.mock
def test_conferir_le_a_resposta_do_contrato(gateway):
    rota = respx.post(f"{BASE}/payments/check").respond(
        json={
            "success": True,
            "paid": True,
            "amount": 1500,
            "paid_amount": 1510,
            "installments": 1,
            "capture_method": "pix",
        }
    )
    c = gateway.conferir(PEDIDO, "nsu-1", "slug-1")
    assert c == Conferencia(True, True, 1500, 1510, 1, "pix")
    pedido = rota.calls.last.request
    assert pedido.headers["Authorization"] == f"Bearer {CHAVE}"
    assert json.loads(pedido.content) == {
        "order_nsu": PEDIDO,
        "transaction_nsu": "nsu-1",
        "slug": "slug-1",
    }


@respx.mock
def test_conferir_com_success_false_e_resposta_valida_nao_erro(gateway):
    respx.post(f"{BASE}/payments/check").respond(json={"success": False, "paid": False})
    c = gateway.conferir(PEDIDO, "nsu-1", "slug-1")
    assert c.success is False and c.paid is False
    assert c == Conferencia(False, False, 0, 0, 1, "")


@respx.mock
@pytest.mark.parametrize("paid", ["true", 1, None])
def test_paid_so_vale_com_booleano_verdadeiro(gateway, paid):
    respx.post(f"{BASE}/payments/check").respond(
        json={"success": True, "paid": paid, "amount": 1500, "paid_amount": 1500}
    )
    assert gateway.conferir(PEDIDO, "n", "s").paid is False


@respx.mock
def test_valores_nao_inteiros_viram_zero_e_nunca_confirmam(gateway):
    respx.post(f"{BASE}/payments/check").respond(
        json={"success": True, "paid": True, "amount": "1500", "paid_amount": 15.5}
    )
    c = gateway.conferir(PEDIDO, "n", "s")
    assert (c.amount, c.paid_amount) == (0, 0)


@respx.mock
def test_valor_inteiro_em_ponto_flutuante_e_aceito(gateway):
    respx.post(f"{BASE}/payments/check").respond(
        json={"success": True, "paid": True, "amount": 1500.0, "paid_amount": 1500.0}
    )
    c = gateway.conferir(PEDIDO, "n", "s")
    assert (c.amount, c.paid_amount) == (1500, 1500)


@respx.mock
def test_conferir_com_erro_de_rede_ou_status_vira_gateway_indisponivel(gateway):
    respx.post(f"{BASE}/payments/check").mock(side_effect=httpx.ConnectError("sem rede"))
    with pytest.raises(GatewayIndisponivel):
        gateway.conferir(PEDIDO, "n", "s")
    respx.post(f"{BASE}/payments/check").respond(502)
    with pytest.raises(GatewayIndisponivel):
        gateway.conferir(PEDIDO, "n", "s")


@respx.mock
def test_nenhuma_mensagem_de_erro_nem_log_leva_a_chave(gateway, caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(f"{BASE}/links").respond(500)
    respx.post(f"{BASE}/payments/check").mock(side_effect=httpx.ConnectError(f"falhou {CHAVE}"))
    erros = []
    for acao in (lambda: criar(gateway), lambda: gateway.conferir(PEDIDO, "n", "s")):
        with pytest.raises(GatewayIndisponivel) as e:
            acao()
        erros.append(e.value)
    for erro in erros:
        assert CHAVE not in str(erro) and CHAVE not in repr(erro)
        assert erro.__cause__ is None and erro.__suppress_context__
    assert CHAVE not in caplog.text


def test_repr_do_adaptador_nao_mostra_a_chave(gateway):
    assert CHAVE not in repr(gateway) and CHAVE not in str(vars(gateway).get("_http", ""))


# --- código do aviso --------------------------------------------------------


def test_codigo_e_hmac_sha256_da_chave_sobre_o_id_do_pedido_32_caracteres():
    # Valor de referência calculado fora do código, com openssl/hmac do Python:
    # hmac.new(b"chave", b"pedido-1", hashlib.sha256).hexdigest()[:32]
    assert codigo_do_aviso("chave", "pedido-1") == "233daa09d5ff2ab59053cdeeb96e22c5"


def test_codigo_depende_da_chave_e_do_pedido(gateway):
    assert codigo_do_aviso("chave", "a") != codigo_do_aviso("chave", "b")
    assert codigo_do_aviso("chave", "a") != codigo_do_aviso("outra", "a")
    assert gateway.codigo_do_aviso(PEDIDO) == codigo_do_aviso(SEGREDO, PEDIDO)
    assert gateway.codigo_do_aviso(PEDIDO) != codigo_do_aviso(CHAVE, PEDIDO)


def test_codigo_usa_o_segredo_proprio_quando_ha_um():
    g = GatewayCheckout(BASE, CHAVE, "outro-segredo", cliente=httpx.Client())
    assert g.codigo_do_aviso(PEDIDO) == codigo_do_aviso("outro-segredo", PEDIDO)
    assert g.codigo_do_aviso(PEDIDO) != codigo_do_aviso(CHAVE, PEDIDO)


def test_sem_segredo_do_aviso_o_adaptador_nao_nasce():
    with pytest.raises(ValueError):
        GatewayCheckout(BASE, CHAVE, "", cliente=httpx.Client())
