"""Aviso (webhook) do gateway de checkout.

O gateway não assina o aviso: a URL leva um código derivado de um segredo (HMAC sobre o id do
pedido) e, mesmo com o código certo, o corpo nunca é prova. Quem confirma é a conferência.
"""

import hmac
import logging

from fastapi import APIRouter, Request
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.adaptadores import repositorio_pagamentos as pagamentos
from app.api.erros import ErroDeNegocio
from app.api.pagamento_comum import conferir_e_aplicar, gateway_ou_erro, id_do_pedido
from app.dominio.pagamento_online import Resultado

router = APIRouter(prefix="/gateway/checkout")
log = logging.getLogger("doce.pagamento")


def _texto(valor) -> str | None:
    return valor if isinstance(valor, str) and valor.strip() else None


def _processar(request: Request, corpo: dict, codigo: str) -> dict:
    gateway = gateway_ou_erro(request)
    pedido_id = id_do_pedido(corpo.get("order_nsu"))
    nsu, slug = _texto(corpo.get("transaction_nsu")), _texto(corpo.get("invoice_slug"))
    if pedido_id is None or nsu is None or slug is None:
        raise ErroDeNegocio("corpo_invalido", "Aviso fora do formato.", 400)
    if not hmac.compare_digest(codigo.encode(), gateway.codigo_do_aviso(pedido_id).encode()):
        log.warning("aviso com código errado")  # sem corpo no log (dado do cliente)
        raise ErroDeNegocio("codigo_invalido", "Aviso não reconhecido.", 400)
    with request.app.state.engine.begin() as c:
        conhecido = c.execute(
            text("SELECT 1 FROM doce.pedido WHERE id::text = :id"), {"id": pedido_id}
        ).first()
        if conhecido is None:  # código certo para um pedido que não existe: só registra
            agora = request.app.state.relogio()
            pagamentos.registrar(c, None, "aviso", Resultado.NAO_CONFIRMADO, nsu, slug, None, agora)
            return {"resultado": Resultado.NAO_CONFIRMADO.value}
    resultado = conferir_e_aplicar(request, pedido_id, "aviso", nsu, slug)
    return {"resultado": resultado.value}


@router.post("/aviso")
async def aviso(request: Request, c: str = "") -> dict:
    try:
        corpo = await request.json()
    except ValueError:
        corpo = None
    if not isinstance(corpo, dict):
        raise ErroDeNegocio("corpo_invalido", "Aviso fora do formato.", 400)
    return await run_in_threadpool(_processar, request, corpo, c)
