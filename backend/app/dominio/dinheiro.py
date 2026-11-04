"""Dinheiro em centavos inteiros; nunca ponto flutuante."""

from app.regras import config


def _inteiro(nome: str, valor: object) -> int:
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise ValueError(f"{nome} precisa ser inteiro: {valor!r}")
    return valor


def formatar(centavos: int) -> str:
    """5380 → 'R$ 53,80'; negativo com sinal de menos tipográfico."""
    _inteiro("centavos", centavos)
    absoluto = abs(centavos)
    reais = f"{absoluto // 100:,}".replace(",", ".")
    texto = f"R$ {reais},{absoluto % 100:02d}"
    return f"−{texto}" if centavos < 0 else texto


def percentual(base_centavos: int, pct: int) -> int:
    """Percentual inteiro de 0 a 100 sobre a base, arredondado para baixo no centavo."""
    _inteiro("base", base_centavos)
    _inteiro("percentual", pct)
    if base_centavos < 0 or not 0 <= pct <= 100:
        raise ValueError("base não negativa e percentual entre 0 e 100")
    if not config.DESCONTO_ARREDONDA_PARA_BAIXO:  # pragma: no cover
        return (base_centavos * pct + 50) // 100
    return base_centavos * pct // 100
