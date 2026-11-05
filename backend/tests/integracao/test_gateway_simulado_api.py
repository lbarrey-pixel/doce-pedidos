"""Demonstração de ponta a ponta com o gateway simulado: criar o pedido, "pagar" na página de
mentira e ver o pedido confirmado, pela volta do cliente e pelo aviso."""

import pytest

from app.adaptadores.gateway_simulado import GatewaySimulado
from app.main import _gateway_do_ambiente, criar_app
from tests.integracao.apoio import montar_mundo, pedir, produzir, saldo, vid
from tests.integracao.apoio_pagamento import volta

PAGAR = "/api/v1/gateway/simulado/pagar"


@pytest.fixture
def mundo_simulado(engine, urls, relogio):
    return montar_mundo(engine, relogio, gateway=GatewaySimulado())


def novo_pedido(loja, painel, engine):
    v = vid(engine)
    produzir(painel, v, 5)
    r = pedir(loja, v, qtd=2)
    assert r.status_code == 201
    return v, r.json()


def test_pagar_na_pagina_simulada_e_voltar_confirma_o_pedido(mundo_simulado, engine):
    loja, painel = mundo_simulado
    v, p = novo_pedido(loja, painel, engine)
    assert p["pagamento"]["url"] == f"https://doceatelie.example/pagar/{p['id']}"
    dados = loja.post(PAGAR, json={"pedido_id": p["id"], "metodo": "credit_card", "parcelas": 3})
    assert dados.status_code == 200 and set(dados.json()) == {"transaction_nsu", "slug"}
    r = volta(loja, p["id"], dados.json()["transaction_nsu"], dados.json()["slug"])
    assert r.json()["estado"] == "pago" and r.json()["forma_pagamento"] == "cartao"
    assert saldo(painel, v)["separada"] == 0
    (no_painel,) = painel.get("/api/v1/painel/pedidos").json()["pedidos"]
    assert (no_painel["parcelas"], no_painel["valor_pago_centavos"]) == (3, 5380 + 5380 * 4 // 100)


def test_pagar_com_aviso_dispara_o_webhook_pelo_mesmo_caminho(mundo_simulado, engine):
    loja, painel = mundo_simulado
    _, p = novo_pedido(loja, painel, engine)
    r = loja.post(PAGAR, json={"pedido_id": p["id"], "metodo": "pix", "avisar": True})
    assert r.json()["resultado"] == "confirmado"
    assert loja.get(f"/api/v1/loja/pedidos/{p['id']}").json()["estado"] == "pago"


def test_pedido_sem_link_ou_id_invalido_responde_404(mundo_simulado):
    loja, _ = mundo_simulado
    for pedido_id in ("3b6a7a4e-0000-4000-8000-000000000000", "nao-e-uuid"):
        assert loja.post(PAGAR, json={"pedido_id": pedido_id}).status_code == 404


def test_a_rota_do_simulador_so_existe_com_o_gateway_simulado(mundo_gateway, mundo):
    for loja, *_ in (mundo_gateway, mundo):
        assert loja.post(PAGAR, json={"pedido_id": "x"}).status_code == 404


def test_gateway_do_ambiente(monkeypatch):
    for var in ("GATEWAY", "GATEWAY_API_URL", "GATEWAY_API_KEY", "GATEWAY_AVISO_CODIGO"):
        monkeypatch.delenv(var, raising=False)
    assert _gateway_do_ambiente() is None
    monkeypatch.setenv("GATEWAY_API_KEY", "so-a-chave")  # sem URL não liga
    assert _gateway_do_ambiente() is None
    monkeypatch.setenv("GATEWAY", "simulado")
    assert isinstance(_gateway_do_ambiente(), GatewaySimulado)
    monkeypatch.setenv("GATEWAY_API_URL", "https://gateway.example/api")
    monkeypatch.setenv("GATEWAY_AVISO_CODIGO", "segredo-do-aviso")
    real = _gateway_do_ambiente()
    assert type(real).__name__ == "GatewayCheckout"
    assert "so-a-chave" not in repr(real)


def test_gateway_http_sem_segredo_do_aviso_nao_sobe(monkeypatch):
    monkeypatch.delenv("GATEWAY_AVISO_CODIGO", raising=False)
    monkeypatch.setenv("GATEWAY_API_URL", "https://gateway.example/api")
    monkeypatch.setenv("GATEWAY_API_KEY", "so-a-chave")
    with pytest.raises(RuntimeError, match="GATEWAY_AVISO_CODIGO"):
        _gateway_do_ambiente()


def test_simulador_recusa_subir_em_ambiente_real(engine, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://projeto.supabase.example")
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        criar_app(engine=engine, gateway=GatewaySimulado(), verificador=object())
    monkeypatch.setenv("GATEWAY", "simulado")
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        criar_app(engine=engine, verificador=object())


def test_simulador_sobe_sem_sinal_de_ambiente_real(engine, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    app = criar_app(engine=engine, gateway=GatewaySimulado(), verificador=object())
    assert isinstance(app.state.gateway, GatewaySimulado)
