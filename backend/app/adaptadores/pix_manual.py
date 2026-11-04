"""Pix copia e cola gerado localmente, confirmado pelo operador (ADR 0004)."""

from dataclasses import dataclass

from app.dominio.pix import gerar_copia_e_cola
from app.portas.pagamento import Cobranca, PagamentoNaoConfigurado


@dataclass(frozen=True)
class PixManual:
    chave: str
    nome: str
    cidade: str

    def cobrar(self, numero_pedido: int, valor_centavos: int) -> Cobranca:
        if not self.chave.strip():
            raise PagamentoNaoConfigurado("chave Pix não cadastrada")
        txid = f"DA{numero_pedido}"
        return Cobranca(
            txid=txid,
            copia_e_cola=gerar_copia_e_cola(
                chave=self.chave,
                nome=self.nome,
                cidade=self.cidade,
                valor_centavos=valor_centavos,
                txid=txid,
            ),
        )
