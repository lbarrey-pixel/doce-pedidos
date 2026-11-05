"""Vendas lançadas no painel (balcão, WhatsApp, Instagram) e o link de pagamento delas.

A venda nasce paga e baixa a pronta entrega na hora. O link só liga um pagamento do gateway a
ela, com a mesma conferência do app: pago no prazo, a venda segue; vencido o prazo sem
pagamento, a venda é cancelada e o estoque volta.
"""

from datetime import timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.adaptadores import repositorio_pagamentos as pagamentos
from app.adaptadores import repositorio_pedidos as pedidos
from app.api.auth import Operador, OperadorAtual
from app.api.erros import ErroDeNegocio
from app.api.pagamento_comum import gateway_ou_erro, url_do_aviso
from app.dominio.dinheiro import formatar
from app.dominio.estoque import FaltaEstoque
from app.dominio.mensagem import url_whatsapp
from app.portas.pagamento import GatewayIndisponivel

router = APIRouter(prefix="/painel/vendas")
VALIDADE_DO_LINK_MIN = 30


class ItemVenda(BaseModel):
    variante_id: str
    quantidade: int = Field(gt=0, le=50)


class NovaVenda(BaseModel):
    itens: list[ItemVenda] = Field(min_length=1, max_length=50)


@router.post("")
def lancar(nova: NovaVenda, request: Request, operador: Operador = OperadorAtual) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)  # o que um link vencido devolve entra no saldo
        precos = {
            str(r.id): r.preco_centavos
            for r in c.execute(
                text("SELECT id, preco_centavos FROM doce.variante WHERE id::text = ANY(:ids)"),
                {"ids": [i.variante_id for i in nova.itens]},
            )
        }
        desconhecida = next((i for i in nova.itens if i.variante_id not in precos), None)
        if desconhecida:
            raise ErroDeNegocio(
                "variante_desconhecida",
                "Item fora do cardápio.",
                variante_id=desconhecida.variante_id,
            )
        itens = [(i.variante_id, i.quantidade, precos[i.variante_id]) for i in nova.itens]
        try:
            pid, numero, total = pedidos.lancar_venda_balcao(c, itens, operador.id, agora)
        except FaltaEstoque as e:  # a exceção desfaz a transação inteira
            raise ErroDeNegocio(
                "falta_estoque",
                f"Só há {e.disponivel} na pronta entrega.",
                disponivel=e.disponivel,
            ) from e
    return {"id": pid, "numero": numero, "total_centavos": total}


def _link_da_venda(url: str, total_centavos: int) -> dict:
    texto = (
        f"Olá! Segue o link para pagar o seu pedido na Doce Ateliê "
        f"({formatar(total_centavos)}): {url}"
    )
    return {"url": url, "whatsapp_url": url_whatsapp("", texto)}


@router.post("/{pedido_id}/link")
def gerar_link(pedido_id: str, request: Request, _: Operador = OperadorAtual) -> dict:
    """Pedir de novo com o link vivo devolve o mesmo link."""
    gateway = gateway_ou_erro(request)
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)  # link vencido vira "expirado"
        p = c.execute(
            text("SELECT * FROM doce.pedido WHERE id::text = :id FOR UPDATE"), {"id": pedido_id}
        ).one_or_none()
        if p is None:
            raise ErroDeNegocio("nao_encontrado", "Venda não encontrada.", 404)
        if p.canal != "balcao":
            raise ErroDeNegocio("canal_sem_link", "Só vendas lançadas no painel têm esse link.")
        if p.estado == "cancelado":
            raise ErroDeNegocio("transicao_invalida", "Essa venda foi cancelada.", 409)
        if p.pagamento_link == "pago":
            raise ErroDeNegocio("link_ja_pago", "Essa venda já foi paga pelo link.", 409)
        if p.total_centavos <= 0:
            raise ErroDeNegocio("valor_invalido", "A venda não tem valor a cobrar.")
        if p.pagamento_link == "aguardando":
            vivo = pagamentos.link_do_pedido(c, pedido_id)
            return _link_da_venda(vivo.url, p.total_centavos)
        valido_ate = agora + timedelta(minutes=VALIDADE_DO_LINK_MIN)
        try:
            link = gateway.criar_link(
                str(p.id),
                p.numero,
                p.total_centavos,
                valido_ate,
                None,  # quem paga pelo WhatsApp não tem página no app para voltar
                url_do_aviso(request, gateway, str(p.id)),
            )
        except GatewayIndisponivel as e:
            raise ErroDeNegocio(
                "gateway_indisponivel", "Não deu para gerar o link agora. Tente de novo.", 503
            ) from e
        pagamentos.criar_link(
            c, str(p.id), link.url, p.total_centavos, valido_ate, link.resposta, agora
        )
        c.execute(
            text("UPDATE doce.pedido SET pagamento_link = 'aguardando' WHERE id = :id"),
            {"id": p.id},
        )
    return _link_da_venda(link.url, p.total_centavos)
