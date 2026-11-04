"""Taxa de entrega pela faixa de distância."""

import pytest

from app.dominio.entrega import taxa_de_entrega


@pytest.mark.parametrize(
    ("metros", "taxa"),
    [
        (0, 1000),
        (3000, 1000),
        (3001, 1400),
        (3100, 1400),
        (5000, 1400),
        (6000, 1400),
        (8000, 1700),
        (10000, 2000),
        (12000, 2500),
    ],
)
def test_faixas_ate_inclusivas(metros, taxa):
    assert taxa_de_entrega(metros) == taxa


@pytest.mark.parametrize("metros", [12001, 12100, 13000])
def test_acima_de_12_km_e_sob_consulta(metros):
    assert taxa_de_entrega(metros) is None


def test_distancia_invalida():
    with pytest.raises(ValueError):
        taxa_de_entrega(-1)
