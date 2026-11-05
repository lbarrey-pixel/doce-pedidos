"""Link de pagamento para venda lançada no painel (balcão, WhatsApp, Instagram).

A venda nasce como sempre: paga, com o estoque baixado no lançamento. O link só liga a venda ao
pagamento do gateway; estoque e estado do pedido não mudam por causa dele.
"""

from datetime import timedelta
from urllib.parse import unquote

from sqlalchemy import text

from tests.integracao.apoio import TARDE, pedir, produzir, saldo, vid
from tests.integracao.apoio_pagamento import aviso, confirmacoes, vendas_baixadas

PAINEL = "/api/v1/painel/pedidos"
PENDENCIAS = "/api/v1/painel/pagamentos/pendencias"


def lancar(painel, v, qtd=2):
    r = painel.post(
        "/api/v1/painel/vendas", json={"itens": [{"variante_id": v, "quantidade": qtd}]}
    )
    assert r.status_code == 200, r.json()
    return r.json()


def gerar(painel, venda_id):
    return painel.post(f"/api/v1/painel/vendas/{venda_id}/link")


def da_lista(painel, pedido_id):
    return next(p for p in painel.get(PAINEL).json()["pedidos"] if p["id"] == pedido_id)


def mundo_com_venda(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v = vid(engine)
    produzir(painel, v, 10)
    return loja, painel, gw, v, lancar(painel, v)


def test_gerar_link_mostra_link_com_o_total_e_a_venda_aguarda_o_link(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    antes = saldo(painel, v)
    r = gerar(painel, venda["id"])
    assert r.status_code == 200, r.json()
    corpo = r.json()
    assert corpo["url"].startswith("https://")
    assert corpo["whatsapp_url"].startswith("https://wa.me/?text=")
    mensagem = unquote(corpo["whatsapp_url"].split("?text=")[1])
    assert corpo["url"] in mensagem and "R$ 39,80" in mensagem
    (link,) = gw.links
    assert link["valor_centavos"] == venda["total_centavos"] == 3980  # 2 × R$ 19,90
    assert link["pedido_id"] == venda["id"] and link["numero"] == venda["numero"]
    assert link["valido_ate"] == TARDE + timedelta(minutes=30)  # 30 min
    assert link["redirect_url"] is None  # o cliente do WhatsApp não tem página no App
    assert link["webhook_url"].endswith(gw.codigo_do_aviso(venda["id"]))
    assert da_lista(painel, venda["id"])["pagamento_link"] == "aguardando"
    assert saldo(painel, v) == antes  # estoque não muda
    assert da_lista(painel, venda["id"])["estado"] == "pago"  # a venda segue como hoje


def test_so_venda_lancada_no_painel_ganha_link(mundo_gateway, engine):
    loja, painel, gw, v, _ = mundo_com_venda(mundo_gateway, engine)
    pedido_do_app = pedir(loja, v, qtd=1).json()
    r = gerar(painel, pedido_do_app["id"])
    assert r.status_code == 422 and r.json()["erro"] == "canal_sem_link"
    assert [x["pedido_id"] for x in gw.links] == [pedido_do_app["id"]]  # o do próprio pedido
    assert gerar(painel, "3b6a7a4e-0000-4000-8000-000000000000").status_code == 404


def test_gerar_de_novo_com_o_link_vivo_devolve_o_mesmo_sem_criar_outro(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    a = gerar(painel, venda["id"]).json()
    b = gerar(painel, venda["id"]).json()
    assert a == b and len(gw.links) == 1


def test_gerar_link_exige_operador_e_gateway_no_ar(mundo_gateway, engine, mundo):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    assert loja.post(f"/api/v1/painel/vendas/{venda['id']}/link").status_code == 401
    gw.falha_link = True
    r = gerar(painel, venda["id"])
    assert r.status_code == 503 and r.json()["erro"] == "gateway_indisponivel"
    assert da_lista(painel, venda["id"])["pagamento_link"] is None
    gw.falha_link = False
    assert gerar(painel, venda["id"]).status_code == 200


def test_sem_gateway_configurado_responde_503(mundo, engine):
    _, painel = mundo
    v = vid(engine)
    produzir(painel, v, 5)
    venda = lancar(painel, v)
    r = gerar(painel, venda["id"])
    assert r.status_code == 503 and r.json()["erro"] == "pagamento_indisponivel"


def test_cliente_paga_o_link_e_a_venda_mostra_paga_pelo_link(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    baixadas = vendas_baixadas(engine, v)
    antes = saldo(painel, v)
    gerar(painel, venda["id"])
    gw.pagar("nsu-1", 3980, metodo="credit_card", parcelas=2, pago=4100)
    assert aviso(loja, gw, venda["id"], "nsu-1").status_code == 200
    d = da_lista(painel, venda["id"])
    assert d["pagamento_link"] == "pago" and d["estado"] == "pago"
    assert (d["forma_pagamento"], d["parcelas"], d["valor_pago_centavos"]) == ("cartao", 2, 4100)
    assert saldo(painel, v) == antes and vendas_baixadas(engine, v) == baixadas
    assert confirmacoes(engine, venda["id"]) == [("confirmado", "aviso")]


def test_mesmas_regras_de_conferencia_do_app(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    assert aviso(loja, gw, venda["id"], "falso").status_code == 200  # gateway não confirma
    assert da_lista(painel, venda["id"])["pagamento_link"] == "aguardando"
    gw.pagar("nsu-erro", 3980, pago=3000)  # pago a menos
    aviso(loja, gw, venda["id"], "nsu-erro")
    assert da_lista(painel, venda["id"])["pagamento_link"] == "aguardando"
    assert [x["resultado"] for x in painel.get(PENDENCIAS).json()["pendencias"]] == [
        "valor_recusado"
    ]
    gw.pagar("nsu-1", 3980)
    aviso(loja, gw, venda["id"], "nsu-1")
    aviso(loja, gw, venda["id"], "nsu-1")  # repetido
    assert da_lista(painel, venda["id"])["pagamento_link"] == "pago"
    gw.pagar("nsu-2", 3980)
    aviso(loja, gw, venda["id"], "nsu-2")  # segundo pagamento
    pend = painel.get(PENDENCIAS).json()["pendencias"]
    assert [x["resultado"] for x in pend] == ["valor_recusado", "a_estornar"]
    assert da_lista(painel, venda["id"])["pagamento_link"] == "pago"


def pronta(painel, v):
    return saldo(painel, v)["pronta"]


def test_link_nao_pago_em_30_min_cancela_a_venda_e_devolve_o_estoque(
    mundo_gateway, engine, relogio
):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    assert pronta(painel, v) == 8  # 10 produzidos − 2 vendidos no lançamento
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=29)
    d = da_lista(painel, venda["id"])
    assert d["pagamento_link"] == "aguardando" and d["estado"] == "pago"
    assert pronta(painel, v) == 8
    relogio.agora = TARDE + timedelta(minutes=30)
    d = da_lista(painel, venda["id"])
    assert d["pagamento_link"] == "expirado" and d["estado"] == "cancelado"
    assert pronta(painel, v) == 10  # as 2 unidades voltaram à pronta entrega
    relogio.agora = TARDE + timedelta(hours=3)
    assert pronta(painel, v) == 10  # expirar de novo não devolve de novo
    r = gerar(painel, venda["id"])  # não há "gerar outro link": lança-se a venda outra vez
    assert r.status_code == 409 and r.json()["erro"] == "transicao_invalida"
    assert len(gw.links) == 1


def test_venda_sem_link_nao_expira_e_o_estoque_fica(mundo_gateway, engine, relogio):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    relogio.agora = TARDE + timedelta(hours=5)
    d = da_lista(painel, venda["id"])
    assert d["estado"] == "pago" and d["pagamento_link"] is None
    assert pronta(painel, v) == 8


def test_pagamento_depois_de_expirar_com_estoque_baixa_de_novo_e_a_venda_volta_a_paga(
    mundo_gateway, engine, relogio
):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=40)
    assert pronta(painel, v) == 10  # devolvido ao expirar
    gw.pagar("nsu-1", 3980)
    aviso(loja, gw, venda["id"], "nsu-1")
    d = da_lista(painel, venda["id"])
    assert d["estado"] == "pago" and d["pagamento_link"] == "pago"
    assert d["pago_apos_expirar"] is True and d["valor_pago_centavos"] == 3980
    assert pronta(painel, v) == 8  # baixou de novo
    assert confirmacoes(engine, venda["id"]) == [("pago_depois_de_expirar", "aviso")]
    aviso(loja, gw, venda["id"], "nsu-1")  # aviso repetido não baixa outra vez
    assert pronta(painel, v) == 8
    assert painel.get(PENDENCIAS).json()["pendencias"] == []


def test_pagamento_depois_de_expirar_sem_estoque_vai_para_a_decidir(mundo_gateway, engine, relogio):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=40)
    outra = lancar(painel, v, qtd=9)  # leva quase tudo do que voltou
    assert pronta(painel, v) == 1
    gw.pagar("nsu-1", 3980)
    aviso(loja, gw, venda["id"], "nsu-1")
    d = da_lista(painel, venda["id"])
    assert d["estado"] == "cancelado" and d["pagamento_link"] == "expirado"
    assert d["pago_apos_expirar"] is False
    assert pronta(painel, v) == 1  # estoque intacto
    assert [x["resultado"] for x in painel.get(PENDENCIAS).json()["pendencias"]] == ["a_decidir"]
    assert da_lista(painel, outra["id"])["estado"] == "pago"


def test_operador_cancela_venda_lancada_e_o_estoque_volta(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    assert pronta(painel, v) == 8
    r = painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert pronta(painel, v) == 10


def test_cancelar_duas_vezes_nao_devolve_duas_vezes(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    url = f"{PAINEL}/{venda['id']}/estado"
    assert painel.post(url, json={"estado": "cancelado"}).status_code == 200
    r = painel.post(url, json={"estado": "cancelado"})
    assert r.status_code == 422 and r.json()["erro"] == "transicao_invalida"
    assert pronta(painel, v) == 10


def test_cancelar_venda_ja_cancelada_por_expiracao_nao_devolve_de_novo(
    mundo_gateway, engine, relogio
):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=30)
    assert pronta(painel, v) == 10
    r = painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
    assert r.json()["erro"] == "transicao_invalida"
    assert pronta(painel, v) == 10


def test_cancelar_com_link_vivo_devolve_uma_vez_e_o_prazo_do_link_nao_devolve_de_novo(
    mundo_gateway, engine, relogio
):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
    assert pronta(painel, v) == 10
    relogio.agora = TARDE + timedelta(minutes=45)
    d = da_lista(painel, venda["id"])
    assert d["estado"] == "cancelado" and pronta(painel, v) == 10


def test_cancelar_venda_paga_pelo_link_avisa_o_estorno(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    gw.pagar("nsu-1", 3980)
    aviso(loja, gw, venda["id"], "nsu-1")
    r = painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
    assert r.status_code == 200 and r.json()["estorno"]["valor_centavos"] == 3980
    assert pronta(painel, v) == 10  # o estoque volta; o dinheiro é estornado no gateway


def test_venda_cancelada_nao_gera_link_e_pagamento_depois_vira_a_estornar(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
    r = gerar(painel, venda["id"])
    assert r.status_code == 409 and r.json()["erro"] == "transicao_invalida"
    gw.pagar("nsu-1", 3980)
    aviso(loja, gw, venda["id"], "nsu-1")
    assert da_lista(painel, venda["id"])["pagamento_link"] == "aguardando"
    assert [x["resultado"] for x in painel.get(PENDENCIAS).json()["pendencias"]] == ["a_estornar"]
    d = da_lista(painel, venda["id"])
    assert d["estado"] == "cancelado" and pronta(painel, v) == 10  # nada baixa de novo


def test_venda_com_link_pago_nao_gera_outro(mundo_gateway, engine):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    gw.pagar("nsu-1", 3980)
    aviso(loja, gw, venda["id"], "nsu-1")
    r = gerar(painel, venda["id"])
    assert r.status_code == 409 and r.json()["erro"] == "link_ja_pago"


def devolucoes(engine, venda_id):
    """Quantas vezes o estoque da venda voltou (cancelamento ou expiração do link)."""
    with engine.connect() as c:
        return c.execute(
            text(
                "SELECT count(*) FROM doce.movimento WHERE pedido_id::text = :p"
                " AND (motivo LIKE 'link da venda%' OR motivo LIKE 'cancelamento do pedido%')"
            ),
            {"p": venda_id},
        ).scalar()


# --- reentrada e confirmação manual ------------------------------------------------


def test_confirmacao_manual_nunca_confirma_venda_lancada(mundo_gateway, engine, relogio):
    """Venda já nasce paga: nenhuma confirmação manual vale, nem com valor igual, nem com
    `aceitar_diferenca` no corpo, antes ou depois de o link expirar."""
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    url = f"{PAINEL}/{venda['id']}/confirmar-pagamento"
    corpos = (
        {"valor_recebido_centavos": 3980},
        {"valor_recebido_centavos": 3900},
        {"valor_recebido_centavos": 3900, "aceitar_diferenca": True},
        {"valor_recebido_centavos": 3980, "aceitar_diferenca": True},
    )
    for corpo in corpos:
        r = painel.post(url, json=corpo)
        assert r.status_code == 422 and r.json()["erro"] == "transicao_invalida", corpo
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=30)
    assert da_lista(painel, venda["id"])["estado"] == "cancelado"
    for corpo in corpos:
        r = painel.post(url, json=corpo)
        assert r.status_code == 422 and r.json()["erro"] == "transicao_invalida", corpo
    assert pronta(painel, v) == 10  # nenhuma confirmação mexeu no estoque
    assert confirmacoes(engine, venda["id"]) == []


def test_varias_rotas_na_expiracao_devolvem_o_estoque_uma_vez(mundo_gateway, engine, relogio):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=30)
    for _ in range(2):  # várias telas e ações logo após o prazo, na ordem em que o painel as chama
        assert da_lista(painel, venda["id"])["estado"] == "cancelado"
        assert pronta(painel, v) == 10
        assert painel.get(PENDENCIAS).status_code == 200
        painel.post(
            f"{PAINEL}/{venda['id']}/confirmar-pagamento", json={"valor_recebido_centavos": 3980}
        )
        r = painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
        assert r.json()["erro"] == "transicao_invalida"
    assert devolucoes(engine, venda["id"]) == 1
    lancar(painel, v, qtd=1)  # o saldo que sobra prova a devolução única
    assert pronta(painel, v) == 9


def test_cancelar_com_link_vivo_e_prazo_passado_devolve_uma_vez(mundo_gateway, engine, relogio):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    painel.post(f"{PAINEL}/{venda['id']}/estado", json={"estado": "cancelado"})
    relogio.agora = TARDE + timedelta(minutes=30)
    for _ in range(2):
        assert pronta(painel, v) == 10
        assert da_lista(painel, venda["id"])["estado"] == "cancelado"
    assert devolucoes(engine, venda["id"]) == 1


def test_aviso_repetido_sem_estoque_nao_duplica_pendencia_nem_baixa(mundo_gateway, engine, relogio):
    loja, painel, gw, v, venda = mundo_com_venda(mundo_gateway, engine)
    gerar(painel, venda["id"])
    relogio.agora = TARDE + timedelta(minutes=40)
    outra = lancar(painel, v, qtd=9)
    assert pronta(painel, v) == 1
    gw.pagar("nsu-1", 3980)
    for _ in range(3):
        aviso(loja, gw, venda["id"], "nsu-1")
        assert pronta(painel, v) == 1
    assert da_lista(painel, venda["id"])["estado"] == "cancelado"
    assert [x["resultado"] for x in painel.get(PENDENCIAS).json()["pendencias"]] == ["a_decidir"]
    assert [r for r, _ in confirmacoes(engine, venda["id"])] == [
        "a_decidir",
        "repetido",
        "repetido",
    ]
    assert da_lista(painel, outra["id"])["estado"] == "pago"
