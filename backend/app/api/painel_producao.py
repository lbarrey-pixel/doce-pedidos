"""Produção do dia e alertas de véspera das Encomendas.

Lê as Encomendas pagas do banco e deixa a regra do dia para `dominio.encomenda`.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import Connection, text

from app.adaptadores import repositorio_pedidos as pedidos
from app.api.auth import Operador, OperadorAtual
from app.dominio.encomenda import EncomendaPaga, alertas_de_vespera, producao_do_dia
from app.dominio.horario import FUSO
from app.regras.config import ALERTA_ENCOMENDA_DIAS_ANTES

router = APIRouter(prefix="/painel")

# Encomenda "paga" para a produção: confirmada e ainda não cancelada (S5, edge cases).
ESTADOS_DA_PRODUCAO = ("pago", "em_preparo", "saiu", "entregue")
ESTADOS_DO_ALERTA = ("pago", "em_preparo")


def _encomendas(c: Connection, desde: datetime, ate: datetime, estados) -> dict[str, object]:
    return {
        str(r.id): r
        for r in c.execute(
            text(
                "SELECT id, numero, estado, recebimento, cliente, endereco, observacao,"
                " entrega_a_partir_de, total_centavos FROM doce.pedido"
                " WHERE tipo_entrega = 'encomenda'"
                " AND estado = ANY(:estados) AND entrega_a_partir_de >= :desde"
                " AND entrega_a_partir_de < :ate"
            ),
            {"estados": list(estados), "desde": desde, "ate": ate},
        )
    }


def _janela(dia: date) -> tuple[datetime, datetime]:
    inicio = datetime(dia.year, dia.month, dia.day, tzinfo=FUSO)
    return inicio, inicio + timedelta(days=1)


def _lista(c: Connection, escolhidas: list[EncomendaPaga], linhas: dict) -> list[dict]:
    itens = pedidos.itens_com_nome(c, [e.pedido_id for e in escolhidas])
    saida = []
    for e in escolhidas:
        p = linhas[e.pedido_id]
        separado = pedidos.separados(c, e.pedido_id)
        for i in itens.get(e.pedido_id, []):
            i["separado"] = separado.get(i["variante_id"], 0)
        saida.append(
            {
                "id": e.pedido_id,
                "numero": e.numero,
                "estado": p.estado,
                "recebimento": p.recebimento,
                "entrega_em": e.entrega_em.astimezone(FUSO).isoformat(),
                "cliente": {k: (p.cliente or {}).get(k) for k in ("nome", "telefone")},
                "endereco": p.endereco,
                "observacao": p.observacao,
                "itens": itens.get(e.pedido_id, []),
                "total_centavos": p.total_centavos,
            }
        )
    return saida


def _pagas(linhas: dict) -> list[EncomendaPaga]:
    return [EncomendaPaga(i, r.numero, r.entrega_a_partir_de) for i, r in linhas.items()]


@router.get("/producao")
def producao(request: Request, dia: date | None = None, _: Operador = OperadorAtual) -> dict:
    agora = request.app.state.relogio()
    dia = dia or agora.astimezone(FUSO).date()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        linhas = _encomendas(c, *_janela(dia), ESTADOS_DA_PRODUCAO)
        escolhidas = producao_do_dia(_pagas(linhas), dia)
        return {"dia": dia.isoformat(), "encomendas": _lista(c, escolhidas, linhas)}


@router.get("/alertas")
def alertas(request: Request, _: Operador = OperadorAtual) -> dict:
    agora = request.app.state.relogio()
    amanha = agora.astimezone(FUSO).date() + timedelta(days=ALERTA_ENCOMENDA_DIAS_ANTES)
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        linhas = _encomendas(c, *_janela(amanha), ESTADOS_DO_ALERTA)
        escolhidas = alertas_de_vespera(_pagas(linhas), agora)
        sem_pix = _encomendas(c, *_janela(amanha), ("aguardando_pagamento",))
        pendentes = alertas_de_vespera(_pagas(sem_pix), agora)
        return {
            "amanha": amanha.isoformat(),
            "encomendas": _lista(c, escolhidas, linhas),
            "aguardando_pagamento": _lista(c, pendentes, sem_pix),  # já separadas no estoque
        }
