"""Gateway de checkout por HTTP (ADR 0006; contrato em docs/contracts/gateway-checkout.md).

Cria o link de pagamento e confere o pagamento. A chave da API vai só no cabeçalho
`Authorization`: nunca em log, em mensagem de erro, em `repr` ou em exceção encadeada. Erro de
rede, tempo esgotado, status que não seja 2xx ou resposta fora do formato viram
`GatewayIndisponivel`.
"""

from datetime import datetime

import httpx

from app.dominio.horario import FUSO
from app.portas.pagamento import Conferencia, GatewayIndisponivel, LinkCriado, codigo_do_aviso

TEMPO_LIMITE_S = 8
EVENTOS = ["paid", "canceled", "refunded"]


def _motivo(servico: str, e: httpx.HTTPError) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"{servico}: HTTP {e.response.status_code}"
    return f"{servico}: {type(e).__name__}"  # só o tipo: a mensagem do httpx pode ecoar cabeçalho


def _inteiro(valor) -> int:
    """Centavos: só inteiro de verdade (ou decimal sem fração). Outra coisa não confirma nada."""
    if isinstance(valor, bool):
        return 0
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return 0


class GatewayCheckout:
    def __init__(
        self,
        url_base: str,
        chave: str,
        segredo_do_aviso: str,
        cliente: httpx.Client | None = None,
    ) -> None:
        if not segredo_do_aviso:
            raise ValueError("segredo_do_aviso é obrigatório e deve ser diferente da chave")
        self._base = url_base.rstrip("/")
        self._chave = chave
        self._segredo = segredo_do_aviso
        self._http = cliente or httpx.Client(timeout=TEMPO_LIMITE_S)

    def __repr__(self) -> str:
        return f"GatewayCheckout(url_base={self._base!r}, chave=***)"

    def codigo_do_aviso(self, pedido_id: str) -> str:
        return codigo_do_aviso(self._segredo, pedido_id)

    def _post(self, caminho: str, corpo: dict, servico: str) -> dict:
        try:
            r = self._http.post(
                f"{self._base}{caminho}",
                headers={"Authorization": f"Bearer {self._chave}"},
                json=corpo,
                timeout=TEMPO_LIMITE_S,
            )
            r.raise_for_status()
            dados = r.json()
        except httpx.HTTPError as e:
            raise GatewayIndisponivel(_motivo(servico, e)) from None
        except ValueError:
            raise GatewayIndisponivel(f"{servico}: resposta que não é JSON") from None
        if not isinstance(dados, dict):
            raise GatewayIndisponivel(f"{servico}: resposta fora do formato")
        return dados

    def criar_link(
        self,
        pedido_id: str,
        numero: int,
        valor_centavos: int,
        valido_ate: datetime,
        redirect_url: str | None,
        webhook_url: str | None,
    ) -> LinkCriado:
        corpo: dict = {
            "order_nsu": pedido_id,
            # Um item só com o total: evita diferença de arredondamento entre itens, desconto
            # e taxa de entrega. Sem nome nem endereço do cliente.
            "items": [
                {
                    "quantity": 1,
                    "price": valor_centavos,
                    "description": f"Pedido nº {numero} · Doce Ateliê",
                }
            ],
        }
        if redirect_url:
            corpo["redirect_url"] = redirect_url
        if webhook_url:
            corpo["webhook"] = {"url": webhook_url, "events": EVENTOS}
        corpo["options"] = {
            "single_payment": True,
            "valid_until": valido_ate.astimezone(FUSO).isoformat(),
            "payment_methods_enabled": ["credit_card", "pix"],
            "assured_installments": 0,  # juros do parcelamento por conta do cliente
        }
        dados = self._post("/links", corpo, "gateway-links")
        url = dados.get("url") or dados.get("link")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise GatewayIndisponivel("gateway-links: resposta sem URL de pagamento")
        return LinkCriado(url=url, resposta=dados)

    def conferir(self, pedido_id: str, transaction_nsu: str, slug: str) -> Conferencia:
        dados = self._post(
            "/payments/check",
            {"order_nsu": pedido_id, "transaction_nsu": transaction_nsu, "slug": slug},
            "gateway-conferencia",
        )
        parcelas = _inteiro(dados.get("installments"))
        metodo = dados.get("capture_method")
        return Conferencia(
            success=dados.get("success") is True,
            paid=dados.get("paid") is True,
            amount=_inteiro(dados.get("amount")),
            paid_amount=_inteiro(dados.get("paid_amount")),
            installments=parcelas if parcelas >= 1 else 1,
            capture_method=metodo if isinstance(metodo, str) else "",
        )
