"""Montagem do pedido do app: taxa, desconto, mínimo, estoque, horário e expiração."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.dominio.horario import Horario
from app.dominio.pedido import (
    Escolha,
    ItemCatalogo,
    Recusa,
    ValorDivergente,
    confirmar_pagamento,
    expirou,
    montar_pedido,
)

FUSO = ZoneInfo("America/Sao_Paulo")
TARDE = datetime(2026, 11, 2, 15, 0, tzinfo=FUSO)
CATALOGO = {
    "doce-ind": ItemCatalogo("doce-ind", "Bolo de Pote Red Velvet · Individual", 1990, pronta=5),
    "lc-ind": ItemCatalogo(
        "lc-ind", "Bolo de Pote de Cenoura com Brigadeiro · Individual", 1790, pronta=3
    ),
    "choco-p": ItemCatalogo("choco-p", "Cheesecake de Frutas Vermelhas · Fatia", 5290, pronta=4),
    "lc-grande": ItemCatalogo("lc-grande", "Torta de Limão · Inteira", 14590, 0),
    "calda": ItemCatalogo("calda", "Calda de Caramelo · 30 g", 490, pronta=9),
    "cartao": ItemCatalogo("cartao", "Cartão para Presente · Médio", 300, pronta=9),
    "ganache": ItemCatalogo("ganache", "Ganache de Nutella · 30 g", 890, pronta=9),
    "coca": ItemCatalogo("coca", "Coca-Cola · Lata 350 ml", 890, pronta=9),
    "sacola": ItemCatalogo("sacola", "Sacola Borboletas", 990, pronta=9),
}


def pedir(itens, *, agora=TARDE, km=2.0, desconto=0, recebimento="entrega", **kw):
    return montar_pedido(
        [Escolha(v, q) for v, q in itens],
        CATALOGO,
        agora=agora,
        recebimento=recebimento,
        distancia_m=None if km is None else round(km * 1000),
        desconto_pct=desconto,
        **({"tipo_entrega": "pronta_entrega", "entrega_em": None} | kw),
    )


def recusa(itens, **kw):
    with pytest.raises(Recusa) as e:
        pedir(itens, **kw)
    return e.value


def test_pronta_entrega_a_5_km():
    p = pedir([("doce-ind", 2)], km=5)
    assert (p.subtotal_centavos, p.desconto_centavos, p.taxa_entrega_centavos) == (3980, 0, 1400)
    assert p.total_centavos == 5380
    assert p.separar == [("doce-ind", 2)]
    assert p.entrega_a_partir_de == TARDE + timedelta(minutes=40)
    assert p.expira_em == TARDE + timedelta(minutes=30)


def test_abaixo_do_minimo_de_8_reais():
    assert recusa([("calda", 1)]).codigo == "abaixo_do_minimo"
    r = recusa([("calda", 1), ("cartao", 1)])
    assert (r.codigo, r.dados["falta_centavos"]) == ("abaixo_do_minimo", 10)


def test_acima_do_minimo_sem_desconto():
    assert pedir([("ganache", 1)]).subtotal_centavos == 890
    assert pedir([("coca", 1), ("sacola", 1)]).subtotal_centavos == 1880


def test_acima_de_12_km_e_sob_consulta():
    assert recusa([("doce-ind", 1)], km=13).codigo == "sob_consulta"


def test_entrega_sem_distancia_e_endereco_nao_encontrado():
    assert recusa([("doce-ind", 1)], km=None).codigo == "endereco_nao_encontrado"


def test_loja_fechada_so_aceita_encomenda():
    madrugada = datetime(2026, 11, 3, 0, 30, tzinfo=FUSO)
    r = recusa([("doce-ind", 1)], agora=madrugada)
    assert r.codigo == "loja_fechada"
    assert r.dados["primeira_encomenda"] == datetime(2026, 11, 3, 12, 30, tzinfo=FUSO)
    p = pedir(
        [("doce-ind", 1)],
        agora=madrugada,
        tipo_entrega="encomenda",
        entrega_em=datetime(2026, 11, 3, 12, 30, tzinfo=FUSO),
    )
    assert p.separar == [] and p.entrega_a_partir_de.hour == 12


@pytest.mark.parametrize(
    ("itens", "desconto", "km", "valores"),
    [
        ([("choco-p", 2)], 10, 2, (10580, 1058, 1000, 10522)),  # 2.6
        ([("lc-ind", 1)], 10, 3, (1790, 179, 1000, 2611)),
        ([("doce-ind", 1)], 15, 6, (1990, 298, 1400, 3092)),
    ],
)
def test_desconto_so_nos_itens_arredondado_para_baixo(itens, desconto, km, valores):
    p = pedir(itens, desconto=desconto, km=km)
    assert (
        p.subtotal_centavos,
        p.desconto_centavos,
        p.taxa_entrega_centavos,
        p.total_centavos,
    ) == valores


def test_retirada_sem_taxa_e_sem_distancia():
    p = pedir([("doce-ind", 1)], recebimento="retirada", km=None)
    assert (p.taxa_entrega_centavos, p.total_centavos) == (0, 1990)
    assert p.entrega_a_partir_de == TARDE + timedelta(minutes=10)


def test_sem_pronta_entrega_suficiente_oferece_encomenda():
    r = recusa([("lc-ind", 4)])
    assert (r.codigo, r.dados["variante"], r.dados["disponivel"]) == ("sem_estoque", "lc-ind", 3)
    assert r.dados["primeira_encomenda"] == datetime(2026, 11, 3, 12, 0, tzinfo=FUSO)
    assert recusa([("doce-ind", 1), ("lc-grande", 1)]).dados["variante"] == "lc-grande"


def test_encomenda_antes_de_12_h_e_recusada():
    r = recusa(
        [("lc-grande", 1)],
        tipo_entrega="encomenda",
        entrega_em=TARDE + timedelta(hours=6),
    )
    assert r.codigo == "encomenda_antecedencia"
    assert r.dados["primeira_encomenda"] == datetime(2026, 11, 3, 12, 0, tzinfo=FUSO)


def test_encomenda_nao_olha_a_pronta_entrega():
    p = pedir(
        [("lc-grande", 2)],
        tipo_entrega="encomenda",
        entrega_em=datetime(2026, 11, 3, 15, 0, tzinfo=FUSO),
    )
    assert p.separar == [] and p.total_centavos == 2 * 14590 + 1000


def test_variante_fora_do_cardapio_ou_quantidade_invalida():
    assert recusa([("nao-existe", 1)]).codigo == "variante_indisponivel"
    with pytest.raises(ValueError):
        pedir([("doce-ind", 0)])
    assert recusa([]).codigo == "carrinho_vazio"


def test_confirmacao_do_pagamento():
    assert confirmar_pagamento(5380, 5380, aceitar_diferenca=False) == 0
    with pytest.raises(ValorDivergente) as e:
        confirmar_pagamento(5380, 5300, aceitar_diferenca=False)
    assert (e.value.esperado, e.value.recebido) == (5380, 5300)
    assert confirmar_pagamento(5380, 5300, aceitar_diferenca=True) == -80


def test_expira_em_30_min_sem_confirmacao():
    expira = TARDE + timedelta(minutes=30)
    assert not expirou("aguardando_pagamento", expira, expira - timedelta(seconds=1))
    assert expirou("aguardando_pagamento", expira, expira)
    assert not expirou("pago", expira, expira + timedelta(hours=1))


# Pronta entrega agendada para hoje.
MANHA = datetime(2026, 11, 2, 8, 40, tzinfo=FUSO)
OITO_AS_24 = Horario(time(8, 0), time(0, 0))


def agendar(entrega, preparo=30, itens=(("doce-ind", 1),)):
    return pedir(
        list(itens),
        agora=MANHA,
        horario=OITO_AS_24,
        entrega_em=entrega,
        tempo_preparo_min=preparo,
    )


def test_agendada_para_hoje_separa_e_entrega_no_horario():
    meio_dia = MANHA.replace(hour=12, minute=0)
    p = agendar(meio_dia)
    assert p.tipo_entrega == "pronta_entrega"
    assert p.separar == [("doce-ind", 1)]
    assert p.entrega_a_partir_de == meio_dia


def test_agendada_antes_do_tempo_de_preparo_e_recusada():
    with pytest.raises(Recusa) as e:
        agendar(MANHA.replace(hour=9, minute=30), preparo=60)
    assert e.value.codigo == "agendamento_horario"
    assert e.value.dados["primeiro_agendamento"] == MANHA.replace(hour=10, minute=0)


def test_agendada_sem_pronta_entrega_suficiente_e_recusada():
    with pytest.raises(Recusa) as e:
        agendar(MANHA.replace(hour=12, minute=0), itens=(("lc-grande", 1),))
    assert e.value.codigo == "sem_estoque"


def test_agendada_para_outro_dia_e_recusada():
    with pytest.raises(Recusa) as e:
        agendar(MANHA + timedelta(days=1))
    assert e.value.codigo == "agendamento_horario"


def test_antes_de_abrir_agenda_a_partir_da_abertura_mais_preparo():
    sete = MANHA.replace(hour=7, minute=0)
    p = pedir(
        [("doce-ind", 1)],
        agora=sete,
        horario=OITO_AS_24,
        entrega_em=sete.replace(hour=8, minute=30),
    )
    assert p.tipo_entrega == "pronta_entrega" and p.separar == [("doce-ind", 1)]
    assert p.entrega_a_partir_de == sete.replace(hour=8, minute=30)
    with pytest.raises(Recusa) as e:  # sem horário escolhido continua fechado
        pedir([("doce-ind", 1)], agora=sete, horario=OITO_AS_24)
    assert e.value.codigo == "loja_fechada"
    with pytest.raises(Recusa) as e:
        pedir([("doce-ind", 1)], agora=sete, horario=OITO_AS_24, entrega_em=sete.replace(hour=8))
    assert e.value.codigo == "agendamento_horario"
