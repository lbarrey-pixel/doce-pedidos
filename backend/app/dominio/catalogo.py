"""Catálogo: produto e variante.

A categoria, a descrição e o preço mudam por tamanho do mesmo produto, então ficam na
variante. O produto só agrupa as variantes de um mesmo sabor. O cardápio entra por CSV
(`backend/dados/cardapio.csv`) e é carregado de forma idempotente no banco.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

_PRECO = re.compile(r"(\d+)(?:\.(\d{1,2}))?")


def centavos_de_texto(texto: str) -> int:
    """'19.90' → 1990, sem ponto flutuante. Recusa vazio, negativo, zero e mais de 2 casas."""
    m = _PRECO.fullmatch(texto.strip())
    if not m:
        raise ValueError(f"preço inválido: {texto!r}")
    centavos = int(m.group(1)) * 100 + int((m.group(2) or "0").ljust(2, "0"))
    if centavos <= 0:
        raise ValueError(f"preço precisa ser positivo: {texto!r}")
    return centavos


@dataclass(frozen=True)
class Variante:
    produto: str
    tamanho: str
    categoria: str
    preco_centavos: int
    peso_g: int | None = None
    porcoes: str = ""
    descricao: str = ""
    ingredientes: str = ""
    observacao: str = ""
    foto: str = ""
    ativa: bool = True
    edicao_limitada: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.preco_centavos, int) or self.preco_centavos <= 0:
            raise ValueError("preco_centavos precisa ser inteiro positivo")
        if not self.produto or not self.categoria:
            raise ValueError("Variante precisa de Produto e Categoria")

    @property
    def chave(self) -> tuple[str, str]:
        return (self.produto, self.tamanho)


@dataclass(frozen=True)
class Catalogo:
    categorias: tuple[str, ...]
    variantes: tuple[Variante, ...]

    @property
    def produtos(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(v.produto for v in self.variantes))

    def variante(self, produto: str, tamanho: str) -> Variante:
        for v in self.variantes:
            if v.chave == (produto, tamanho):
                return v
        raise KeyError((produto, tamanho))


def ler_cardapio(cardapio_csv: Path) -> Catalogo:
    """Lê o CSV do cardápio. A ordem das categorias é a da primeira aparição no arquivo."""
    variantes: list[Variante] = []
    with cardapio_csv.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            observacao = r["observacao"].strip()
            variantes.append(
                Variante(
                    produto=r["produto"].strip(),
                    tamanho=r["tamanho"].strip(),
                    categoria=r["categoria"].strip(),
                    preco_centavos=centavos_de_texto(r["preco"]),
                    peso_g=int(r["peso_g"]) if r["peso_g"].strip() else None,
                    porcoes=r["porcoes"].strip(),
                    descricao=r["descricao"].strip(),
                    ingredientes=r["ingredientes"].strip(),
                    observacao=observacao,
                    foto=r.get("foto", "").strip(),
                    edicao_limitada="edição limitada" in observacao.lower(),
                )
            )
    chaves = [v.chave for v in variantes]
    if len(set(chaves)) != len(chaves):
        raise ValueError("cardápio com Variante repetida (mesmo Produto e tamanho)")
    categorias = tuple(dict.fromkeys(v.categoria for v in variantes))
    return Catalogo(categorias=categorias, variantes=tuple(variantes))
