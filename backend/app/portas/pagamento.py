"""Portas de pagamento.

`ProvedorDePagamento` gera a cobrança do Pix copia e cola (ADR 0004). `GatewayDePagamento`
cria um link de pagamento hospedado e confere pagamentos num gateway de checkout (ADR 0006).
"""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime
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


class GatewayIndisponivel(Exception):
    """Rede, tempo esgotado, resposta fora do formato ou status não 2xx.

    A mensagem nunca leva a chave da API nem o corpo da resposta."""


@dataclass(frozen=True)
class LinkCriado:
    url: str
    resposta: dict = field(default_factory=dict)  # guardada sem dado pessoal


@dataclass(frozen=True)
class Conferencia:
    """Resposta da conferência de um pagamento. `success` ou `paid` falsos são resposta
    válida (não pago), não erro."""

    success: bool
    paid: bool
    amount: int  # centavos cobrados pelo link
    paid_amount: int  # centavos pagos (amount + juros do parcelamento, se houver)
    installments: int
    capture_method: str  # "pix" ou "credit_card"


@runtime_checkable
class GatewayDePagamento(Protocol):
    def criar_link(
        self,
        pedido_id: str,
        numero: int,
        valor_centavos: int,
        valido_ate: datetime,
        redirect_url: str | None,
        webhook_url: str | None,
    ) -> LinkCriado: ...

    def conferir(self, pedido_id: str, transaction_nsu: str, slug: str) -> Conferencia: ...

    def codigo_do_aviso(self, pedido_id: str) -> str: ...


def codigo_do_aviso(segredo: str, pedido_id: str) -> str:
    """Código que vai na URL do aviso: o gateway não assina o webhook, então cada link carrega
    um HMAC do id do pedido. Código errado nem chega a consultar o gateway."""
    return hmac.new(segredo.encode(), pedido_id.encode(), hashlib.sha256).hexdigest()[:32]
