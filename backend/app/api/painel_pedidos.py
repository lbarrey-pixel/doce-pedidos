"""Pedidos no painel: lista, confirmação do Pix e mudança de estado.

A expiração é preguiçosa (ADR 0005): toda rota libera antes os Pedidos vencidos.
"""

import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.adaptadores import repositorio_pagamentos as pagamentos
from app.adaptadores import repositorio_pedidos as pedidos
from app.api.auth import Operador, OperadorAtual
from app.api.erros import ErroDeNegocio
from app.api.pagamento_comum import conferir_e_aplicar
from app.dominio.dinheiro import formatar
from app.dominio.encomenda import SeparacaoInvalida, conferir_separacao, faltando
from app.dominio.estoque import Estado, FaltaEstoque
from app.dominio.horario import FUSO
from app.dominio.pedido import ValorDivergente, confirmar_pagamento
from app.regras import config

router = APIRouter(prefix="/painel/pedidos")

PROXIMOS = {
    "aguardando_pagamento": {"cancelado"},
    "pago": {"em_preparo", "cancelado"},
    "em_preparo": {"saiu", "cancelado"},
    "saiu": {"entregue"},
}


class Confirmacao(BaseModel):
    valor_recebido_centavos: int = Field(ge=0)  # campo a mais é ignorado


class Separacao(BaseModel):
    variante_id: str
    quantidade: int = Field(gt=0, le=1_000)
    origem: Literal["producao", "pronta", "liberar"]


class Entregador(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    telefone: str = Field(default="", max_length=20)


class NovoEstado(BaseModel):
    estado: Literal["em_preparo", "saiu", "entregue", "cancelado"]
    devolucao_centavos: int = Field(default=0, ge=0)
    entregador: Entregador | None = None


def _pedido(c, pedido_id: str):
    p = c.execute(
        text("SELECT * FROM doce.pedido WHERE id::text = :id FOR UPDATE"), {"id": pedido_id}
    ).one_or_none()
    if p is None:
        raise ErroDeNegocio("nao_encontrado", "Pedido não encontrado.", 404)
    return p


def _resumo(p, itens) -> dict:
    return {
        "id": str(p.id),
        "numero": p.numero,
        "canal": p.canal,
        "estado": p.estado,
        "recebimento": p.recebimento,
        "tipo_entrega": p.tipo_entrega,
        "cliente": {k: (p.cliente or {}).get(k) for k in ("nome", "telefone")},
        "endereco": p.endereco,
        "observacao": p.observacao,
        "itens": itens,
        "subtotal_centavos": p.subtotal_centavos,
        "desconto_centavos": p.desconto_centavos,
        "taxa_entrega_centavos": p.taxa_entrega_centavos,
        "total_centavos": p.total_centavos,
        "diferenca_pagamento_centavos": p.diferenca_pagamento_centavos,
        "devolvido_centavos": p.devolvido_centavos,
        "forma_pagamento": p.forma_pagamento,
        "parcelas": p.parcelas,
        "valor_pago_centavos": p.valor_pago_centavos,
        "pago_apos_expirar": p.pago_apos_expirar,
        "pagamento_link": p.pagamento_link,
        # Pedido do app com link de pagamento: confirma só pelo gateway (sem "Recebi R$").
        "paga_pelo_link": bool(getattr(p, "paga_pelo_link", False)),
        "entregador": p.entregador,
        "saiu_em": p.saiu_em.astimezone(FUSO).isoformat() if p.saiu_em else None,
        "entregue_previsto_em": (
            (p.saiu_em + timedelta(minutes=config.TEMPO_ENTREGA_MIN)).astimezone(FUSO).isoformat()
            if p.saiu_em and p.recebimento == "entrega"
            else None
        ),
        "criado_em": p.criado_em.isoformat(),
        "expira_em": p.expira_em.isoformat() if p.expira_em else None,
        "entrega_a_partir_de": (
            p.entrega_a_partir_de.isoformat() if p.entrega_a_partir_de else None
        ),
    }


@router.get("")
def listar(
    request: Request,
    estado: str | None = None,
    dias: int = 7,
    _: Operador = OperadorAtual,
) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        pedidos.marcar_entregues(c, agora)
        linhas = c.execute(
            text(
                "SELECT p.*, EXISTS (SELECT 1 FROM doce.link_pagamento l"
                " WHERE l.pedido_id = p.id) AND p.canal = 'app' AS paga_pelo_link"
                " FROM doce.pedido p WHERE p.criado_em >= :desde"
                " AND (CAST(:estado AS text) IS NULL OR p.estado = :estado)"
                " ORDER BY p.criado_em DESC LIMIT 200"
            ),
            {"desde": agora - timedelta(days=max(1, min(dias, 90))), "estado": estado},
        ).all()
        itens = pedidos.itens_com_nome(c, [str(p.id) for p in linhas])
    return {"pedidos": [_resumo(p, itens.get(str(p.id), [])) for p in linhas]}


@router.post("/{pedido_id}/confirmar-pagamento")
def confirmar(
    pedido_id: str, dados: Confirmacao, request: Request, operador: Operador = OperadorAtual
) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        p = _pedido(c, pedido_id)
        expirado = p.estado == "cancelado" and p.pago_em is None and p.cancelado_em == p.expira_em
        if p.estado != "aguardando_pagamento" and not expirado:
            raise ErroDeNegocio("transicao_invalida", "Esse Pedido não espera pagamento.")
        if (
            p.canal == "app"
            and c.execute(
                text("SELECT 1 FROM doce.link_pagamento WHERE pedido_id = :id LIMIT 1"),
                {"id": p.id},
            ).first()
        ):
            # Confirmar na mão um pedido do link faria o aviso do mesmo pagamento virar
            # "a estornar".
            raise ErroDeNegocio(
                "pagamento_pelo_gateway",
                "Este pedido é pago pelo gateway. Use Conferir pagamento.",
                409,
            )
        try:
            confirmar_pagamento(p.total_centavos, dados.valor_recebido_centavos)
        except ValorDivergente as e:
            raise ErroDeNegocio(
                "valor_divergente",
                "O valor recebido é diferente do total do Pedido.",
                esperado_centavos=e.esperado,
                recebido_centavos=e.recebido,
            ) from e
        if p.tipo_entrega == "pronta_entrega":
            try:  # expirado: a separação já voltou; vende da Pronta entrega se ainda houver
                de = Estado.PRONTA if expirado else Estado.SEPARADA
                pedidos.baixar_venda(c, pedido_id, de, operador.id, agora)
            except FaltaEstoque as e:
                raise ErroDeNegocio(
                    "unidade_indisponivel",
                    "A unidade já foi vendida. Separe outra, ofereça Encomenda ou devolva o Pix.",
                    409,
                ) from e
        c.execute(
            text(
                "UPDATE doce.pedido SET estado = 'pago', pago_em = :agora, cancelado_em = NULL,"
                " confirmado_por = :op, diferenca_pagamento_centavos = 0,"
                " entrega_a_partir_de = :a_partir WHERE id = :id"
            ),
            {
                "agora": agora,
                "op": operador.id,
                "a_partir": pedidos.a_partir_de(p, agora),
                "id": p.id,
            },
        )
    return {"estado": "pago", "diferenca_pagamento_centavos": 0}


@router.post("/{pedido_id}/conferir-pagamento")
def conferir(pedido_id: str, request: Request, _: Operador = OperadorAtual) -> dict:
    """Confere no gateway com o último aviso do pedido. Vale também para pedido cancelado
    ou expirado, que pode ter sido pago depois."""
    with request.app.state.engine.connect() as c:
        aviso = pagamentos.ultimo_aviso(c, pedido_id)
        existe = (
            c.execute(
                text("SELECT 1 FROM doce.pedido WHERE id::text = :id"), {"id": pedido_id}
            ).first()
            is not None
        )
    if not existe:
        raise ErroDeNegocio("nao_encontrado", "Pedido não encontrado.", 404)
    if aviso is None:
        raise ErroDeNegocio(
            "sem_aviso_gateway",
            "Sem aviso do gateway para este pedido: confira no painel do gateway.",
            409,
        )
    resultado = conferir_e_aplicar(request, pedido_id, "painel", *aviso)
    with request.app.state.engine.connect() as c:
        estado = c.execute(
            text("SELECT estado FROM doce.pedido WHERE id::text = :id"), {"id": pedido_id}
        ).scalar_one()
    return {"estado": estado, "resultado": resultado.value}


@router.post("/{pedido_id}/estado")
def mudar_estado(
    pedido_id: str, dados: NovoEstado, request: Request, operador: Operador = OperadorAtual
) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        p = _pedido(c, pedido_id)
        if dados.estado not in PROXIMOS.get(p.estado, set()):
            raise ErroDeNegocio("transicao_invalida", "Esse passo não vale para este Pedido.")
        if p.canal == "balcao":
            if dados.estado == "cancelado":
                # A venda lançada baixou a pronta entrega; cancelada, volta. Venda já cancelada
                # (inclusive por link expirado) cai na transição inválida acima: o estoque
                # nunca volta duas vezes.
                pedidos.devolver_ao_estoque(c, pedido_id, p.numero, operador.id, agora)
        elif p.tipo_entrega == "encomenda":
            _encomenda_muda_de_estado(c, p, dados.estado, operador.id, agora)
        elif dados.estado == "cancelado" and p.tipo_entrega == "pronta_entrega":
            if p.estado == "aguardando_pagamento":
                pedidos.liberar_separacao(c, pedido_id, operador.id, agora)
            elif p.canal == "app":  # pago e ainda não saiu: volta ao estoque
                pedidos.devolver_ao_estoque(c, pedido_id, p.numero, operador.id, agora)
        final = dados.estado
        entregador = None
        if dados.estado == "saiu":
            if p.recebimento == "retirada":
                final = "entregue"  # o cliente retirou: não há trajeto
            elif dados.entregador:
                entregador = pedidos.guardar_entregador(
                    c, dados.entregador.nome, dados.entregador.telefone
                )
        c.execute(
            text(
                "UPDATE doce.pedido SET estado = :e,"
                " cancelado_em = CASE WHEN :e = 'cancelado' THEN :agora ELSE cancelado_em END,"
                " cancelado_por = CASE WHEN :e = 'cancelado' THEN :op ELSE cancelado_por END,"
                " saiu_em = CASE WHEN :saiu THEN :agora ELSE saiu_em END,"
                " entregue_em = CASE WHEN :e = 'entregue' THEN :agora ELSE entregue_em END,"
                " entregador = coalesce(CAST(:entregador AS jsonb), entregador),"
                " devolvido_centavos = devolvido_centavos + :dev WHERE id = :id"
            ),
            {
                "e": final,
                "agora": agora,
                "op": operador.id,
                "saiu": dados.estado == "saiu",
                "entregador": json.dumps(entregador, ensure_ascii=False) if entregador else None,
                "dev": dados.devolucao_centavos if dados.estado == "cancelado" else 0,
                "id": p.id,
            },
        )
    resposta: dict = {"estado": final}
    if dados.estado == "cancelado" and p.forma_pagamento in ("pix", "cartao"):
        # Pago pelo gateway: o sistema não estorna sozinho; avisa o valor que entrou.
        valor = p.valor_pago_centavos or p.total_centavos
        resposta["estorno"] = {
            "valor_centavos": valor,
            "mensagem": f"Faça o estorno de {formatar(valor)} no painel do gateway.",
        }
    return resposta


def _itens(c, pedido_id: str) -> dict[str, int]:
    return dict(pedidos.itens_do_pedido(c, pedido_id))


def _encomenda_muda_de_estado(c, p, novo: str, autor: str, agora) -> None:
    """Encomenda: baixa da separação ao sair; cancelada, a separação volta à Pronta entrega."""
    pid = str(p.id)
    separado = pedidos.separados(c, pid)
    if novo == "saiu":
        falta = faltando(_itens(c, pid), separado)
        if falta:
            raise ErroDeNegocio(
                "encomenda_sem_separacao",
                "Lance a produção desta Encomenda antes de ela sair.",
                faltando=[{"variante_id": v, "quantidade": q} for v, q in falta.items()],
            )
        pedidos.baixar_venda(c, pid, Estado.SEPARADA, autor, agora)
    elif novo == "cancelado":
        for variante, qtd in separado.items():
            pedidos.separar_para_encomenda(c, pid, variante, qtd, "liberar", autor, agora)


@router.post("/{pedido_id}/separacao")
def separacao(
    pedido_id: str, dados: Separacao, request: Request, operador: Operador = OperadorAtual
) -> dict:
    """Produção "para a Encomenda nº X", uso da Pronta entrega ou desfazer."""
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        p = _pedido(c, pedido_id)
        if p.tipo_entrega != "encomenda" or p.estado not in ("pago", "em_preparo"):
            raise ErroDeNegocio("transicao_invalida", "Só Encomenda paga e ainda não saída.")
        separado = pedidos.separados(c, pedido_id)
        sinal = -1 if dados.origem == "liberar" else 1
        try:
            conferir_separacao(
                _itens(c, pedido_id), separado, dados.variante_id, sinal * dados.quantidade
            )
            pedidos.separar_para_encomenda(
                c, pedido_id, dados.variante_id, dados.quantidade, dados.origem, operador.id, agora
            )
        except SeparacaoInvalida as e:
            raise ErroDeNegocio("separacao_invalida", str(e).capitalize() + ".") from e
        except ValueError as e:  # movimento que não serve ao controle de estoque da Variante
            raise ErroDeNegocio("movimento_invalido", "Esse lançamento não serve aqui.") from e
        except FaltaEstoque as e:
            raise ErroDeNegocio(
                "falta_estoque", f"Só há {e.disponivel} na pronta entrega.", disponivel=e.disponivel
            ) from e
        return {"separado": pedidos.separados(c, pedido_id)}
