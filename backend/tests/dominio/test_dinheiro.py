"""Dinheiro em centavos inteiros."""

import pytest

from app.dominio.dinheiro import formatar, percentual


@pytest.mark.parametrize(
    ("centavos", "texto"),
    [
        (5380, "R$ 53,80"),
        (10, "R$ 0,10"),
        (0, "R$ 0,00"),
        (123456, "R$ 1.234,56"),
        (-1058, "−R$ 10,58"),
    ],
)
def test_formatar(centavos, texto):
    assert formatar(centavos) == texto


@pytest.mark.parametrize(
    ("base", "pct", "esperado"),
    [
        (10580, 10, 1058),
        (1790, 10, 179),
        (1990, 15, 298),  # 298,5 arredonda para baixo
        (1, 99, 0),
        (5290, 0, 0),
        (5290, 100, 5290),
    ],
)
def test_percentual_arredonda_para_baixo(base, pct, esperado):
    assert percentual(base, pct) == esperado


@pytest.mark.parametrize(
    ("base", "pct"), [(1.5, 10), (100, -1), (100, 101), (-100, 10), (100, 10.5)]
)
def test_percentual_recusa_entrada_invalida(base, pct):
    with pytest.raises(ValueError):
        percentual(base, pct)


def test_formatar_recusa_float():
    with pytest.raises(ValueError):
        formatar(53.8)
