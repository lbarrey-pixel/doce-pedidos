"""Encomenda: antecedência, produção do dia e alerta de véspera.

A montagem do pedido usa a interface pública de `pedido.montar_pedido`; a lista
de produção do dia e o alerta de véspera, a de `encomenda`.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.dominio.encomenda import EncomendaPaga, alertas_de_vespera, producao_do_dia
from app.dominio.pedido import Escolha, ItemCatalogo, Recusa, montar_pedido

FUSO = ZoneInfo("America/Sao_Paulo")
TARDE = datetime(2026, 11, 2, 15, 0, tzinfo=FUSO)
# 0 em pronta entrega e 1 na reserva congelada. O catálogo do app só enxerga a pronta
# entrega: a reserva congelada nem chega aqui.
CATALOGO = {
    "lc-grande": ItemCatalogo("lc-grande", "Torta de Limão · Inteira", 14590, 0),
    "choco-branco": ItemCatalogo("choco-branco", "Chocolate Branco c/ Frutas · Grande", 15990, 0),
    "doce-ind": ItemCatalogo("doce-ind", "Bolo de Pote Red Velvet · Individual", 1990, pronta=2),
}


def pedir(itens, *, agora=TARDE, tipo="pronta_entrega", entrega_em=None):
    return montar_pedido(
        [Escolha(v, q) for v, q in itens],
        CATALOGO,
        agora=agora,
        recebimento="retirada",
        distancia_m=None,
        desconto_pct=0,
        tipo_entrega=tipo,
        entrega_em=entrega_em,
    )


def recusa(itens, **kw) -> Recusa:
    with pytest.raises(Recusa) as e:
        pedir(itens, **kw)
    return e.value


def h(dia, hora, minuto=0, mes=11):
    return datetime(2026, mes, dia, hora, minuto, tzinfo=FUSO)


def test_sem_pronta_entrega_nao_vende_o_congelado_e_oferece_encomenda():
    r = recusa([("lc-grande", 1)])
    assert r.codigo == "sem_estoque" and r.dados["disponivel"] == 0
    assert r.dados["primeira_encomenda"] == h(3, 12, 0)  # 15h + 12 h = 3h, loja fechada → 12h
    p = pedir([("lc-grande", 1)], tipo="encomenda", entrega_em=h(3, 12, 0))
    assert p.tipo_entrega == "encomenda" and p.separar == []


def test_daqui_6_h_e_recusado_com_a_primeira_data_possivel():
    r = recusa([("choco-branco", 1)], tipo="encomenda", entrega_em=TARDE + timedelta(hours=6))
    assert r.codigo == "encomenda_antecedencia"
    assert r.dados["primeira_encomenda"] == h(3, 12, 0)


def test_encomenda_pedida_as_18h_primeira_opcao_amanha_12h():
    r = recusa([("lc-grande", 1)], agora=h(2, 18, 0))
    assert r.dados["primeira_encomenda"] == h(3, 12, 0)


def test_loja_fechada_aceita_encomenda_primeira_opcao_hoje_12h30():
    madrugada = h(3, 0, 30)
    r = recusa([("doce-ind", 1)], agora=madrugada)
    assert r.codigo == "loja_fechada" and r.dados["primeira_encomenda"] == h(3, 12, 30)
    assert pedir([("doce-ind", 1)], agora=madrugada, tipo="encomenda", entrega_em=h(3, 12, 30))


def test_encomenda_para_daqui_45_dias_e_aceita():
    p = pedir([("lc-grande", 1)], tipo="encomenda", entrega_em=h(17, 15, 0, mes=12))
    assert p.entrega_a_partir_de == h(17, 15, 0, mes=12)


def test_quer_3_ha_2_prontos_leva_2_ou_o_pedido_inteiro_vira_encomenda():
    r = recusa([("doce-ind", 3)])
    assert (r.codigo, r.dados["disponivel"]) == ("sem_estoque", 2)
    assert pedir([("doce-ind", 2)]).separar == [("doce-ind", 2)]
    inteiro = pedir([("doce-ind", 3)], tipo="encomenda", entrega_em=h(3, 15, 0))
    assert inteiro.separar == [] and inteiro.subtotal_centavos == 3 * 1990


def test_um_item_sem_pronta_entrega_o_pedido_inteiro_vira_encomenda():
    r = recusa([("doce-ind", 1), ("lc-grande", 1)])
    assert r.codigo == "sem_estoque" and r.dados["variante"] == "lc-grande"
    p = pedir([("doce-ind", 1), ("lc-grande", 1)], tipo="encomenda", entrega_em=h(3, 15, 0))
    assert p.separar == [] and len(p.itens) == 2  # uma só entrega, nada separado agora


AMANHA_15H = EncomendaPaga("p1", 101, h(3, 15, 0))
DAQUI_45_DIAS = EncomendaPaga("p2", 102, h(17, 15, 0, mes=12))
HOJE_19H = EncomendaPaga("p3", 103, h(2, 19, 0))


def test_encomenda_paga_para_amanha_aparece_na_producao_do_dia():
    todas = [DAQUI_45_DIAS, AMANHA_15H, HOJE_19H]
    assert producao_do_dia(todas, date(2026, 11, 3)) == [AMANHA_15H]
    assert producao_do_dia(todas, date(2026, 11, 2)) == [HOJE_19H]


def test_producao_do_dia_em_ordem_de_horario_e_pela_data_de_porto_alegre():
    cedo = EncomendaPaga("p4", 104, h(3, 12, 0))
    meia_noite_utc = EncomendaPaga("p5", 105, h(3, 23, 30))  # 02h30 UTC do dia 4
    assert producao_do_dia([meia_noite_utc, AMANHA_15H, cedo], date(2026, 11, 3)) == [
        cedo,
        AMANHA_15H,
        meia_noite_utc,
    ]


def test_alerta_na_vespera_e_so_na_vespera():
    todas = [DAQUI_45_DIAS, AMANHA_15H]
    assert alertas_de_vespera(todas, h(16, 9, 0, mes=12)) == [DAQUI_45_DIAS]
    assert alertas_de_vespera(todas, h(15, 9, 0, mes=12)) == []
    assert alertas_de_vespera(todas, h(2, 0, 5)) == [AMANHA_15H]


def test_hora_sem_fuso_e_erro():
    with pytest.raises(ValueError):
        producao_do_dia([EncomendaPaga("x", 1, datetime(2026, 11, 3, 15))], date(2026, 11, 3))
