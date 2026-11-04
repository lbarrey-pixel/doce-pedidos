"""Porta ProvedorDePagamento. Hoje só existe o adaptador pix_manual (ADR 0004)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Cobranca:
    txid: str
    copia_e_cola: str


class PagamentoNaoConfigurado(Exception):
    """A loja ainda não cadastrou os dados que o provedor precisa (ex.: chave Pix)."""


@runtime_checkable
class ProvedorDePagamento(Protocol):
    def cobrar(self, numero_pedido: int, valor_centavos: int) -> Cobranca: ...


class FabricaDePagamento(Protocol):
    """Monta o provedor com a configuração da loja lida do banco a cada pedido."""

    def __call__(self, chave: str, nome: str, cidade: str) -> ProvedorDePagamento: ...
