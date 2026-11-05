"""Pagar no app e o pedido confirmar sozinho.

Exemplo: 2 cheesecakes (R$ 39,80) + entrega a 5 km (R$ 14,00) = R$ 53,80. O gateway é falso
(sem rede); o contrato do adaptador está em tests/contrato/test_gateway_checkout.py.
"""

from datetime import datetime, timedelta

from sqlalchemy import text

from tests.integracao.apoio import FUSO, TARDE, pedir, produzir, saldo, vid
from tests.integracao.apoio_pagamento import (
    AVISO,
    ORIGENS,
    URL_EXTERNA,
    aviso,
    pedido_com_link,
    volta,
)

PEDIDOS = "/api/v1/loja/pedidos"
PAINEL = "/api/v1/painel/pedidos"


def do_painel(painel, pedido_id):
    return next(p for p in painel.get(PAINEL).json()["pedidos"] if p["id"] == pedido_id)


def test_pagar_cria_pedido_aguardando_com_link_do_valor_exato(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    assert p["estado"] == "aguardando_pagamento" and p["total_centavos"] == 5380
    assert p["pagamento"]["tipo"] == "link" and p["pagamento"]["url"].startswith("https://")
    assert p["pix"] is None  # com link não há copia e cola
    (link,) = gw.links
    assert link["valor_centavos"] == 5380 and link["pedido_id"] == p["id"]
    assert link["numero"] == p["numero"]
    # validade do link = expiração do pedido (30 min)
    assert link["valido_ate"] == TARDE + timedelta(minutes=30)
    assert datetime.fromisoformat(p["expira_em"]) == link["valido_ate"]
    assert saldo(painel, v)["separada"] == 2  # as 2 unidades ficam separadas
    with engine.connect() as c:
        guardado = c.execute(
            text("SELECT url, valor_centavos, valido_ate FROM doce.link_pagamento")
        ).one()
    assert guardado.url == p["pagamento"]["url"] and guardado.valor_centavos == 5380


def test_aviso_vai_para_a_url_do_servidor_com_o_codigo_do_pedido(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    esperado = f"{URL_EXTERNA}{AVISO}?c={gw.codigo_do_aviso(p['id'])}"
    assert gw.links[0]["webhook_url"] == esperado


def test_volta_ao_app_usa_a_origem_do_pedido_se_estiver_em_cors_origens(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v = vid(engine)
    produzir(painel, v, 10)
    corpo = {
        "cliente": {"nome": "Ana Paula Souza", "telefone": "(11) 90000-0001"},
        "recebimento": "retirada",
        "itens": [{"variante_id": v, "quantidade": 2}],
        "tipo_entrega": "pronta_entrega",
    }
    ok = loja.post(PEDIDOS, json=corpo, headers={"Origin": "https://outro.doceatelie.example"})
    assert ok.status_code == 201, ok.json()
    assert (
        gw.links[-1]["redirect_url"] == f"https://outro.doceatelie.example/pedido/{ok.json()['id']}"
    )
    # origem desconhecida (ou ausente) cai na primeira origem configurada
    for cabecalho in ({"Origin": "https://malvado.example"}, {}):
        r = loja.post(PEDIDOS, json=corpo, headers=cabecalho)
        assert r.status_code == 201
        assert gw.links[-1]["redirect_url"] == (f"{ORIGENS.split(',')[0]}/pedido/{r.json()['id']}")


def test_pagar_no_pix_confirma_sozinho_baixa_a_separacao_e_mostra_no_painel(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    r = aviso(loja, gw, p["id"], "nsu-1")
    assert r.status_code == 200
    s = saldo(painel, v)
    assert (s["pronta"], s["separada"]) == (3, 0)  # as 2 separadas saíram (venda)
    no_painel = do_painel(painel, p["id"])
    assert no_painel["estado"] == "pago" and no_painel["forma_pagamento"] == "pix"
    assert (no_painel["parcelas"], no_painel["valor_pago_centavos"]) == (1, 5380)
    assert no_painel["total_centavos"] == 5380 and no_painel["pago_apos_expirar"] is False
    acompanhado = loja.get(f"{PEDIDOS}/{p['id']}").json()
    assert acompanhado["estado"] == "pago" and acompanhado["forma_pagamento"] == "pix"
    assert acompanhado["pagamento"] is None and acompanhado["pix"] is None


def test_cartao_a_vista_mostra_a_forma_cartao(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-2", 5380, metodo="credit_card", parcelas=1)
    assert aviso(loja, gw, p["id"], "nsu-2").status_code == 200
    no_painel = do_painel(painel, p["id"])
    assert no_painel["estado"] == "pago" and no_painel["forma_pagamento"] == "cartao"
    assert no_painel["parcelas"] == 1


def test_parcelado_em_3x_mostra_valor_do_pedido_e_valor_pago(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-3", 5380, metodo="credit_card", parcelas=3, pago=5660)
    assert aviso(loja, gw, p["id"], "nsu-3").status_code == 200
    no_painel = do_painel(painel, p["id"])
    assert no_painel["estado"] == "pago" and no_painel["forma_pagamento"] == "cartao"
    assert no_painel["parcelas"] == 3
    assert no_painel["total_centavos"] == 5380 and no_painel["valor_pago_centavos"] == 5660


def test_volta_depois_de_10_min_sem_pagar_continua_aguardando_com_o_mesmo_link(
    mundo_gateway, engine, relogio
):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    relogio.agora = TARDE + timedelta(minutes=10)
    r = loja.get(f"{PEDIDOS}/{p['id']}").json()
    assert r["estado"] == "aguardando_pagamento"
    assert r["pagamento"] == p["pagamento"]  # o mesmo pagamento
    assert r["pix"] is None and len(gw.links) == 1  # não cria outro link
    assert datetime.fromisoformat(r["expira_em"]) == datetime.fromisoformat(
        p["expira_em"]
    )  # o App mostra "reservado até" mesmo ao voltar


def test_cartao_recusado_continua_aguardando_e_o_painel_nao_mostra_a_tentativa(
    mundo_gateway, engine
):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    # o gateway avisa, mas o conferência diz que não pagou (cartão recusado)
    assert aviso(loja, gw, p["id"], "nsu-recusado").status_code == 200
    assert volta(loja, p["id"], "nsu-recusado").json()["estado"] == "aguardando_pagamento"
    assert do_painel(painel, p["id"])["estado"] == "aguardando_pagamento"
    assert painel.get("/api/v1/painel/pagamentos/pendencias").json() == {"pendencias": []}
    # tenta outro cartão na mesma página e paga
    gw.pagar("nsu-ok", 5380, metodo="credit_card")
    assert aviso(loja, gw, p["id"], "nsu-ok").status_code == 200
    assert do_painel(painel, p["id"])["estado"] == "pago"


def test_nao_pago_em_30_min_expira_e_devolve_as_separadas(mundo_gateway, engine, relogio):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    relogio.agora = TARDE + timedelta(minutes=30)
    r = loja.get(f"{PEDIDOS}/{p['id']}").json()
    assert r["estado"] == "cancelado" and r["pagamento"] is None
    s = saldo(painel, v)
    assert (s["pronta"], s["separada"]) == (5, 0)


def test_encomenda_paga_no_ato_por_link_entra_na_producao(mundo_gateway, engine, relogio):
    loja, painel, gw = mundo_gateway
    grande = vid(engine, "Torta de Limão", "Inteira")
    r = pedir(loja, grande, qtd=1, tipo_entrega="encomenda", entrega_em="2026-11-03T15:00:00-03:00")
    assert r.status_code == 201, r.json()
    e = r.json()
    assert e["pagamento"]["tipo"] == "link" and gw.links[0]["valor_centavos"] == e["total_centavos"]
    gw.pagar("nsu-e", e["total_centavos"], metodo="credit_card")
    assert aviso(loja, gw, e["id"], "nsu-e").status_code == 200
    assert do_painel(painel, e["id"])["estado"] == "pago"
    relogio.agora = datetime(2026, 11, 3, 9, 0, tzinfo=FUSO)
    producao = painel.get("/api/v1/painel/producao").json()["encomendas"]
    assert [x["numero"] for x in producao] == [e["numero"]]


def test_gateway_fora_do_ar_o_pedido_nasce_com_o_pix_copia_e_cola(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    gw.falha_link = True
    v, p = pedido_com_link(loja, painel, engine)
    assert p["pagamento"] == {"tipo": "pix_manual"}
    assert p["pix"]["copia_e_cola"].startswith("000201")
    assert saldo(painel, v)["separada"] == 2  # o pedido foi criado
    acompanhado = loja.get(f"{PEDIDOS}/{p['id']}").json()
    assert acompanhado["pagamento"] == {"tipo": "pix_manual"}
    assert acompanhado["pix"]["copia_e_cola"] == p["pix"]["copia_e_cola"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM doce.link_pagamento")).scalar_one() == 0
    # a confirmação manual de hoje segue valendo
    r = painel.post(
        f"{PAINEL}/{p['id']}/confirmar-pagamento", json={"valor_recebido_centavos": 5380}
    )
    assert r.status_code == 200 and r.json()["estado"] == "pago"
    assert do_painel(painel, p["id"])["forma_pagamento"] == "pix_manual"


def test_sem_chave_do_gateway_o_comportamento_e_o_de_hoje(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 3)
    p = pedir(loja, v, qtd=1).json()
    assert p["pagamento"] == {"tipo": "pix_manual"} and p["pix"]["copia_e_cola"]


def test_gateway_no_ar_nao_mostra_o_pix_copia_e_cola(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    assert p["pix"] is None
    assert loja.get(f"{PEDIDOS}/{p['id']}").json()["pix"] is None


def test_sem_chave_pix_e_com_gateway_fora_o_pedido_nao_nasce(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    gw.falha_link = True
    with engine.begin() as c:
        c.execute(text("UPDATE doce.configuracao_loja SET pix_chave = ''"))
    v = vid(engine)
    produzir(painel, v, 3)
    r = pedir(loja, v, qtd=1)
    assert r.status_code == 503 and r.json()["erro"] == "pix_nao_configurado"
    assert saldo(painel, v)["separada"] == 0  # a transação inteira desfez


def test_mudar_o_tempo_para_pagar_faz_o_link_acompanhar_o_pedido(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    with engine.begin() as c:
        c.execute(
            text("UPDATE doce.configuracao_loja SET expiracao_pagamento_min = 45 WHERE id = 1")
        )
    _, p = pedido_com_link(loja, painel, engine)
    (link,) = gw.links
    assert link["valido_ate"] == TARDE + timedelta(minutes=45)
    assert datetime.fromisoformat(p["expira_em"]) == link["valido_ate"]
