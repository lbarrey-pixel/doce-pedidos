"""Taxa de entrega pela faixa de distância. Metros e centavos inteiros."""

from app.regras.config import FAIXAS_DISTANCIA


def taxa_de_entrega(metros: int, faixas=FAIXAS_DISTANCIA) -> int | None:
    """Taxa da primeira faixa cujo limite "até" (inclusivo) cobre a distância.

    None = acima do último limite: a entrega é combinada à parte.
    """
    if not isinstance(metros, int) or metros < 0:
        raise ValueError(f"distância inválida: {metros!r}")
    for ate, taxa in faixas:
        if metros <= ate:
            return taxa
    return None
