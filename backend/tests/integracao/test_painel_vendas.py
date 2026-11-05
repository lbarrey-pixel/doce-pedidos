"""Venda lançada no painel: nasce paga, baixa a pronta entrega e é tudo ou nada."""

from tests.integracao.apoio import produzir, saldo, vid

VENDAS = "/api/v1/painel/vendas"


def test_lancar_venda_baixa_a_pronta_entrega_e_nasce_paga(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 5)
    r = painel.post(VENDAS, json={"itens": [{"variante_id": v, "quantidade": 2}]})
    assert r.status_code == 200 and r.json()["total_centavos"] == 3980
    assert saldo(painel, v)["pronta"] == 3
    (p,) = [
        x for x in painel.get("/api/v1/painel/pedidos").json()["pedidos"] if x["canal"] == "balcao"
    ]
    assert p["estado"] == "pago" and p["forma_pagamento"] == "externo"
    assert p["id"] == r.json()["id"] and p["total_centavos"] == 3980


def test_venda_maior_que_o_saldo_nao_grava_nada(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 1)
    r = painel.post(VENDAS, json={"itens": [{"variante_id": v, "quantidade": 2}]})
    assert r.status_code == 422 and r.json()["erro"] == "falta_estoque"
    assert r.json()["disponivel"] == 1
    assert saldo(painel, v)["pronta"] == 1
    assert painel.get("/api/v1/painel/pedidos").json()["pedidos"] == []


def test_venda_de_item_fora_do_cardapio_e_recusada(mundo):
    _, painel = mundo
    r = painel.post(
        VENDAS,
        json={"itens": [{"variante_id": "3b6a7a4e-0000-4000-8000-000000000000", "quantidade": 1}]},
    )
    assert r.status_code == 422 and r.json()["erro"] == "variante_desconhecida"


def test_lancar_venda_exige_operador_e_ao_menos_um_item(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    assert (
        loja.post(VENDAS, json={"itens": [{"variante_id": v, "quantidade": 1}]}).status_code == 401
    )
    assert painel.post(VENDAS, json={"itens": []}).status_code == 422
