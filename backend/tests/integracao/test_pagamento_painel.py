"""O operador em volta do pagamento online: lista com forma e valor pago, cancelamento com
aviso de estorno, pendências, resumo por forma e tarifas."""

from sqlalchemy import text

from tests.integracao.apoio import pedir, produzir, saldo, vid
from tests.integracao.apoio_pagamento import aviso, pedido_com_link

PAINEL = "/api/v1/painel/pedidos"
PENDENCIAS = "/api/v1/painel/pagamentos/pendencias"
CONFIGURACAO = "/api/v1/painel/configuracao"


def do_painel(painel, pedido_id):
    return next(p for p in painel.get(PAINEL).json()["pedidos"] if p["id"] == pedido_id)


def pagar(loja, gw, pedido, nsu, total=5380, **kw):
    gw.pagar(nsu, total, **kw)
    assert aviso(loja, gw, pedido["id"], nsu).status_code == 200


# --- listar -------------------------------------------------------------------------------


def test_painel_lista_traz_os_campos_de_pagamento_em_todos_os_pedidos(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v = vid(engine)
    produzir(painel, v, 10)
    pago = pedir(loja, v, qtd=2).json()
    esperando = pedir(loja, v, qtd=1).json()
    pagar(loja, gw, pago, "nsu-1", metodo="credit_card", parcelas=2, pago=5500)
    a, b = do_painel(painel, pago["id"]), do_painel(painel, esperando["id"])
    assert (a["forma_pagamento"], a["parcelas"], a["valor_pago_centavos"]) == ("cartao", 2, 5500)
    assert (a["pago_apos_expirar"], a["pagamento_link"]) == (False, None)
    assert b["estado"] == "aguardando_pagamento"
    assert (b["forma_pagamento"], b["parcelas"], b["valor_pago_centavos"]) == (
        "pix_manual",
        None,
        None,
    )


# --- cancelar -----------------------------------------------------------------------


def test_cancelar_pedido_pago_pelo_gateway_devolve_estoque_e_avisa_o_estorno(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    pagar(loja, gw, p, "nsu-1")
    assert saldo(painel, v)["pronta"] == 3
    r = painel.post(f"{PAINEL}/{p['id']}/estado", json={"estado": "cancelado"})
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert r.json()["estorno"] == {
        "valor_centavos": 5380,
        "mensagem": "Faça o estorno de R$ 53,80 no painel do gateway.",
    }
    assert saldo(painel, v)["pronta"] == 5  # o estoque voltou
    with engine.connect() as c:
        quem = c.execute(
            text(
                "SELECT cancelado_por::text AS q, o.nome FROM doce.pedido p"
                " JOIN doce.operador o ON o.id = p.cancelado_por WHERE p.id::text = :i"
            ),
            {"i": p["id"]},
        ).one()
    assert quem.nome == "Marina"  # o cancelamento registra quem cancelou
    # o sistema não estorna sozinho: nada mais foi pedido ao gateway
    assert len(gw.links) == 1


def test_estorno_de_pedido_parcelado_mostra_o_valor_que_o_cliente_pagou(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    pagar(loja, gw, p, "nsu-1", metodo="credit_card", parcelas=3, pago=5660)
    r = painel.post(f"{PAINEL}/{p['id']}/estado", json={"estado": "cancelado"})
    assert r.json()["estorno"]["valor_centavos"] == 5660
    assert "R$ 56,60" in r.json()["estorno"]["mensagem"]


def test_cancelar_depois_de_preparo_tambem_avisa_o_estorno(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    pagar(loja, gw, p, "nsu-1")
    painel.post(f"{PAINEL}/{p['id']}/estado", json={"estado": "em_preparo"})
    r = painel.post(f"{PAINEL}/{p['id']}/estado", json={"estado": "cancelado"})
    assert r.json()["estorno"]["valor_centavos"] == 5380


def test_cancelar_pedido_pago_na_mao_ou_aguardando_nao_traz_estorno(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, manual = pedido_com_link(loja, painel, engine)
    painel.post(
        f"{PAINEL}/{manual['id']}/confirmar-pagamento", json={"valor_recebido_centavos": 5380}
    )
    r = painel.post(f"{PAINEL}/{manual['id']}/estado", json={"estado": "cancelado"})
    assert r.status_code == 200 and "estorno" not in r.json()
    esperando = pedir(loja, v, qtd=1).json()
    r = painel.post(f"{PAINEL}/{esperando['id']}/estado", json={"estado": "cancelado"})
    assert r.status_code == 200 and "estorno" not in r.json()


# --- pendências ---------------------------------------------------------------------------


def test_pendencias_exigem_operador_e_resolver_e_idempotente(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    gw.pagar("nsu-1", 5380, cobrado=5000, pago=5000)
    aviso(loja, gw, p["id"], "nsu-1")
    assert loja.get(PENDENCIAS).status_code == 401
    (pend,) = painel.get(PENDENCIAS).json()["pendencias"]
    assert pend["resultado"] == "valor_recusado" and pend["pedido_id"] == p["id"]
    assert pend["numero"] == p["numero"] and pend["criado_em"]
    url = f"/api/v1/painel/pagamentos/pendencias/{pend['id']}/resolver"
    assert loja.post(url).status_code == 401
    assert painel.post(url).json() == {"resolvido": True}
    assert painel.post(url).status_code == 200  # repetir não quebra
    assert painel.get(PENDENCIAS).json()["pendencias"] == []
    with engine.connect() as c:
        r = c.execute(text("SELECT resolvido_em, resolvido_por FROM doce.confirmacao_pagamento"))
        linha = r.one()
    assert linha.resolvido_em is not None and linha.resolvido_por is not None


def test_pendencias_resolver_o_que_nao_existe_ou_nao_e_pendencia_e_404(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    pagar(loja, gw, p, "nsu-1")  # confirmado: não é pendência
    with engine.connect() as c:
        confirmado = c.execute(text("SELECT id FROM doce.confirmacao_pagamento")).scalar_one()
    base = "/api/v1/painel/pagamentos/pendencias"
    assert painel.post(f"{base}/{confirmado}/resolver").status_code == 404
    assert painel.post(f"{base}/99999/resolver").status_code == 404


def test_painel_nao_apaga_nem_edita_o_historico_de_confirmacoes(mundo_gateway, engine):
    """O papel da API só atualiza resolvido_em e resolvido_por (migration 0007)."""
    loja, painel, gw = mundo_gateway
    _, p = pedido_com_link(loja, painel, engine)
    pagar(loja, gw, p, "nsu-1")
    import pytest
    from sqlalchemy.exc import DBAPIError

    for sql in (
        "DELETE FROM doce.confirmacao_pagamento",
        "UPDATE doce.confirmacao_pagamento SET resultado = 'repetido'",
        "DELETE FROM doce.link_pagamento",
    ):
        with pytest.raises(DBAPIError), engine.begin() as c:
            c.execute(text(sql))


# --- resumo por forma ------------------------------------------------------------------------


def test_resumos_separam_pix_e_cartao_com_a_taxa_estimada(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v = vid(engine)
    produzir(painel, v, 20)
    pix = pedir(loja, v, qtd=2).json()
    cartao = pedir(loja, v, qtd=2).json()
    parcelado = pedir(loja, v, qtd=2).json()
    # Pix manual = pedido criado com o gateway fora do ar: sem link, a confirmação é na mão.
    gw.falha_link = True
    manual = pedir(loja, v, qtd=1).json()
    gw.falha_link = False
    pedir(loja, v, qtd=1)  # aguardando: fora
    pagar(loja, gw, pix, "n1")
    pagar(loja, gw, cartao, "n2", metodo="credit_card")
    pagar(loja, gw, parcelado, "n3", metodo="credit_card", parcelas=3, pago=5660)
    r_manual = painel.post(
        f"{PAINEL}/{manual['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": manual["total_centavos"]},
    )
    assert r_manual.status_code == 200, r_manual.json()
    painel.post("/api/v1/painel/vendas", json={"itens": [{"variante_id": v, "quantidade": 1}]})
    corpo = painel.get("/api/v1/painel/resumos?de=2026-11-02&ate=2026-11-08").json()
    forma = corpo["por_forma"]
    assert set(forma) == {"pix", "cartao", "pix_manual"}
    assert forma["pix"] == {"pedidos": 1, "valor_centavos": 5380, "taxa_estimada_centavos": 0}
    # cartão: 2 pedidos de R$ 53,80 (valor do pedido, não o pago com a taxa do parcelamento);
    # 4,20% de 10.760 = 451,92 → 452
    assert forma["cartao"] == {
        "pedidos": 2,
        "valor_centavos": 10760,
        "taxa_estimada_centavos": 452,
    }
    assert (
        forma["pix_manual"]["pedidos"] == 1 and forma["pix_manual"]["taxa_estimada_centavos"] == 0
    )
    # a venda lançada no painel (forma "externo") não entra em nenhuma das três formas
    assert sum(f["pedidos"] for f in forma.values()) == 4


def test_resumos_usam_as_tarifas_da_configuracao(mundo_gateway, engine):
    loja, painel, gw = mundo_gateway
    v, p = pedido_com_link(loja, painel, engine)
    pagar(loja, gw, p, "n1", metodo="credit_card")
    cfg = painel.get(CONFIGURACAO).json()
    painel.put(CONFIGURACAO, json=cfg | {"tarifa_cartao_bps": 549})
    corpo = painel.get("/api/v1/painel/resumos?de=2026-11-02&ate=2026-11-08").json()
    assert corpo["por_forma"]["cartao"]["taxa_estimada_centavos"] == 295  # 5,49% de 5380 = 295,36


# --- tarifas ------------------------------------------------------------------------------


def test_configuracao_traz_tarifas_de_exemplo(mundo_gateway):
    _, painel, _ = mundo_gateway
    assert painel.get(CONFIGURACAO).json() == {"tarifa_cartao_bps": 420, "tarifa_pix_bps": 0}


def test_tarifas_sao_editaveis(mundo_gateway):
    loja, painel, _ = mundo_gateway
    r = painel.put(CONFIGURACAO, json={"tarifa_cartao_bps": 500, "tarifa_pix_bps": 99})
    assert r.status_code == 200
    assert painel.get(CONFIGURACAO).json() == {"tarifa_cartao_bps": 500, "tarifa_pix_bps": 99}
    assert loja.get(CONFIGURACAO).status_code == 401
    assert (
        loja.put(CONFIGURACAO, json={"tarifa_cartao_bps": 1, "tarifa_pix_bps": 1}).status_code
        == 401
    )


def test_tarifa_invalida_nao_grava(mundo_gateway):
    _, painel, _ = mundo_gateway
    for ruim in (-1, 10001, True, "4,2", 4.2, None):
        r = painel.put(CONFIGURACAO, json={"tarifa_cartao_bps": ruim, "tarifa_pix_bps": 0})
        assert r.status_code == 422 and "tarifa_cartao_bps" in r.json()["mensagem"], ruim
    r = painel.put(CONFIGURACAO, json={"tarifa_cartao_bps": 420})  # falta a do Pix
    assert r.status_code == 422
    assert painel.get(CONFIGURACAO).json()["tarifa_cartao_bps"] == 420
