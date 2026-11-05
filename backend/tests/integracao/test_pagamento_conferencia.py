"""Só conta como pago o que o gateway confirma: aviso falso, repetido, pagamento que não chegou,
pago depois de expirar, valor recusado, pago depois de cancelar e segundo pagamento.

Aviso do gateway nunca é prova: toda mudança no pedido passa pela conferência.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import text

from tests.integracao.apoio import TARDE, pedir, produzir, saldo, vid
from tests.integracao.apoio_pagamento import (
    AVISO,
    aviso,
    confirmacoes,
    pedido_com_link,
    vendas_baixadas,
    volta,
)

PEDIDOS = "/api/v1/loja/pedidos"
PAINEL = "/api/v1/painel/pedidos"
PENDENCIAS = "/api/v1/painel/pagamentos/pendencias"


def do_painel(painel, pedido_id):
    return next(p for p in painel.get(PAINEL).json()["pedidos"] if p["id"] == pedido_id)


def cancelar(painel, pedido_id):
    return painel.post(f"{PAINEL}/{pedido_id}/estado", json={"estado": "cancelado"})


# --- 2.1: aviso falso ---------------------------------------------------------------------


def test_codigo_errado_responde_400_sem_consultar_o_gateway(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    r = aviso(loja, gw, p["id"], "nsu-1", codigo="0" * 32)
    assert r.status_code == 400
    assert gw.conferencias == []
    assert do_painel(painel, p["id"])["estado"] == "aguardando_pagamento"
    # o código de outro pedido também não serve
    outro = aviso(loja, gw, p["id"], "nsu-1", codigo=gw.codigo_do_aviso("outro-pedido"))
    assert outro.status_code == 400 and gw.conferencias == []


def test_aviso_sem_codigo_ou_com_corpo_invalido_responde_400(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    assert loja.post(AVISO, json={"order_nsu": p["id"]}).status_code == 400
    c = gw.codigo_do_aviso(p["id"])
    assert loja.post(f"{AVISO}?c={c}", json={"order_nsu": p["id"]}).status_code == 400
    assert loja.post(f"{AVISO}?c={c}", content=b"nao e json").status_code == 400
    assert loja.post(f"{AVISO}?c={c}", json=["lista"]).status_code == 400
    assert (
        loja.post(
            f"{AVISO}?c=x",
            json={"order_nsu": "nao-uuid", "transaction_nsu": "n", "invoice_slug": "s"},
        ).status_code
        == 400
    )
    assert gw.conferencias == []


def test_aviso_de_pago_que_o_gateway_nao_confirma_e_ignorado_e_registrado(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    # o corpo do aviso diz "pago", mas o conferência responde paid: false
    r = aviso(loja, gw, p["id"], "nsu-falso", amount=5380, paid_amount=5380)
    assert r.status_code == 200
    assert do_painel(painel, p["id"])["estado"] == "aguardando_pagamento"
    assert saldo(painel, v)["separada"] == 2
    assert confirmacoes(engine, p["id"]) == [("nao_confirmado", "aviso")]
    assert gw.conferencias == [(p["id"], "nsu-falso", "slug-1")]


def test_o_registro_nao_guarda_dado_do_cliente_final(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    aviso(loja, gw, p["id"], "nsu-falso", customer={"name": "Ana Paula Souza"})
    with engine.connect() as c:
        linha = c.execute(text("SELECT row_to_json(t)::text FROM doce.confirmacao_pagamento t"))
        assert "Ana" not in linha.scalar_one()


def test_aviso_com_valor_so_no_corpo_nao_vale_o_gateway_manda(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    # corpo mente o valor: o que vale é a Conferência do gateway
    aviso(loja, gw, p["id"], "nsu-1", amount=1, paid_amount=1)
    assert do_painel(painel, p["id"])["valor_pago_centavos"] == 5380


# --- 2.2: idempotência --------------------------------------------------------------------


def test_aviso_repetido_nao_muda_nada_e_baixa_o_estoque_uma_vez(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    for _ in range(3):
        assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    assert do_painel(painel, p["id"])["estado"] == "pago"
    assert vendas_baixadas(engine, v) == 2
    s = saldo(painel, v)
    assert (s["pronta"], s["separada"]) == (3, 0)
    assert [r for r, _ in confirmacoes(engine, p["id"])] == [
        "confirmado",
        "repetido",
        "repetido",
    ]


def test_aviso_e_volta_ao_app_em_seguida_baixam_uma_vez(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    r = volta(loja, p["id"], "nsu-1")
    assert r.status_code == 200 and r.json()["estado"] == "pago"
    assert vendas_baixadas(engine, v) == 2
    assert confirmacoes(engine, p["id"]) == [("confirmado", "aviso"), ("repetido", "volta")]


def test_aviso_e_volta_ao_mesmo_tempo_baixam_uma_vez(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futuros = [
            pool.submit(aviso, loja, gw, p["id"], "nsu-1")
            if i % 2 == 0
            else pool.submit(volta, loja, p["id"], "nsu-1")
            for i in range(6)
        ]
        respostas = [f.result() for f in futuros]
    assert all(r.status_code == 200 for r in respostas)
    assert vendas_baixadas(engine, v) == 2
    s = saldo(painel, v)
    assert (s["pronta"], s["separada"]) == (3, 0)
    resultados = [r for r, _ in confirmacoes(engine, p["id"])]
    assert resultados.count("confirmado") == 1 and resultados.count("repetido") == 5


def test_mesmo_pagamento_nao_confirma_dois_pedidos(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v = vid(engine)
    produzir(painel, v, 6)
    a = pedir(loja, v, qtd=2).json()
    b = pedir(loja, v, qtd=2).json()
    assert a["total_centavos"] == b["total_centavos"]
    gw.pagar("nsu-a", 5380)
    aviso(loja, gw, a["id"], "nsu-a")
    # alguém tenta usar o pagamento de A para fechar B
    r = volta(loja, b["id"], "nsu-a")
    assert r.status_code == 200 and r.json()["estado"] == "aguardando_pagamento"
    assert do_painel(painel, b["id"])["estado"] == "aguardando_pagamento"
    assert vendas_baixadas(engine, v) == 2


# --- 2.3: aviso que não chegou ------------------------------------------------------------


def test_volta_ao_app_sem_aviso_confere_e_confirma(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    r = volta(loja, p["id"], "nsu-1")
    assert r.status_code == 200 and r.json()["estado"] == "pago"
    assert r.json()["forma_pagamento"] == "pix"
    assert confirmacoes(engine, p["id"]) == [("confirmado", "volta")]
    assert saldo(painel, v)["separada"] == 0


def test_volta_ao_app_de_pedido_que_nao_existe_e_404(mundo_gateway, engine):
    loja, _, gw = mundo_gateway
    r = volta(loja, "3b6a7a4e-0000-4000-8000-000000000000", "nsu-1")
    assert r.status_code == 404 and gw.conferencias == []


def test_painel_confere_com_o_ultimo_aviso_e_confirma(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    url = f"{PAINEL}/{p['id']}/conferir-pagamento"
    r = painel.post(url)  # nenhum aviso ainda
    assert r.status_code == 409 and r.json()["erro"] == "sem_aviso_gateway"
    aviso(loja, gw, p["id"], "nsu-1", slug="slug-9")  # chegou, mas o gateway ainda não confirma
    assert painel.post(url).json()["estado"] == "aguardando_pagamento"
    gw.pagar("nsu-1", 5380)
    r = painel.post(url)
    assert r.status_code == 200 and r.json()["estado"] == "pago"
    assert gw.conferencias[-1] == (p["id"], "nsu-1", "slug-9")
    assert vendas_baixadas(engine, v) == 2
    assert confirmacoes(engine, p["id"])[-1] == ("confirmado", "painel")


def test_conferir_exige_operador_logado(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    assert loja.post(f"{PAINEL}/{p['id']}/conferir-pagamento").status_code == 401


def test_gateway_fora_na_conferencia_responde_503_e_nao_confirma(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    gw.falha_conferir = True
    r = volta(loja, p["id"], "nsu-1")
    assert r.status_code == 503 and r.json()["erro"] == "gateway_indisponivel"
    r = aviso(loja, gw, p["id"], "nsu-1")  # 503 faz o gateway reenviar o aviso
    assert r.status_code == 503
    assert do_painel(painel, p["id"])["estado"] == "aguardando_pagamento"
    gw.falha_conferir = False
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    assert do_painel(painel, p["id"])["estado"] == "pago"


def test_sem_gateway_configurado_a_conferencia_responde_503(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 3)
    p = pedir(loja, v, qtd=1).json()
    r = loja.post(f"{PEDIDOS}/{p['id']}/conferir", json={"transaction_nsu": "n", "slug": "s"})
    assert r.status_code == 503 and r.json()["erro"] == "pagamento_indisponivel"


# --- 2.4: pago depois de expirar ----------------------------------------------------------


def test_pago_depois_de_expirar_com_estoque_separa_de_novo(mundo_gateway, engine, relogio):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    relogio.agora = TARDE + timedelta(minutes=45)
    assert loja.get(f"{PEDIDOS}/{p['id']}").json()["estado"] == "cancelado"
    assert saldo(painel, v)["pronta"] == 5
    gw.pagar("nsu-1", 5380)
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    no_painel = do_painel(painel, p["id"])
    assert no_painel["estado"] == "pago" and no_painel["pago_apos_expirar"] is True
    s = saldo(painel, v)
    assert (s["pronta"], s["separada"]) == (3, 0)
    assert vendas_baixadas(engine, v) == 2
    assert confirmacoes(engine, p["id"]) == [("pago_depois_de_expirar", "aviso")]


def test_pago_depois_de_expirar_sem_estoque_fica_para_o_operador_decidir(
    mundo_gateway, engine, relogio
):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine, produzido=2)
    relogio.agora = TARDE + timedelta(minutes=45)
    loja.get(f"{PEDIDOS}/{p['id']}")  # expira
    painel.post(  # outra venda leva as 2 unidades
        "/api/v1/painel/vendas",
        json={"itens": [{"variante_id": v, "quantidade": 2}]},
    )
    antes = saldo(painel, v)
    gw.pagar("nsu-1", 5380)
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    no_painel = do_painel(painel, p["id"])
    assert no_painel["estado"] == "cancelado" and no_painel["pago_apos_expirar"] is False
    assert saldo(painel, v) == antes  # estoque intacto
    assert confirmacoes(engine, p["id"]) == [("a_decidir", "aviso")]
    (pend,) = painel.get(PENDENCIAS).json()["pendencias"]
    assert pend["resultado"] == "a_decidir" and pend["numero"] == p["numero"]
    # repetir o aviso não duplica a pendência
    aviso(loja, gw, p["id"], "nsu-1")
    assert len(painel.get(PENDENCIAS).json()["pendencias"]) == 1
    assert [r for r, _ in confirmacoes(engine, p["id"])] == ["a_decidir", "repetido"]


# --- casos de borda -----------------------------------------------------------------------


def test_valor_recusado_nao_confirma_e_destaca_no_painel(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380, cobrado=5000, pago=5000)  # valor cobrado diferente do pedido
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    gw.pagar("nsu-2", 5380, pago=5300)  # pagou menos do que o cobrado
    assert aviso(loja, gw, p["id"], "nsu-2").status_code == 200
    assert do_painel(painel, p["id"])["estado"] == "aguardando_pagamento"
    assert saldo(painel, v)["separada"] == 2 and vendas_baixadas(engine, v) == 0
    pend = painel.get(PENDENCIAS).json()["pendencias"]
    assert [x["resultado"] for x in pend] == ["valor_recusado", "valor_recusado"]
    assert (pend[0]["valor_cobrado_centavos"], pend[0]["valor_pago_centavos"]) == (5000, 5000)
    assert pend[0]["total_centavos"] == 5380
    aviso(loja, gw, p["id"], "nsu-1")  # repetir não lista de novo
    assert len(painel.get(PENDENCIAS).json()["pendencias"]) == 2


def test_pago_depois_de_cancelado_pelo_operador_a_estornar_sem_mexer_em_nada(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    assert cancelar(painel, p["id"]).status_code == 200
    antes = saldo(painel, v)
    assert antes["pronta"] == 5
    gw.pagar("nsu-1", 5380)
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200
    assert do_painel(painel, p["id"])["estado"] == "cancelado"
    assert saldo(painel, v) == antes and vendas_baixadas(engine, v) == 0
    (pend,) = painel.get(PENDENCIAS).json()["pendencias"]
    assert pend["resultado"] == "a_estornar" and pend["valor_pago_centavos"] == 5380
    # o cliente vê a orientação do WhatsApp
    visto = loja.get(f"{PEDIDOS}/{p['id']}").json()
    assert visto["estado"] == "cancelado" and visto["a_estornar"] is True
    assert visto["whatsapp_url"].startswith("https://wa.me/5511900000002?text=")
    # resolvida pelo operador, a mensagem some
    r = painel.post(f"/api/v1/painel/pagamentos/pendencias/{pend['id']}/resolver")
    assert r.status_code == 200
    assert loja.get(f"{PEDIDOS}/{p['id']}").json()["a_estornar"] is False
    assert painel.get(PENDENCIAS).json()["pendencias"] == []


def test_segundo_pagamento_do_mesmo_pedido_a_estornar(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    gw.pagar("nsu-2", 5380, metodo="credit_card")  # dois aparelhos pagaram
    aviso(loja, gw, p["id"], "nsu-1")
    assert aviso(loja, gw, p["id"], "nsu-2").status_code == 200
    no_painel = do_painel(painel, p["id"])
    assert no_painel["estado"] == "pago" and no_painel["forma_pagamento"] == "pix"
    assert vendas_baixadas(engine, v) == 2  # baixou uma vez só
    (pend,) = painel.get(PENDENCIAS).json()["pendencias"]
    assert pend["resultado"] == "a_estornar"
    assert loja.get(f"{PEDIDOS}/{p['id']}").json()["a_estornar"] is True


def test_pedido_do_link_nao_aceita_confirmacao_manual(mundo_gateway, engine):
    """Confirmar na mão um pedido do link faria o aviso do mesmo pagamento
    virar "a estornar". Só o gateway confirma; o painel esconde "Recebi R$"."""
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    url = f"{PAINEL}/{p['id']}/confirmar-pagamento"
    for corpo in (
        {"valor_recebido_centavos": 5380},
        {"valor_recebido_centavos": 5300},
    ):
        r = painel.post(url, json=corpo)
        assert r.status_code == 409 and r.json()["erro"] == "pagamento_pelo_gateway"
    assert do_painel(painel, p["id"])["paga_pelo_link"] is True
    gw.pagar("nsu-1", 5380)
    aviso(loja, gw, p["id"], "nsu-1")
    assert do_painel(painel, p["id"])["estado"] == "pago"
    assert vendas_baixadas(engine, v) == 2
    assert painel.get(PENDENCIAS).json()["pendencias"] == []


def test_aviso_de_pedido_desconhecido_com_codigo_valido_so_registra(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    fantasma = "3b6a7a4e-0000-4000-8000-000000000000"
    r = aviso(loja, gw, fantasma, "nsu-x")
    assert r.status_code == 200 and gw.conferencias == []
    assert confirmacoes(engine) == [("nao_confirmado", "aviso")]


def test_aviso_nao_exige_login_de_operador(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380)
    assert aviso(loja, gw, p["id"], "nsu-1").status_code == 200  # `loja` não tem token
