"""Resumo por forma de pagamento: quanto entrou por Pix, cartão e Pix manual, com a taxa
estimada pelas tarifas da configuração."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.adaptadores import repositorio_pedidos as pedidos
from app.api.auth import Operador, OperadorAtual
from app.api.erros import ErroDeNegocio
from app.dominio.horario import FUSO
from app.dominio.pagamento_online import VendaPaga, resumir_por_forma

router = APIRouter(prefix="/painel")


@router.get("/resumos")
def resumos(
    request: Request,
    de: date | None = None,
    ate: date | None = None,
    _: Operador = OperadorAtual,
) -> dict:
    agora = request.app.state.relogio()
    hoje = agora.astimezone(FUSO).date()
    de, ate = de or hoje - timedelta(days=6), ate or hoje
    if ate < de or (ate - de).days > 366:
        raise ErroDeNegocio("periodo_invalido", "Escolha um período de até um ano, em ordem.")
    desde = datetime(de.year, de.month, de.day, tzinfo=FUSO)
    fim = datetime(ate.year, ate.month, ate.day, tzinfo=FUSO) + timedelta(days=1)
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)  # expirado conta como cancelado
        vendas = [
            VendaPaga(r.forma_pagamento, r.estado, r.pago_em, r.total_centavos)
            for r in c.execute(
                text(
                    "SELECT forma_pagamento, estado, pago_em, total_centavos FROM doce.pedido"
                    " WHERE pago_em >= :desde AND pago_em < :ate"
                ),
                {"desde": desde, "ate": fim},
            )
        ]
        tarifas = c.execute(
            text("SELECT tarifa_cartao_bps, tarifa_pix_bps FROM doce.configuracao_loja")
        ).one()
    return {
        "de": de.isoformat(),
        "ate": ate.isoformat(),
        "por_forma": resumir_por_forma(
            vendas,
            de=de,
            ate=ate,
            tarifa_cartao_bps=tarifas.tarifa_cartao_bps,
            tarifa_pix_bps=tarifas.tarifa_pix_bps,
        ),
    }
