"""Encomendas pagas no painel: produção do dia, alerta de véspera e separação.

Puro: recebe as encomendas pagas já lidas do banco. O dia é o do fuso local.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.dominio.horario import FUSO
from app.regras.config import ALERTA_ENCOMENDA_DIAS_ANTES


@dataclass(frozen=True)
class EncomendaPaga:
    pedido_id: str
    numero: int
    entrega_em: datetime


def _dia(quando: datetime) -> date:
    if quando.tzinfo is None:
        raise ValueError("hora sem fuso")
    return quando.astimezone(FUSO).date()


def producao_do_dia(encomendas: list[EncomendaPaga], dia: date) -> list[EncomendaPaga]:
    """Encomendas para entregar no dia, na ordem do horário."""
    return sorted((e for e in encomendas if _dia(e.entrega_em) == dia), key=lambda e: e.entrega_em)


def alertas_de_vespera(encomendas: list[EncomendaPaga], agora: datetime) -> list[EncomendaPaga]:
    """Encomendas de amanhã, para o operador programar a produção."""
    return producao_do_dia(encomendas, _dia(agora) + timedelta(days=ALERTA_ENCOMENDA_DIAS_ANTES))


class SeparacaoInvalida(ValueError):
    pass


def faltando(pedido: dict[str, int], separado: dict[str, int]) -> dict[str, int]:
    """O que ainda falta separar para a encomenda sair."""
    return {v: q - separado.get(v, 0) for v, q in pedido.items() if q > separado.get(v, 0)}


def conferir_separacao(
    pedido: dict[str, int], separado: dict[str, int], variante: str, quantidade: int
) -> None:
    """Separar para a encomenda só o que ela pede; liberar (quantidade negativa) só o que há."""
    if variante not in pedido:
        raise SeparacaoInvalida("item fora da Encomenda")
    ja = separado.get(variante, 0)
    if quantidade > 0 and ja + quantidade > pedido[variante]:
        raise SeparacaoInvalida(f"a Encomenda pede {pedido[variante]}, já há {ja} separado")
    if quantidade < 0 and -quantidade > ja:
        raise SeparacaoInvalida(f"só há {ja} separado para esta Encomenda")
