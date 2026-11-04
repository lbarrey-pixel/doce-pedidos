"""Saída com o entregador e Entregue pelo tempo.

Controle visual, sem confirmação: o pedido que saiu vira Entregue sozinho depois do tempo
médio de entrega (30 min). Retirada vira Entregue quando o cliente retira.
"""

from datetime import timedelta

from tests.integracao.apoio import TARDE, pedir, produzir, vid

MOTOBOY = {"nome": "Coop. Motoboys Express", "telefone": "(11) 3333-4444"}


def pago(loja, painel, engine, **extra):
    doce = vid(engine)
    produzir(painel, doce, 2)
    p = pedir(loja, doce, qtd=1, **extra).json()
    painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": p["total_centavos"]},
    )
    painel.post(f"/api/v1/painel/pedidos/{p['id']}/estado", json={"estado": "em_preparo"})
    return p


def lista(painel):
    return {p["id"]: p for p in painel.get("/api/v1/painel/pedidos").json()["pedidos"]}


def test_saiu_com_entregador_e_vira_entregue_depois_do_tempo_medio(mundo, engine, relogio):
    loja, painel = mundo
    p = pago(loja, painel, engine)
    r = painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/estado", json={"estado": "saiu", "entregador": MOTOBOY}
    )
    assert r.status_code == 200
    visto = lista(painel)[p["id"]]
    assert visto["estado"] == "saiu" and visto["entregador"] == {
        "nome": "Coop. Motoboys Express",
        "telefone": "1133334444",
    }
    assert visto["entregue_previsto_em"] == (TARDE + timedelta(minutes=30)).isoformat()
    relogio.agora = TARDE + timedelta(minutes=29)
    assert lista(painel)[p["id"]]["estado"] == "saiu"
    relogio.agora = TARDE + timedelta(minutes=30)
    assert lista(painel)[p["id"]]["estado"] == "entregue"


def test_entregador_fica_salvo_para_escolher_depois(mundo, engine):
    loja, painel = mundo
    p = pago(loja, painel, engine)
    painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/estado", json={"estado": "saiu", "entregador": MOTOBOY}
    )
    assert painel.get("/api/v1/painel/entregadores").json()["entregadores"] == [
        {"nome": "Coop. Motoboys Express", "telefone": "1133334444"}
    ]


def test_saiu_sem_entregador_tambem_vale(mundo, engine, relogio):
    loja, painel = mundo
    p = pago(loja, painel, engine)
    r = painel.post(f"/api/v1/painel/pedidos/{p['id']}/estado", json={"estado": "saiu"})
    assert r.status_code == 200 and lista(painel)[p["id"]]["entregador"] is None


def test_retirada_vira_entregue_quando_o_cliente_retira(mundo, engine):
    loja, painel = mundo
    p = pago(loja, painel, engine, recebimento="retirada", endereco=None)
    r = painel.post(f"/api/v1/painel/pedidos/{p['id']}/estado", json={"estado": "saiu"})
    assert r.status_code == 200 and r.json()["estado"] == "entregue"
    assert lista(painel)[p["id"]]["estado"] == "entregue"
