"""Configuração das tarifas do gateway, usadas só na taxa estimada dos resumos.

Em pontos-base: 420 = 4,20%. O resto da configuração da loja fica na tabela
`configuracao_loja` nesta versão."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import text

from app.api.auth import Operador, OperadorAtual

router = APIRouter(prefix="/painel/configuracao")


class Tarifas(BaseModel):
    # StrictInt: nada de "4,2", 4.2 nem true virando tarifa
    tarifa_cartao_bps: StrictInt = Field(ge=0, le=10_000)
    tarifa_pix_bps: StrictInt = Field(ge=0, le=10_000)


def _ler(request: Request) -> dict:
    with request.app.state.engine.connect() as c:
        r = c.execute(
            text("SELECT tarifa_cartao_bps, tarifa_pix_bps FROM doce.configuracao_loja")
        ).one()
    return {"tarifa_cartao_bps": r.tarifa_cartao_bps, "tarifa_pix_bps": r.tarifa_pix_bps}


@router.get("")
def obter(request: Request, _: Operador = OperadorAtual) -> dict:
    return _ler(request)


@router.put("")
def salvar(dados: Tarifas, request: Request, _: Operador = OperadorAtual) -> dict:
    with request.app.state.engine.begin() as c:
        c.execute(
            text(
                "UPDATE doce.configuracao_loja SET tarifa_cartao_bps = :c, tarifa_pix_bps = :p"
                " WHERE id = 1"
            ),
            {"c": dados.tarifa_cartao_bps, "p": dados.tarifa_pix_bps},
        )
    return dados.model_dump()
