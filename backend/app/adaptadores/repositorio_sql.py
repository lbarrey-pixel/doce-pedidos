"""Repositório SQL do schema doce. SQL explícito sobre SQLAlchemy Core.

Toda função recebe a conexão; quem chama abre e fecha a transação. Assim a separação
(trava do saldo + movimento + Pedido) cabe numa transação só.
"""

from datetime import datetime

from sqlalchemy import Connection, text

from app.dominio.catalogo import Catalogo
from app.dominio.estoque import (
    Controle,
    Estado,
    LoteDescongelando,
    Movimento,
    Saldo,
    Tipo,
    aplicar,
    descongelamento,
)
from app.regras.config import CONTROLE_POR_CATEGORIA

_ESTADOS = [e.value for e in Estado]


def carregar_catalogo(conn: Connection, catalogo: Catalogo) -> None:
    """Carrega ou atualiza o cardápio (idempotente por nome e tamanho) e cria o saldo zerado."""
    for ordem, nome in enumerate(catalogo.categorias):
        conn.execute(
            text(
                "INSERT INTO doce.categoria (nome, ordem) VALUES (:nome, :ordem)"
                " ON CONFLICT (nome) DO UPDATE SET ordem = EXCLUDED.ordem"
            ),
            {"nome": nome, "ordem": ordem},
        )
    for nome in catalogo.produtos:
        conn.execute(
            text("INSERT INTO doce.produto (nome) VALUES (:nome) ON CONFLICT (nome) DO NOTHING"),
            {"nome": nome},
        )
    for ordem, v in enumerate(catalogo.variantes):
        conn.execute(
            text(
                """
                INSERT INTO doce.variante (produto_id, categoria_id, tamanho, peso_g, porcoes,
                  descricao, ingredientes, observacao, foto, preco_centavos, edicao_limitada, ordem)
                SELECT p.id, c.id, :tamanho, :peso_g, :porcoes, :descricao, :ingredientes,
                  :observacao, :foto, :preco, :edicao_limitada, :ordem
                FROM doce.produto p, doce.categoria c
                WHERE p.nome = :produto AND c.nome = :categoria
                ON CONFLICT (produto_id, tamanho) DO UPDATE SET
                  categoria_id = EXCLUDED.categoria_id, peso_g = EXCLUDED.peso_g,
                  porcoes = EXCLUDED.porcoes, descricao = EXCLUDED.descricao,
                  ingredientes = EXCLUDED.ingredientes, observacao = EXCLUDED.observacao,
                  foto = EXCLUDED.foto, preco_centavos = EXCLUDED.preco_centavos,
                  edicao_limitada = EXCLUDED.edicao_limitada, ordem = EXCLUDED.ordem
                """
            ),
            {
                "produto": v.produto,
                "categoria": v.categoria,
                "tamanho": v.tamanho,
                "peso_g": v.peso_g,
                "porcoes": v.porcoes,
                "descricao": v.descricao,
                "ingredientes": v.ingredientes,
                "observacao": v.observacao,
                "foto": v.foto,
                "preco": v.preco_centavos,
                "edicao_limitada": v.edicao_limitada,
                "ordem": ordem,
            },
        )
    conn.execute(
        text(
            "INSERT INTO doce.saldo (variante_id) SELECT id FROM doce.variante"
            " ON CONFLICT (variante_id) DO NOTHING"
        )
    )
    # Controle de estoque inicial pela categoria, só em variante ainda sem movimento.
    for categoria, controle in CONTROLE_POR_CATEGORIA.items():
        conn.execute(
            text(
                """
                UPDATE doce.variante v SET controle_estoque = :controle
                FROM doce.categoria c
                WHERE c.id = v.categoria_id AND c.nome = :categoria
                  AND NOT EXISTS (SELECT 1 FROM doce.movimento m WHERE m.variante_id = v.id)
                """
            ),
            {"categoria": categoria, "controle": controle},
        )


def id_da_variante(conn: Connection, produto: str, tamanho: str) -> str:
    return str(
        conn.execute(
            text(
                "SELECT v.id FROM doce.variante v JOIN doce.produto p ON p.id = v.produto_id"
                " WHERE p.nome = :produto AND v.tamanho = :tamanho"
            ),
            {"produto": produto, "tamanho": tamanho},
        ).scalar_one()
    )


def _linha_para_saldo(linha) -> Saldo:
    return Saldo(**{e: getattr(linha, e) for e in _ESTADOS})


def registrar_movimento(conn: Connection, m: Movimento) -> Saldo:
    """Trava o saldo da Variante, valida no domínio, grava o movimento e o novo saldo."""
    linha = conn.execute(
        text(
            f"SELECT {', '.join('s.' + e for e in _ESTADOS)}, v.controle_estoque"
            " FROM doce.saldo s JOIN doce.variante v ON v.id = s.variante_id"
            " WHERE s.variante_id = :v FOR UPDATE OF s"
        ),
        {"v": m.variante},
    ).one()
    novo = aplicar(_linha_para_saldo(linha), m, Controle(linha.controle_estoque))
    conn.execute(
        text(
            "INSERT INTO doce.movimento (variante_id, tipo, quantidade, de_estado, para_estado,"
            " pedido_id, autor, motivo, criado_em) VALUES (:v, :tipo, :qtd, :de, :para,"
            " :pedido, :autor, :motivo, :criado_em)"
        ),
        {
            "v": m.variante,
            "tipo": m.tipo.value,
            "qtd": m.quantidade,
            "de": m.de_estado.value if m.de_estado else None,
            "para": m.para_estado.value if m.para_estado else None,
            "pedido": m.pedido_id,
            "autor": m.autor,
            "motivo": m.motivo,
            "criado_em": m.criado_em,
        },
    )
    conn.execute(
        text(
            f"UPDATE doce.saldo SET {', '.join(f'{e} = :{e}' for e in _ESTADOS)}"
            " WHERE variante_id = :v"
        ),
        {"v": m.variante, **{e: getattr(novo, e) for e in _ESTADOS}},
    )
    return novo


def saldos(conn: Connection) -> dict[str, Saldo]:
    linhas = conn.execute(text(f"SELECT variante_id, {', '.join(_ESTADOS)} FROM doce.saldo"))
    return {str(r.variante_id): _linha_para_saldo(r) for r in linhas}


def conferir_saldos(conn: Connection) -> list[str]:
    """Variantes cujo saldo materializado difere da soma do livro (deve ser lista vazia)."""
    soma = ", ".join(
        f"coalesce(sum(CASE WHEN para_estado = '{e}' THEN quantidade ELSE 0 END)"
        f" - sum(CASE WHEN de_estado = '{e}' THEN quantidade ELSE 0 END), 0) AS {e}"
        for e in _ESTADOS
    )
    diferentes = conn.execute(
        text(
            f"""
            WITH livro AS (
              SELECT s.variante_id, {soma}
              FROM doce.saldo s LEFT JOIN doce.movimento m ON m.variante_id = s.variante_id
              GROUP BY s.variante_id
            )
            SELECT s.variante_id FROM doce.saldo s JOIN livro l USING (variante_id)
            WHERE {" OR ".join(f"s.{e} <> l.{e}" for e in _ESTADOS)}
            """
        )
    )
    return [str(r.variante_id) for r in diferentes]


def atualizar_descongelamentos(conn: Connection, agora: datetime) -> list[LoteDescongelando]:
    """Grava os fins de Descongelamento vencidos e devolve os lotes ainda descongelando.

    Sem agendador (ADR 0005): roda ao ler ou mexer no estoque. Idempotente.
    """
    linhas = conn.execute(
        text(
            "SELECT variante_id, tipo, quantidade, de_estado, para_estado, autor, motivo,"
            " criado_em FROM doce.movimento"
            " WHERE de_estado = 'descongelando' OR para_estado = 'descongelando'"
            " ORDER BY criado_em"
        )
    )
    livro = [
        Movimento(
            variante=str(r.variante_id),
            tipo=Tipo(r.tipo),
            quantidade=r.quantidade,
            de_estado=Estado(r.de_estado) if r.de_estado else None,
            para_estado=Estado(r.para_estado) if r.para_estado else None,
            autor=r.autor,
            criado_em=r.criado_em,
            motivo=r.motivo or "-",
        )
        for r in linhas
    ]
    resultado = descongelamento(livro, agora)
    for fim in resultado.vencidos:
        registrar_movimento(conn, fim)
    return resultado.pendentes
