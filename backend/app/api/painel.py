"""Estoque no painel: saldos por Variante e lançamentos do operador."""

from datetime import UTC

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.adaptadores import repositorio_pedidos as pedidos
from app.adaptadores import repositorio_sql as repo
from app.api.auth import Operador, OperadorAtual
from app.api.erros import ErroDeNegocio
from app.dominio.estoque import Estado, FaltaEstoque, Movimento, Tipo

router = APIRouter(prefix="/painel")

ESTADOS_SALDO = ("pronta", "separada", "congelada", "descongelando", "reserva")
# Tipos que o operador lança por aqui; de/para fixos quando o tipo só tem um caminho.
CAMINHO_FIXO = {
    Tipo.CONGELAMENTO: (Estado.PRONTA, Estado.CONGELADA),
    Tipo.INICIO_DESCONGELAMENTO: (Estado.CONGELADA, Estado.DESCONGELANDO),
    Tipo.TRANSFERENCIA: (Estado.RESERVA, Estado.PRONTA),
}
TIPOS_DO_OPERADOR = {Tipo.PRODUCAO, Tipo.ENTRADA, Tipo.PERDA, Tipo.AJUSTE, *CAMINHO_FIXO}


class NovoMovimento(BaseModel):
    variante_id: str
    tipo: Tipo
    quantidade: int = Field(gt=0, le=10_000)
    de_estado: Estado | None = None
    para_estado: Estado | None = None
    motivo: str = Field(default="", max_length=500)


def _saldo(s) -> dict[str, int]:
    return {e: getattr(s, e) for e in ESTADOS_SALDO}


def _falta(e: FaltaEstoque, variante_id: str) -> ErroDeNegocio:
    return ErroDeNegocio(
        "falta_estoque",
        f"Só há {e.disponivel} em {e.estado.value.replace('_', ' ')}.",
        variante_id=variante_id,
        disponivel=e.disponivel,
    )


def _existe(c: Connection, variante_id: str) -> bool:
    return (
        c.execute(
            text("SELECT 1 FROM doce.variante WHERE id::text = :v"), {"v": variante_id}
        ).first()
        is not None
    )


@router.get("/estoque")
def estoque(request: Request, _: Operador = OperadorAtual) -> dict:
    with request.app.state.engine.begin() as c:
        pendentes = repo.atualizar_descongelamentos(c, request.app.state.relogio())
        linhas = c.execute(
            text(
                """
                SELECT v.id, p.nome AS produto, v.tamanho, c.nome AS categoria,
                       v.controle_estoque, v.preco_centavos, v.ativa, v.foto,
                       s.pronta, s.separada, s.congelada, s.descongelando, s.reserva
                FROM doce.variante v
                JOIN doce.produto p ON p.id = v.produto_id
                JOIN doce.categoria c ON c.id = v.categoria_id
                JOIN doce.saldo s ON s.variante_id = v.id
                WHERE v.excluida_em IS NULL
                ORDER BY c.ordem, v.ordem
                """
            )
        ).all()
    lotes: dict[str, list] = {}
    for lote in sorted(pendentes, key=lambda x: x.pronta_as):
        lotes.setdefault(lote.variante, []).append(
            {"quantidade": lote.quantidade, "pronta_as": lote.pronta_as.astimezone(UTC).isoformat()}
        )
    return {
        "variantes": [
            {
                "id": str(r.id),
                "produto": r.produto,
                "tamanho": r.tamanho,
                "categoria": r.categoria,
                "controle_estoque": r.controle_estoque,
                "preco_centavos": r.preco_centavos,
                "ativa": r.ativa,
                "foto": r.foto,
                "saldo": _saldo(r),
                "descongelando": lotes.get(str(r.id), []),
            }
            for r in linhas
        ]
    }


@router.post("/estoque/movimentos")
def movimentar(novo: NovoMovimento, request: Request, operador: Operador = OperadorAtual) -> dict:
    if novo.tipo not in TIPOS_DO_OPERADOR:
        raise ErroDeNegocio("movimento_invalido", "Esse lançamento não é feito por aqui.")
    de, para = CAMINHO_FIXO.get(novo.tipo, (novo.de_estado, novo.para_estado))
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        if not _existe(c, novo.variante_id):
            raise ErroDeNegocio("variante_desconhecida", "Item fora do cardápio.")
        repo.atualizar_descongelamentos(c, agora)
        try:
            m = Movimento(
                variante=novo.variante_id,
                tipo=novo.tipo,
                quantidade=novo.quantidade,
                de_estado=de,
                para_estado=para,
                autor=operador.id,
                criado_em=agora,
                motivo=novo.motivo.strip(),
            )
            saldo = repo.registrar_movimento(c, m)
        except FaltaEstoque as e:
            raise _falta(e, novo.variante_id) from e
        except ValueError as e:
            raise ErroDeNegocio("movimento_invalido", "Esse lançamento não serve aqui.") from e
    return {"saldo": _saldo(saldo)}


@router.get("/entregadores")
def entregadores(request: Request, _: Operador = OperadorAtual) -> dict:
    """Entregadores já usados, para escolher na saída."""
    with request.app.state.engine.connect() as c:
        return {"entregadores": pedidos.entregadores(c)}
