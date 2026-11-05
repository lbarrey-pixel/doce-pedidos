"""Gateway de checkout em memória, para demonstração e testes (sem rede, sem conta).

Guarda os links criados e os pagamentos simulados. `pagar` faz o papel do cliente na página do
gateway e devolve o que a URL de volta traria (`transaction_nsu` e `slug`). O estado vive na
instância, atrás de um lock: cada app tem o seu gateway.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.portas.pagamento import Conferencia, GatewayIndisponivel, LinkCriado, codigo_do_aviso


@dataclass
class _Pagamento:
    pedido_id: str
    cobrado: int
    pago: int
    parcelas: int
    metodo: str


class GatewaySimulado:
    def __init__(
        self,
        url_base: str = "https://doceatelie.example/pagar",
        segredo_do_aviso: str = "segredo-do-simulador",
    ) -> None:
        self._url_base = url_base.rstrip("/")
        self._segredo = segredo_do_aviso
        self._trava = threading.Lock()
        self._links: dict[str, int] = {}  # pedido_id -> valor cobrado
        self._pagamentos: dict[str, _Pagamento] = {}  # transaction_nsu -> pagamento
        self.fora_do_ar = False  # testes: simula rede caída

    def codigo_do_aviso(self, pedido_id: str) -> str:
        return codigo_do_aviso(self._segredo, pedido_id)

    def criar_link(
        self,
        pedido_id: str,
        numero: int,
        valor_centavos: int,
        valido_ate: datetime,
        redirect_url: str | None,
        webhook_url: str | None,
    ) -> LinkCriado:
        if self.fora_do_ar:
            raise GatewayIndisponivel("gateway-simulado: fora do ar")
        with self._trava:
            self._links[pedido_id] = valor_centavos
        return LinkCriado(
            url=f"{self._url_base}/{pedido_id}",
            resposta={"simulado": True, "valor": valor_centavos},
        )

    def pagar(
        self,
        pedido_id: str,
        metodo: str = "pix",
        parcelas: int = 1,
        *,
        valor_pago: int | None = None,
        valor_cobrado: int | None = None,
    ) -> tuple[str, str]:
        """O cliente paga o link. Por padrão paga o valor cobrado; no cartão parcelado soma
        juros de 2% por parcela acima da primeira. Devolve (transaction_nsu, slug)."""
        with self._trava:
            cobrado = valor_cobrado if valor_cobrado is not None else self._links[pedido_id]
            if valor_pago is None:
                juros = cobrado * 2 * (parcelas - 1) // 100 if metodo == "credit_card" else 0
                valor_pago = cobrado + juros
            nsu = f"nsu-{uuid.uuid4().hex[:12]}"
            self._pagamentos[nsu] = _Pagamento(pedido_id, cobrado, valor_pago, parcelas, metodo)
        return nsu, f"slug-{nsu[4:]}"

    def conferir(self, pedido_id: str, transaction_nsu: str, slug: str) -> Conferencia:
        if self.fora_do_ar:
            raise GatewayIndisponivel("gateway-simulado: fora do ar")
        with self._trava:
            p = self._pagamentos.get(transaction_nsu)
        if p is None or p.pedido_id != pedido_id or slug != f"slug-{transaction_nsu[4:]}":
            return Conferencia(False, False, 0, 0, 1, "")
        return Conferencia(True, True, p.cobrado, p.pago, p.parcelas, p.metodo)
