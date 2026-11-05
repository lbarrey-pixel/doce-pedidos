"""Pagamentos que pedem decisão do operador: a estornar, a decidir e valor recusado. O sistema
registra e avisa; quem estorna ou decide é o operador."""

from fastapi import APIRouter, Request

from app.adaptadores import repositorio_pagamentos as pagamentos
from app.api.auth import Operador, OperadorAtual
from app.api.erros import ErroDeNegocio

router = APIRouter(prefix="/painel/pagamentos")


@router.get("/pendencias")
def pendencias(request: Request, _: Operador = OperadorAtual) -> dict:
    with request.app.state.engine.connect() as c:
        return {"pendencias": pagamentos.pendencias(c)}


@router.post("/pendencias/{confirmacao_id}/resolver")
def resolver(confirmacao_id: int, request: Request, operador: Operador = OperadorAtual) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        if not pagamentos.resolver(c, confirmacao_id, operador.id, agora):
            raise ErroDeNegocio("nao_encontrado", "Pendência não encontrada.", 404)
    return {"resolvido": True}
