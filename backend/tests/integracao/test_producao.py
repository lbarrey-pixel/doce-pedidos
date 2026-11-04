"""Produção do dia e alertas de véspera das Encomendas no painel."""

from datetime import datetime

from tests.integracao.apoio import FUSO, pedir, vid

GRANDE = ("Torta de Limão", "Inteira")


def encomendar(loja, painel, engine, entrega_em: str, pagar=True) -> dict:
    r = pedir(loja, vid(engine, *GRANDE), qtd=1, tipo_entrega="encomenda", entrega_em=entrega_em)
    assert r.status_code == 201, r.json()
    corpo = r.json()
    if pagar:
        r = painel.post(
            f"/api/v1/painel/pedidos/{corpo['id']}/confirmar-pagamento",
            json={"valor_recebido_centavos": corpo["total_centavos"]},
        )
        assert r.status_code == 200
    return corpo


def test_encomenda_paga_para_amanha_aparece_na_producao_do_dia(mundo, engine, relogio):
    loja, painel = mundo
    paga = encomendar(loja, painel, engine, "2026-11-03T15:00:00-03:00")
    encomendar(loja, painel, engine, "2026-11-03T16:00:00-03:00", pagar=False)  # sem Pix
    relogio.agora = datetime(2026, 11, 3, 9, 0, tzinfo=FUSO)  # manhã do dia
    corpo = painel.get("/api/v1/painel/producao").json()
    assert corpo["dia"] == "2026-11-03"
    assert [e["numero"] for e in corpo["encomendas"]] == [paga["numero"]]
    e = corpo["encomendas"][0]
    assert e["entrega_em"] == "2026-11-03T15:00:00-03:00"
    assert [(i["nome"], i["quantidade"], i["separado"]) for i in e["itens"]] == [
        ("Torta de Limão · Inteira", 1, 0)
    ]
    assert e["cliente"]["nome"] == "Ana Paula Souza" and e["recebimento"] == "entrega"
    assert painel.get("/api/v1/painel/producao?dia=2026-11-04").json()["encomendas"] == []


def test_encomenda_de_45_dias_avisada_na_vespera(mundo, engine, relogio):
    loja, painel = mundo
    paga = encomendar(loja, painel, engine, "2026-12-17T15:00:00-03:00")
    assert painel.get("/api/v1/painel/alertas").json()["encomendas"] == []
    relogio.agora = datetime(2026, 12, 16, 8, 0, tzinfo=FUSO)
    corpo = painel.get("/api/v1/painel/alertas").json()
    assert corpo["amanha"] == "2026-12-17"
    assert [e["numero"] for e in corpo["encomendas"]] == [paga["numero"]]


def test_aviso_da_vespera_separa_pagas_e_esperando_pix(mundo, engine, relogio):
    loja, painel = mundo
    paga = encomendar(loja, painel, engine, "2026-11-03T15:00:00-03:00")
    relogio.agora = datetime(2026, 11, 2, 18, 0, tzinfo=FUSO)
    sem_pix = encomendar(loja, painel, engine, "2026-11-03T16:00:00-03:00", pagar=False)
    corpo = painel.get("/api/v1/painel/alertas").json()
    assert [e["numero"] for e in corpo["encomendas"]] == [paga["numero"]]
    assert [e["numero"] for e in corpo["aguardando_pagamento"]] == [sem_pix["numero"]]
    assert corpo["aguardando_pagamento"][0]["estado"] == "aguardando_pagamento"


def test_encomenda_cancelada_sai_da_producao_e_dos_alertas(mundo, engine, relogio):
    loja, painel = mundo
    paga = encomendar(loja, painel, engine, "2026-11-03T15:00:00-03:00")
    r = painel.post(f"/api/v1/painel/pedidos/{paga['id']}/estado", json={"estado": "cancelado"})
    assert r.status_code == 200
    assert painel.get("/api/v1/painel/alertas").json()["encomendas"] == []
    assert painel.get("/api/v1/painel/producao?dia=2026-11-03").json()["encomendas"] == []


def test_producao_exige_operador_e_dia_valido(mundo, engine):
    loja, painel = mundo
    assert loja.get("/api/v1/painel/producao").status_code == 401
    r = painel.get("/api/v1/painel/producao?dia=ontem")
    assert r.status_code == 422
