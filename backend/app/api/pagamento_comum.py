"""O que as rotas de pagamento têm em comum: conferir com o gateway fora do banco e depois
aplicar o resultado no pedido.

A conferência acontece antes de travar o pedido: a rede nunca segura trava de banco.
"""

import uuid

from fastapi import Request
from sqlalchemy import text

from app.adaptadores import repositorio_pagamentos as pagamentos
from app.api.erros import ErroDeNegocio
from app.dominio.pagamento_online import Resultado
from app.portas.pagamento import GatewayDePagamento, GatewayIndisponivel


def gateway_ou_erro(request: Request) -> GatewayDePagamento:
    gateway = request.app.state.gateway
    if gateway is None:
        raise ErroDeNegocio(
            "pagamento_indisponivel", "O pagamento online não está ligado agora.", 503
        )
    return gateway


def id_do_pedido(valor: object) -> str | None:
    """O id do pedido como o banco o escreve, ou None se não for um uuid."""
    try:
        return str(uuid.UUID(valor))  # type: ignore[arg-type]
    except (ValueError, AttributeError, TypeError):
        return None


def conferir_e_aplicar(
    request: Request, pedido_id: str, origem: str, nsu: str, slug: str, *, so_app: bool = False
) -> Resultado:
    gateway = gateway_ou_erro(request)
    with request.app.state.engine.connect() as c:
        achado = c.execute(
            text("SELECT canal FROM doce.pedido WHERE id::text = :id"), {"id": pedido_id}
        ).one_or_none()
    if achado is None or (so_app and achado.canal != "app"):
        raise ErroDeNegocio("nao_encontrado", "Pedido não encontrado.", 404)
    try:
        conf = gateway.conferir(pedido_id, nsu, slug)
    except GatewayIndisponivel as e:
        raise ErroDeNegocio(
            "gateway_indisponivel", "Não deu para conferir o pagamento agora. Tente de novo.", 503
        ) from e
    with request.app.state.engine.begin() as c:
        return pagamentos.aplicar(
            c, pedido_id, origem, nsu, slug, conf, request.app.state.relogio()
        )


def url_do_aviso(request: Request, gateway: GatewayDePagamento, pedido_id: str) -> str | None:
    """URL do webhook com o código do pedido; sem URL pública da API, sem webhook."""
    base = request.app.state.url_externa
    if not base:
        return None
    return f"{base}/api/v1/gateway/checkout/aviso?c={gateway.codigo_do_aviso(pedido_id)}"


def url_de_volta(request: Request, pedido_id: str) -> str | None:
    """Volta ao app: a origem do pedido, se estiver em CORS_ORIGENS; senão a primeira delas."""
    origens = request.app.state.origens
    origem = request.headers.get("origin", "").strip().rstrip("/")
    if origem not in origens:
        origem = origens[0] if origens else ""
    return f"{origem}/pedido/{pedido_id}" if origem else None
