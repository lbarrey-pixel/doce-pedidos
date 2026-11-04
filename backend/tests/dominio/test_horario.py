"""Horário da loja e antecedência da Encomenda."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.dominio.horario import (
    HORARIO_PADRAO,
    Horario,
    abre_as,
    agendamento_valido,
    encomenda_valida,
    loja_aberta,
    primeira_encomenda,
    primeiro_agendamento,
)

FUSO = ZoneInfo("America/Sao_Paulo")


def h(dia, hora, minuto=0):
    return datetime(2026, 11, dia, hora, minuto, tzinfo=FUSO)


@pytest.mark.parametrize(
    ("quando", "aberta"),
    [
        (h(2, 11, 59), False),
        (h(2, 12, 0), True),
        (h(2, 23, 59), True),
        (h(3, 0, 0), False),
        (h(3, 0, 30), False),
    ],
)
def test_loja_aberta_das_12h_as_24h(quando, aberta):
    assert loja_aberta(quando) is aberta


def test_quando_abre():
    assert abre_as(h(3, 0, 30)) == h(3, 12, 0)
    assert abre_as(h(2, 13, 0)) == h(3, 12, 0)


@pytest.mark.parametrize(
    ("agora", "primeira"),
    [
        (h(2, 18, 0), h(3, 12, 0)),  # 18h + 12 h = 6h, loja fechada → amanhã 12h
        (h(3, 0, 30), h(3, 12, 30)),  # loja fechada aceita Encomenda; hoje 12h30
        (h(2, 15, 0), h(3, 12, 0)),  # 3.2: 15h + 12 h = 3h → amanhã 12h
        (h(2, 9, 10), h(2, 21, 30)),  # meia em meia hora, para cima
    ],
)
def test_primeira_encomenda(agora, primeira):
    assert primeira_encomenda(agora) == primeira


def test_encomenda_antes_de_12_h_ou_fora_do_horario_e_recusada():
    agora = h(2, 15, 0)
    assert not encomenda_valida(agora, h(2, 21, 0))  # daqui 6 h
    assert not encomenda_valida(agora, h(3, 3, 0))  # loja fechada
    assert encomenda_valida(agora, h(3, 12, 0))


def test_encomenda_sem_prazo_maximo():
    assert encomenda_valida(h(2, 15, 0), h(30, 15, 0).replace(month=12, day=17))


# Horário de abertura e fechamento configurável.
ONZE_AS_VINTE = Horario(time(11, 0), time(20, 0))


def test_fechamento_editavel_fecha_antes_da_meia_noite():
    assert loja_aberta(h(2, 19, 59), ONZE_AS_VINTE)
    assert not loja_aberta(h(2, 20, 0), ONZE_AS_VINTE)
    assert loja_aberta(h(2, 11, 0), ONZE_AS_VINTE)
    assert abre_as(h(2, 21, 0), ONZE_AS_VINTE) == h(3, 11, 0)
    assert abre_as(h(3, 9, 0), ONZE_AS_VINTE) == h(3, 11, 0)


def test_primeira_encomenda_depois_do_fechamento_vai_para_a_abertura_seguinte():
    # 10h + 12 h = 22h, depois do fechamento das 20h: amanhã às 11h, nunca hoje de manhã.
    assert primeira_encomenda(h(2, 10, 0), ONZE_AS_VINTE) == h(3, 11, 0)
    # 3h + 12 h = 15h, dentro do horário.
    assert primeira_encomenda(h(2, 3, 0), ONZE_AS_VINTE) == h(2, 15, 0)
    assert encomenda_valida(h(2, 3, 0), h(2, 19, 30), ONZE_AS_VINTE)
    assert not encomenda_valida(h(2, 3, 0), h(2, 20, 0), ONZE_AS_VINTE)


def test_padrao_continua_12h_as_24h():
    assert Horario(time(12, 0), time(0, 0)) == HORARIO_PADRAO
    assert loja_aberta(h(2, 23, 59), HORARIO_PADRAO) and not loja_aberta(h(3, 0, 0), HORARIO_PADRAO)


# Pronta entrega agendada: hoje, de meia em meia hora, a partir de agora + Tempo de preparo.
OITO_AS_24 = Horario(time(8, 0), time(0, 0))


@pytest.mark.parametrize(
    ("agora", "preparo", "primeiro"),
    [
        (h(2, 8, 40), 30, h(2, 9, 30)),
        (h(2, 8, 40), 60, h(2, 10, 0)),
        (h(2, 9, 0), 30, h(2, 9, 30)),  # já cai na meia hora
        (h(2, 23, 0), 30, h(2, 23, 30)),
        (h(2, 23, 10), 30, None),  # 23h40 → meia-noite: fechado, nada hoje
        (h(2, 7, 0), 30, h(2, 8, 30)),  # antes de abrir: abertura + Tempo de preparo (2.15)
        (h(2, 0, 30), 60, h(2, 9, 0)),  # madrugada: abre hoje às 8h
    ],
)
def test_primeiro_agendamento_de_hoje(agora, preparo, primeiro):
    assert primeiro_agendamento(agora, OITO_AS_24, preparo) == primeiro


def test_depois_de_fechar_nao_agenda_para_hoje():
    ate_as_22 = Horario(time(8, 0), time(22, 0))
    assert primeiro_agendamento(h(2, 22, 30), ate_as_22, 30) is None  # abre só amanhã


@pytest.mark.parametrize(
    ("entrega", "valido"),
    [
        (h(2, 9, 30), True),
        (h(2, 12, 0), True),
        (h(2, 23, 30), True),
        (h(2, 9, 0), False),  # antes de agora + Tempo de preparo
        (h(2, 12, 15), False),  # fora da meia hora
        (h(3, 12, 0), False),  # outro dia é Encomenda
    ],
)
def test_agendamento_valido(entrega, valido):
    assert agendamento_valido(h(2, 8, 40), entrega, OITO_AS_24, 30) is valido
