"""Pedidos do App no banco: criação com separação, expiração preguiçosa (ADR 0005),
confirmação do Pix, mudança de estado e reconhecimento do cliente."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from app.adaptadores.repositorio_sql import registrar_movimento
from app.dominio.cliente import Anterior, chave
from app.dominio.estoque import Estado, Movimento, Tipo
from app.dominio.horario import Horario
from app.dominio.pedido import ItemCatalogo, PedidoMontado
from app.regras.config import (
    PREPARO_RETIRADA_MIN,
    PREVISAO_PRONTA_MIN,
    TEMPO_ENTREGA_MIN,
    TEMPO_PREPARO_PADRAO_MIN,
)


@dataclass(frozen=True)
class Configuracao:
    pedido_minimo_centavos: int
    desconto_app_percentual: int
    pix_chave: str
    pix_nome: str
    pix_cidade: str
    whatsapp_negocio: str
    origem: tuple[float, float]
    faixas: tuple[tuple[int, int], ...]
    horario: Horario
    expiracao_pagamento_min: int = 30
    tempo_preparo_min: int = TEMPO_PREPARO_PADRAO_MIN


def configuracao(conn: Connection) -> Configuracao:
    r = conn.execute(text("SELECT * FROM doce.configuracao_loja WHERE id = 1")).one()
    e = r.endereco_origem
    return Configuracao(
        r.pedido_minimo_centavos,
        r.desconto_app_percentual,
        r.pix_chave,
        r.pix_nome,
        r.pix_cidade,
        r.whatsapp_negocio,
        (e["lat"], e["lon"]),
        tuple((int(a), int(t)) for a, t in r.faixas_distancia),
        Horario(r.horario_abertura, r.horario_fechamento),
        r.expiracao_pagamento_min,
        r.tempo_preparo_min,
    )


def a_partir_de(p, agora: datetime) -> datetime:
    """Quando o pedido recém-pago pode sair: encomenda mantém a data; o resto, agora + preparo."""
    if p.tipo_entrega == "encomenda":
        return p.entrega_a_partir_de
    minutos = PREPARO_RETIRADA_MIN if p.recebimento == "retirada" else PREVISAO_PRONTA_MIN
    # Pronta entrega agendada: pago antes do horário escolhido, o horário fica.
    return max(agora + timedelta(minutes=minutos), p.entrega_a_partir_de or agora)


def catalogo(conn: Connection) -> dict[str, ItemCatalogo]:
    linhas = conn.execute(
        text(
            "SELECT v.id, p.nome || CASE WHEN v.tamanho <> '' THEN ' · ' || v.tamanho ELSE ''"
            " END AS nome, v.preco_centavos, v.ativa, s.pronta FROM doce.variante v"
            " JOIN doce.produto p ON p.id = v.produto_id"
            " JOIN doce.saldo s ON s.variante_id = v.id"
        )
    )
    return {
        str(r.id): ItemCatalogo(str(r.id), r.nome, r.preco_centavos, r.pronta, r.ativa)
        for r in linhas
    }


def _movimento(variante, tipo, qtd, de, para, pedido_id, agora, autor="app", motivo=""):
    return Movimento(
        variante=variante,
        tipo=tipo,
        quantidade=qtd,
        de_estado=de,
        para_estado=para,
        autor=autor,
        criado_em=agora,
        pedido_id=pedido_id,
        motivo=motivo,
    )


def itens_do_pedido(conn: Connection, pedido_id: str) -> list[tuple[str, int]]:
    return [
        (str(r.variante_id), r.q)
        for r in conn.execute(
            text(
                "SELECT variante_id, sum(quantidade)::int AS q FROM doce.item_pedido"
                " WHERE pedido_id = :p GROUP BY variante_id"
            ),
            {"p": pedido_id},
        )
    ]


def itens_com_nome(conn: Connection, pedido_ids: list[str]) -> dict[str, list[dict]]:
    """Itens de vários Pedidos com o nome da tela ("Produto · tamanho"), por Pedido."""
    itens: dict[str, list[dict]] = {}
    for r in conn.execute(
        text(
            "SELECT i.pedido_id, i.variante_id, p.nome || CASE WHEN v.tamanho <> ''"
            " THEN ' · ' || v.tamanho ELSE '' END AS nome, i.quantidade FROM doce.item_pedido i"
            " JOIN doce.variante v ON v.id = i.variante_id"
            " JOIN doce.produto p ON p.id = v.produto_id"
            " WHERE i.pedido_id::text = ANY(:ids) ORDER BY i.id"
        ),
        {"ids": [str(i) for i in pedido_ids]},
    ):
        itens.setdefault(str(r.pedido_id), []).append(
            {"variante_id": str(r.variante_id), "nome": r.nome, "quantidade": r.quantidade}
        )
    return itens


def marcar_entregues(conn: Connection, agora: datetime) -> None:
    """Saiu há mais que o tempo médio de entrega: Entregue, sem confirmação."""
    conn.execute(
        text(
            "UPDATE doce.pedido SET estado = 'entregue', entregue_em = saiu_em + :prazo"
            " WHERE estado = 'saiu' AND saiu_em IS NOT NULL AND saiu_em + :prazo <= :agora"
        ),
        {"prazo": timedelta(minutes=TEMPO_ENTREGA_MIN), "agora": agora},
    )


def guardar_entregador(conn: Connection, nome: str, telefone: str) -> dict:
    dados = {"nome": nome.strip(), "telefone": "".join(c for c in telefone if c.isdigit())}
    conn.execute(
        text(
            "INSERT INTO doce.entregador (nome, telefone) VALUES (:nome, :telefone)"
            " ON CONFLICT (nome, telefone) DO NOTHING"
        ),
        dados,
    )
    return dados


def entregadores(conn: Connection) -> list[dict]:
    return [
        {"nome": r.nome, "telefone": r.telefone}
        for r in conn.execute(
            text("SELECT nome, telefone FROM doce.entregador ORDER BY nome, telefone")
        )
    ]


def liberar_expirados(conn: Connection, agora: datetime) -> None:
    """Pedido aguardando pagamento depois de 30 min vira cancelado e devolve a separação."""
    vencidos = conn.execute(
        text(
            "SELECT id, tipo_entrega, expira_em FROM doce.pedido"
            " WHERE estado = 'aguardando_pagamento' AND expira_em <= :agora"
            " ORDER BY expira_em FOR UPDATE SKIP LOCKED"
        ),
        {"agora": agora},
    ).all()
    for p in vencidos:
        if p.tipo_entrega == "pronta_entrega":
            for variante, qtd in itens_do_pedido(conn, str(p.id)):
                registrar_movimento(
                    conn,
                    _movimento(
                        variante,
                        Tipo.LIBERACAO_SEPARACAO,
                        qtd,
                        Estado.SEPARADA,
                        Estado.PRONTA,
                        str(p.id),
                        p.expira_em,
                    ),
                )
        conn.execute(
            text(
                "UPDATE doce.pedido SET estado = 'cancelado', cancelado_em = expira_em"
                " WHERE id = :id"
            ),
            {"id": p.id},
        )
    expirar_links_de_venda(conn, agora)


def expirar_links_de_venda(conn: Connection, agora: datetime) -> None:
    """Venda do painel cujo link venceu sem pagamento é cancelada, o estoque que o lançamento
    baixou volta à pronta entrega e o link fica "expirado"."""
    vencidas = conn.execute(
        text(
            "SELECT p.id, p.numero, l.valido_ate FROM doce.pedido p"
            " JOIN LATERAL (SELECT valido_ate FROM doce.link_pagamento WHERE pedido_id = p.id"
            " ORDER BY criado_em DESC, id DESC LIMIT 1) l ON true"
            " WHERE p.pagamento_link = 'aguardando' AND p.estado <> 'cancelado'"
            " AND l.valido_ate <= :agora ORDER BY l.valido_ate FOR UPDATE OF p SKIP LOCKED"
        ),
        {"agora": agora},
    ).all()
    for v in vencidas:
        devolver_ao_estoque(
            conn,
            str(v.id),
            v.numero,
            "app",
            v.valido_ate,
            motivo=f"link da venda nº {v.numero} expirou sem pagamento",
        )
        conn.execute(
            text(
                "UPDATE doce.pedido SET estado = 'cancelado', cancelado_em = :ate,"
                " pagamento_link = 'expirado' WHERE id = :id"
            ),
            {"ate": v.valido_ate, "id": v.id},
        )


def anteriores(conn: Connection, telefone: str, nome: str) -> list[Anterior]:
    tel, primeiro = chave(telefone, nome)
    linhas = conn.execute(
        text(
            "SELECT cliente, endereco, criado_em FROM doce.pedido WHERE canal = 'app'"
            " AND cliente->>'telefone' = :t AND cliente->>'primeiro_nome' = :n"
            " AND endereco IS NOT NULL ORDER BY criado_em DESC LIMIT 5"
        ),
        {"t": tel, "n": primeiro},
    )
    return [
        Anterior(r.cliente["telefone"], r.cliente["nome"], r.endereco, r.criado_em) for r in linhas
    ]


def criar_pedido_app(
    conn: Connection,
    montado: PedidoMontado,
    cliente: dict,
    endereco: dict | None,
    distancia_m: int | None,
    agora: datetime,
    observacao: str | None = None,
) -> tuple[str, int]:
    tel, primeiro = chave(cliente["telefone"], cliente["nome"])
    dados_cliente = {
        "nome": cliente["nome"].strip(),
        "telefone": tel,
        "primeiro_nome": primeiro,
        "cpf": cliente.get("cpf") or None,
    }
    linha = conn.execute(
        text(
            """
            INSERT INTO doce.pedido (canal, cliente, endereco, distancia_m, subtotal_centavos,
              desconto_centavos, taxa_entrega_centavos, total_centavos, tipo_entrega,
              recebimento, entrega_a_partir_de, forma_pagamento, estado, expira_em, criado_em,
              observacao)
            VALUES ('app', CAST(:cliente AS jsonb), CAST(:endereco AS jsonb), :dist, :sub, :desc,
              :taxa, :total, :tipo, :receb, :a_partir, 'pix_manual', 'aguardando_pagamento',
              :expira, :agora, :obs)
            RETURNING id, numero
            """
        ),
        {
            "cliente": json.dumps(dados_cliente, ensure_ascii=False),
            "endereco": json.dumps(endereco, ensure_ascii=False) if endereco else None,
            "dist": distancia_m,
            "sub": montado.subtotal_centavos,
            "desc": montado.desconto_centavos,
            "taxa": montado.taxa_entrega_centavos,
            "total": montado.total_centavos,
            "tipo": montado.tipo_entrega,
            "receb": montado.recebimento,
            "a_partir": montado.entrega_a_partir_de,
            "expira": montado.expira_em,
            "agora": agora,
            "obs": observacao,
        },
    ).one()
    for i in montado.itens:
        conn.execute(
            text(
                "INSERT INTO doce.item_pedido (pedido_id, variante_id, quantidade,"
                " preco_unitario_centavos, total_centavos) VALUES (:p, :v, :q, :preco, :t)"
            ),
            {
                "p": linha.id,
                "v": i.variante,
                "q": i.quantidade,
                "preco": i.preco_unitario_centavos,
                "t": i.total_centavos,
            },
        )
    for variante, qtd in montado.separar:  # FOR UPDATE no saldo: um pedido por vez
        registrar_movimento(
            conn,
            _movimento(
                variante, Tipo.SEPARACAO, qtd, Estado.PRONTA, Estado.SEPARADA, str(linha.id), agora
            ),
        )
    return str(linha.id), linha.numero


def baixar_venda(conn: Connection, pedido_id: str, de: Estado, autor: str, agora) -> None:
    for variante, qtd in itens_do_pedido(conn, pedido_id):
        registrar_movimento(
            conn, _movimento(variante, Tipo.VENDA, qtd, de, None, pedido_id, agora, autor)
        )


def devolver_ao_estoque(
    conn: Connection, pedido_id: str, numero: int, autor: str, agora, motivo: str | None = None
) -> None:
    for variante, qtd in itens_do_pedido(conn, pedido_id):
        registrar_movimento(
            conn,
            _movimento(
                variante,
                Tipo.AJUSTE,
                qtd,
                None,
                Estado.PRONTA,
                pedido_id,  # identifica a devolução de cancelamento nos resumos
                agora,
                autor,
                motivo=motivo or f"cancelamento do pedido nº {numero}",
            ),
        )


def lancar_venda_balcao(
    conn: Connection, itens: list[tuple[str, int, int]], autor: str, agora: datetime
) -> tuple[str, int, int]:
    """Venda feita fora do app (balcão, WhatsApp, Instagram): nasce paga, a baixa sai da
    pronta entrega. `itens` é (variante, quantidade, preço unitário em centavos). Quem chama
    abre a transação: se faltar saldo, `FaltaEstoque` desfaz o pedido junto."""
    total = sum(q * preco for _, q, preco in itens)
    linha = conn.execute(
        text(
            "INSERT INTO doce.pedido (canal, subtotal_centavos, total_centavos, forma_pagamento,"
            " estado, criado_em, pago_em, confirmado_por) VALUES ('balcao', :t, :t, 'externo',"
            " 'pago', :agora, :agora, :op) RETURNING id, numero"
        ),
        {"t": total, "agora": agora, "op": autor},
    ).one()
    for variante, qtd, preco in itens:
        conn.execute(
            text(
                "INSERT INTO doce.item_pedido (pedido_id, variante_id, quantidade,"
                " preco_unitario_centavos, total_centavos) VALUES (:p, :v, :q, :preco, :t)"
            ),
            {"p": linha.id, "v": variante, "q": qtd, "preco": preco, "t": qtd * preco},
        )
    baixar_venda(conn, str(linha.id), Estado.PRONTA, autor, agora)
    return str(linha.id), linha.numero, total


def liberar_separacao(conn: Connection, pedido_id: str, autor: str, agora) -> None:
    for variante, qtd in itens_do_pedido(conn, pedido_id):
        registrar_movimento(
            conn,
            _movimento(
                variante,
                Tipo.LIBERACAO_SEPARACAO,
                qtd,
                Estado.SEPARADA,
                Estado.PRONTA,
                pedido_id,
                agora,
                autor,
            ),
        )


def separados(conn: Connection, pedido_id: str) -> dict[str, int]:
    """Unidades hoje separadas para o Pedido, por Variante (separação − liberação − venda)."""
    linhas = conn.execute(
        text(
            "SELECT variante_id, sum(CASE WHEN para_estado = 'separada' THEN quantidade"
            " WHEN de_estado = 'separada' THEN -quantidade ELSE 0 END)::int AS q"
            " FROM doce.movimento WHERE pedido_id::text = :p GROUP BY variante_id"
        ),
        {"p": pedido_id},
    )
    return {str(r.variante_id): r.q for r in linhas if r.q}


def separar_para_encomenda(
    conn: Connection, pedido_id: str, variante: str, qtd: int, origem: str, autor: str, agora
) -> None:
    """Produção (ou entrada) na Pronta entrega e separação para a Encomenda, ou o contrário."""
    if origem == "liberar":
        registrar_movimento(
            conn,
            _movimento(
                variante,
                Tipo.LIBERACAO_SEPARACAO,
                qtd,
                Estado.SEPARADA,
                Estado.PRONTA,
                pedido_id,
                agora,
                autor,
            ),
        )
        return
    if origem == "producao":
        controle = conn.execute(
            text("SELECT controle_estoque FROM doce.variante WHERE id::text = :v"), {"v": variante}
        ).scalar_one()
        tipo = Tipo.PRODUCAO if controle == "congelavel" else Tipo.ENTRADA
        registrar_movimento(
            conn, _movimento(variante, tipo, qtd, None, Estado.PRONTA, None, agora, autor)
        )
    registrar_movimento(
        conn,
        _movimento(
            variante, Tipo.SEPARACAO, qtd, Estado.PRONTA, Estado.SEPARADA, pedido_id, agora, autor
        ),
    )
