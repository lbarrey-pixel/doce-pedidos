"""Pagamento online no banco: link de pagamento, confirmações e a aplicação do resultado no
pedido, com idempotência.

Toda confirmação passa por `aplicar`: trava o pedido (FOR UPDATE), pede o veredito à regra pura
`dominio.pagamento_online.decidir` e só então mexe no pedido e no estoque, na mesma transação.
O índice único parcial por `transaction_nsu` é a segunda trava: o mesmo pagamento nunca baixa
o estoque duas vezes, nem com aviso e volta ao app chegando juntos.
"""

import json
from datetime import datetime

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.adaptadores import repositorio_pedidos as pedidos
from app.dominio.estoque import Estado, FaltaEstoque
from app.dominio.pagamento_online import (
    Resultado,
    Situacao,
    decidir,
    forma_do_pagamento,
)
from app.portas.pagamento import Conferencia

AUTOR = "gateway"  # autor dos movimentos de estoque feitos pela confirmação automática
# Resultados que "gastam" o transaction_nsu: repetir o aviso não repete o efeito nem a pendência.
GASTAM_O_NSU = (
    Resultado.CONFIRMADO,
    Resultado.PAGO_DEPOIS_DE_EXPIRAR,
    Resultado.A_ESTORNAR,
    Resultado.A_DECIDIR,
)
PENDENTES = (Resultado.A_ESTORNAR, Resultado.A_DECIDIR, Resultado.VALOR_RECUSADO)


def criar_link(
    c: Connection,
    pedido_id: str,
    url: str,
    valor_centavos: int,
    valido_ate: datetime,
    resposta: dict,
    agora: datetime,
) -> None:
    c.execute(
        text(
            "INSERT INTO doce.link_pagamento (pedido_id, url, valor_centavos, valido_ate,"
            " criado_em, resposta) VALUES (:p, :url, :v, :ate, :agora, CAST(:r AS jsonb))"
        ),
        {
            "p": pedido_id,
            "url": url,
            "v": valor_centavos,
            "ate": valido_ate,
            "agora": agora,
            "r": json.dumps(resposta, ensure_ascii=False),
        },
    )


def link_do_pedido(c: Connection, pedido_id: str):
    """O link mais recente do pedido (um vivo por vez), ou None."""
    return c.execute(
        text(
            "SELECT url, valido_ate FROM doce.link_pagamento WHERE pedido_id::text = :p"
            " ORDER BY criado_em DESC, id DESC LIMIT 1"
        ),
        {"p": pedido_id},
    ).one_or_none()


def ultimo_aviso(c: Connection, pedido_id: str) -> tuple[str, str] | None:
    """(transaction_nsu, slug) da última notícia do gateway sobre o pedido."""
    r = c.execute(
        text(
            "SELECT transaction_nsu, slug FROM doce.confirmacao_pagamento"
            " WHERE pedido_id::text = :p AND transaction_nsu IS NOT NULL AND slug IS NOT NULL"
            " ORDER BY id DESC LIMIT 1"
        ),
        {"p": pedido_id},
    ).one_or_none()
    return (r.transaction_nsu, r.slug) if r else None


def a_estornar(c: Connection, pedido_id: str) -> bool:
    """Há pagamento a estornar ainda não resolvido pelo operador (mensagem do WhatsApp)."""
    return (
        c.execute(
            text(
                "SELECT 1 FROM doce.confirmacao_pagamento WHERE pedido_id::text = :p"
                " AND resultado = 'a_estornar' AND resolvido_em IS NULL LIMIT 1"
            ),
            {"p": pedido_id},
        ).first()
        is not None
    )


def registrar(
    c: Connection,
    pedido_id: str | None,
    origem: str,
    resultado: Resultado,
    nsu: str | None,
    slug: str | None,
    conf: Conferencia | None,
    agora: datetime,
) -> None:
    """Uma linha por aviso ou conferência. Sem nome, telefone ou endereço do cliente."""
    sucesso = conf is not None and conf.success
    c.execute(
        text(
            "INSERT INTO doce.confirmacao_pagamento (pedido_id, origem, resultado,"
            " transaction_nsu, slug, metodo, parcelas, valor_cobrado_centavos,"
            " valor_pago_centavos, criado_em) VALUES (:p, :origem, :res, :nsu, :slug, :metodo,"
            " :parcelas, :cobrado, :pago, :agora)"
        ),
        {
            "p": pedido_id,
            "origem": origem,
            "res": resultado.value,
            "nsu": nsu,
            "slug": slug,
            "metodo": forma_do_pagamento(conf)[1] if sucesso and conf.capture_method else None,
            "parcelas": conf.installments if sucesso else None,
            "cobrado": conf.amount if sucesso else None,
            "pago": conf.paid_amount if sucesso else None,
            "agora": agora,
        },
    )


def situacao_do_pedido(p) -> Situacao:
    """Onde o pedido está para a regra pura. Vendas do painel seguem o estado do link."""
    if p.estado == "cancelado":
        if p.canal != "app":  # venda cancelada com o link expirado foi o prazo que cancelou
            expirou = p.pagamento_link == "expirado"
        else:
            expirou = p.pago_em is None and p.cancelado_em == p.expira_em
        return Situacao.EXPIRADO if expirou else Situacao.CANCELADO_PELO_OPERADOR
    if p.canal != "app":  # a venda já nasce paga; o que importa é o link
        return {
            "aguardando": Situacao.AGUARDANDO,
            "expirado": Situacao.EXPIRADO,
            "pago": Situacao.PAGO,
        }.get(p.pagamento_link, Situacao.CANCELADO_PELO_OPERADOR)
    return Situacao.AGUARDANDO if p.estado == "aguardando_pagamento" else Situacao.PAGO


def _travar(c: Connection, pedido_id: str):
    return c.execute(
        text("SELECT * FROM doce.pedido WHERE id::text = :id FOR UPDATE"), {"id": pedido_id}
    ).one_or_none()


def _nsu_ja_registrado(c: Connection, pedido_id: str, nsu: str) -> bool:
    return (
        c.execute(
            text(
                "SELECT 1 FROM doce.confirmacao_pagamento WHERE transaction_nsu = :n"
                " AND pedido_id::text = :p AND resultado = ANY(:r) LIMIT 1"
            ),
            {"n": nsu, "p": pedido_id, "r": [x.value for x in GASTAM_O_NSU]},
        ).first()
        is not None
    )


def _recusa_ja_listada(c: Connection, pedido_id: str, nsu: str) -> bool:
    return (
        c.execute(
            text(
                "SELECT 1 FROM doce.confirmacao_pagamento WHERE transaction_nsu = :n"
                " AND pedido_id::text = :p AND resultado = 'valor_recusado'"
                " AND resolvido_em IS NULL LIMIT 1"
            ),
            {"n": nsu, "p": pedido_id},
        ).first()
        is not None
    )


def _efeitos(c: Connection, p, resultado: Resultado, conf: Conferencia, agora: datetime) -> None:
    forma, _, parcelas = forma_do_pagamento(conf)
    depois_de_expirar = resultado is Resultado.PAGO_DEPOIS_DE_EXPIRAR
    pid = str(p.id)
    if p.canal != "app":
        # A venda já nasceu paga e baixada. No prazo, só o link muda (estoque intacto).
        # Depois de expirar (venda cancelada, estoque devolvido): baixa de novo se houver
        # (FaltaEstoque desfaz tudo e vai para "a decidir") e a venda volta a paga.
        if depois_de_expirar:
            pedidos.baixar_venda(c, pid, Estado.PRONTA, AUTOR, agora)
        c.execute(
            text(
                "UPDATE doce.pedido SET pagamento_link = 'pago', forma_pagamento = :forma,"
                " parcelas = :parcelas, valor_pago_centavos = :pago,"
                " pago_apos_expirar = :tarde,"
                " estado = 'pago', cancelado_em = NULL,"
                " pago_em = CASE WHEN :tarde THEN :agora ELSE pago_em END WHERE id = :id"
            ),
            {
                "forma": forma,
                "parcelas": parcelas,
                "pago": conf.paid_amount,
                "tarde": depois_de_expirar,
                "agora": agora,
                "id": p.id,
            },
        )
        return
    if p.tipo_entrega == "pronta_entrega":
        # Expirado: a separação já voltou à pronta entrega; vende dela se ainda houver.
        de = Estado.PRONTA if depois_de_expirar else Estado.SEPARADA
        pedidos.baixar_venda(c, pid, de, AUTOR, agora)
    c.execute(
        text(
            "UPDATE doce.pedido SET estado = 'pago', pago_em = :agora, cancelado_em = NULL,"
            " forma_pagamento = :forma, parcelas = :parcelas, valor_pago_centavos = :pago,"
            " pago_apos_expirar = :tarde, entrega_a_partir_de = :a_partir WHERE id = :id"
        ),
        {
            "agora": agora,
            "forma": forma,
            "parcelas": parcelas,
            "pago": conf.paid_amount,
            "tarde": depois_de_expirar,
            "a_partir": pedidos.a_partir_de(p, agora),
            "id": p.id,
        },
    )


def aplicar(
    c: Connection,
    pedido_id: str,
    origem: str,
    nsu: str,
    slug: str,
    conf: Conferencia,
    agora: datetime,
) -> Resultado:
    """Registra a conferência e, se for o caso, confirma o pedido. Uma vez só por pagamento."""
    p = _travar(c, pedido_id)
    if p is None:
        registrar(c, None, origem, Resultado.NAO_CONFIRMADO, nsu, slug, conf, agora)
        return Resultado.NAO_CONFIRMADO
    pedidos.liberar_expirados(c, agora)  # com o pedido já travado: expirado vira "cancelado"
    p = _travar(c, pedido_id)
    resultado = decidir(
        situacao=situacao_do_pedido(p),
        total_centavos=p.total_centavos,
        nsu_ja_registrado=_nsu_ja_registrado(c, pedido_id, nsu),
        conferencia=conf,
    )
    if resultado in (Resultado.CONFIRMADO, Resultado.PAGO_DEPOIS_DE_EXPIRAR):
        try:
            with c.begin_nested():  # reserva o nsu e mexe no estoque: tudo ou nada
                registrar(c, pedido_id, origem, resultado, nsu, slug, conf, agora)
                _efeitos(c, p, resultado, conf, agora)
            return resultado
        except FaltaEstoque:  # pago depois de expirar sem unidade: o operador decide
            resultado = Resultado.A_DECIDIR
        except IntegrityError:  # o mesmo pagamento já foi usado em outro pedido
            resultado = Resultado.NAO_CONFIRMADO
    if resultado is Resultado.VALOR_RECUSADO and _recusa_ja_listada(c, pedido_id, nsu):
        return resultado
    registrar(c, pedido_id, origem, resultado, nsu, slug, conf, agora)
    return resultado


def pendencias(c: Connection) -> list[dict]:
    return [
        {
            "id": r.id,
            "pedido_id": str(r.pedido_id) if r.pedido_id else None,
            "numero": r.numero,
            "resultado": r.resultado,
            "origem": r.origem,
            "metodo": r.metodo,
            "parcelas": r.parcelas,
            "total_centavos": r.total_centavos,
            "valor_cobrado_centavos": r.valor_cobrado_centavos,
            "valor_pago_centavos": r.valor_pago_centavos,
            "criado_em": r.criado_em.isoformat(),
        }
        for r in c.execute(
            text(
                "SELECT cp.id, cp.pedido_id, p.numero, p.total_centavos, cp.resultado,"
                " cp.origem, cp.metodo, cp.parcelas, cp.valor_cobrado_centavos,"
                " cp.valor_pago_centavos, cp.criado_em FROM doce.confirmacao_pagamento cp"
                " LEFT JOIN doce.pedido p ON p.id = cp.pedido_id"
                " WHERE cp.resolvido_em IS NULL AND cp.resultado = ANY(:r) ORDER BY cp.id"
            ),
            {"r": [x.value for x in PENDENTES]},
        )
    ]


def resolver(c: Connection, confirmacao_id: int, operador_id: str, agora: datetime) -> bool:
    """Marca a pendência como resolvida. False se ela não existe (ou não é uma pendência)."""
    achada = c.execute(
        text(
            "SELECT resolvido_em FROM doce.confirmacao_pagamento"
            " WHERE id = :id AND resultado = ANY(:r) FOR UPDATE"
        ),
        {"id": confirmacao_id, "r": [x.value for x in PENDENTES]},
    ).one_or_none()
    if achada is None:
        return False
    if achada.resolvido_em is None:
        c.execute(
            text(
                "UPDATE doce.confirmacao_pagamento SET resolvido_em = :agora,"
                " resolvido_por = :op WHERE id = :id"
            ),
            {"agora": agora, "op": operador_id, "id": confirmacao_id},
        )
    return True
