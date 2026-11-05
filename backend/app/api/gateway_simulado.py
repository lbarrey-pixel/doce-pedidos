"""Página de pagamento de mentira, só para demonstração: só existe quando o gateway em uso é o
simulado (`GATEWAY=simulado`). O front chama esta rota no lugar do cliente pagando no gateway."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.erros import ErroDeNegocio
from app.api.pagamento_comum import conferir_e_aplicar, id_do_pedido

router = APIRouter(prefix="/gateway/simulado")


class Pagar(BaseModel):
    pedido_id: str
    metodo: Literal["pix", "credit_card"] = "pix"
    parcelas: int = Field(default=1, ge=1, le=12)
    avisar: bool = False  # true: dispara também o aviso, como o gateway faria


def _pagar(request: Request, dados: Pagar) -> dict:
    pedido_id = id_do_pedido(dados.pedido_id)
    gateway = request.app.state.gateway
    if pedido_id is None:
        raise ErroDeNegocio("nao_encontrado", "Pedido não encontrado.", 404)
    try:
        nsu, slug = gateway.pagar(pedido_id, dados.metodo, dados.parcelas)
    except KeyError as e:  # nenhum link foi criado para este pedido
        raise ErroDeNegocio("nao_encontrado", "Link de pagamento não encontrado.", 404) from e
    resposta: dict = {"transaction_nsu": nsu, "slug": slug}
    if dados.avisar:
        resposta["resultado"] = conferir_e_aplicar(request, pedido_id, "aviso", nsu, slug).value
    return resposta


@router.post("/pagar")
async def pagar(dados: Pagar, request: Request) -> dict:
    return await run_in_threadpool(_pagar, request, dados)
