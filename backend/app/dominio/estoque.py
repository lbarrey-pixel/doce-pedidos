"""Estoque como livro de movimentos. O saldo é sempre derivado do livro.

Nada aqui conhece banco ou framework. A trava contra separação concorrente fica no
repositório (SELECT … FOR UPDATE); este módulo só decide se o movimento cabe no saldo lido.
Saldo nunca fica negativo; descongelamento termina sozinho depois do prazo.
"""

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from app.regras.config import DESCONGELAMENTO_H


class Lugar(StrEnum):
    LOJA = "loja"  # onde o cliente retira e de onde sai a entrega
    COZINHA = "cozinha"  # produção, freezer e reserva de bebidas


class Estado(StrEnum):
    PRONTA = "pronta"
    CONGELADA = "congelada"
    DESCONGELANDO = "descongelando"
    SEPARADA = "separada"
    RESERVA = "reserva"  # bebidas e afins guardados na cozinha, sem congelar


LUGAR_DO_ESTADO = {
    Estado.PRONTA: Lugar.LOJA,
    Estado.DESCONGELANDO: Lugar.LOJA,
    Estado.SEPARADA: Lugar.LOJA,
    Estado.CONGELADA: Lugar.COZINHA,
    Estado.RESERVA: Lugar.COZINHA,
}


class Tipo(StrEnum):
    PRODUCAO = "producao"
    ENTRADA = "entrada"  # bebidas e embalagens chegam compradas, não produzidas
    CONGELAMENTO = "congelamento"
    INICIO_DESCONGELAMENTO = "inicio_descongelamento"
    FIM_DESCONGELAMENTO = "fim_descongelamento"
    TRANSFERENCIA = "transferencia"  # reserva → pronta entrega
    SEPARACAO = "separacao"
    LIBERACAO_SEPARACAO = "liberacao_separacao"
    VENDA = "venda"
    PERDA = "perda"
    AJUSTE = "ajuste"


E = Estado
_TODOS = tuple(Estado)
# (de, para) permitidos por tipo. None = fora do estoque.
TRANSICOES: dict[Tipo, frozenset[tuple[Estado | None, Estado | None]]] = {
    Tipo.PRODUCAO: frozenset({(None, E.PRONTA), (None, E.CONGELADA)}),
    Tipo.ENTRADA: frozenset({(None, E.PRONTA), (None, E.RESERVA)}),
    Tipo.CONGELAMENTO: frozenset({(E.PRONTA, E.CONGELADA)}),
    Tipo.INICIO_DESCONGELAMENTO: frozenset({(E.CONGELADA, E.DESCONGELANDO)}),
    Tipo.FIM_DESCONGELAMENTO: frozenset({(E.DESCONGELANDO, E.PRONTA)}),
    Tipo.TRANSFERENCIA: frozenset({(E.RESERVA, E.PRONTA)}),
    Tipo.SEPARACAO: frozenset({(E.PRONTA, E.SEPARADA)}),
    Tipo.LIBERACAO_SEPARACAO: frozenset({(E.SEPARADA, E.PRONTA)}),
    Tipo.VENDA: frozenset({(E.SEPARADA, None), (E.PRONTA, None)}),
    Tipo.PERDA: frozenset((e, None) for e in _TODOS),
    Tipo.AJUSTE: frozenset({(None, e) for e in _TODOS} | {(e, None) for e in _TODOS}),
}
_EXIGE_PEDIDO = {Tipo.SEPARACAO, Tipo.LIBERACAO_SEPARACAO, Tipo.VENDA}


class Controle(StrEnum):
    """Como o estoque de uma variante é controlado."""

    CONGELAVEL = "congelavel"  # pronta entrega, reserva congelada e descongelamento
    RESERVA = "reserva"  # bebidas: pronta entrega e estoque reserva
    SIMPLES = "simples"  # embalagens: só pronta entrega


_ESTADOS_DO_CONTROLE = {
    Controle.CONGELAVEL: {E.PRONTA, E.CONGELADA, E.DESCONGELANDO, E.SEPARADA},
    Controle.RESERVA: {E.PRONTA, E.RESERVA, E.SEPARADA},
    Controle.SIMPLES: {E.PRONTA, E.SEPARADA},
}
_TIPOS_SO_DO_CONGELAVEL = {
    Tipo.PRODUCAO,
    Tipo.CONGELAMENTO,
    Tipo.INICIO_DESCONGELAMENTO,
    Tipo.FIM_DESCONGELAMENTO,
}
_EXIGE_MOTIVO = {Tipo.PERDA, Tipo.AJUSTE}


@dataclass(frozen=True)
class Movimento:
    variante: str
    tipo: Tipo
    quantidade: int
    de_estado: Estado | None
    para_estado: Estado | None
    autor: str
    criado_em: datetime
    pedido_id: str | None = None
    motivo: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.quantidade, int) or self.quantidade <= 0:
            raise ValueError("quantidade precisa ser inteiro positivo")
        if (self.de_estado, self.para_estado) not in TRANSICOES[self.tipo]:
            raise ValueError(
                f"transição inválida para {self.tipo}: {self.de_estado} → {self.para_estado}"
            )
        if self.tipo in _EXIGE_PEDIDO and not self.pedido_id:
            raise ValueError(f"{self.tipo} exige pedido_id")
        if self.tipo in _EXIGE_MOTIVO and not self.motivo.strip():
            raise ValueError(f"{self.tipo} exige motivo")
        if not self.autor.strip():
            raise ValueError("movimento sem autor")
        if self.criado_em.tzinfo is None:
            raise ValueError("criado_em precisa de fuso")


class FaltaEstoque(Exception):
    def __init__(self, estado: Estado, disponivel: int, pedido: int) -> None:
        super().__init__(f"falta estoque em {estado}: há {disponivel}, pedido {pedido}")
        self.estado, self.disponivel, self.pedido = estado, disponivel, pedido


@dataclass(frozen=True)
class Saldo:
    pronta: int = 0
    congelada: int = 0
    descongelando: int = 0
    separada: int = 0
    reserva: int = 0

    @property
    def disponivel_agora(self) -> int:
        return self.pronta

    @property
    def negativo(self) -> bool:
        return any(getattr(self, e.value) < 0 for e in Estado)

    def no_lugar(self, lugar: Lugar) -> int:
        return sum(getattr(self, e.value) for e, lg in LUGAR_DO_ESTADO.items() if lg == lugar)


def _servir_ao_controle(m: Movimento, controle: Controle) -> None:
    congelavel = controle is Controle.CONGELAVEL
    so_congelavel = m.tipo in _TIPOS_SO_DO_CONGELAVEL
    # Produção e congelamento só no controle congelável; entrada só nos outros.
    if so_congelavel != congelavel and m.tipo in _TIPOS_SO_DO_CONGELAVEL | {Tipo.ENTRADA}:
        raise ValueError(f"{m.tipo} não serve ao controle {controle}")
    usados = {e for e in (m.de_estado, m.para_estado) if e is not None}
    if not usados <= _ESTADOS_DO_CONTROLE[controle]:
        raise ValueError(f"estado fora do controle {controle}: {sorted(usados)}")


def aplicar(saldo: Saldo, m: Movimento, controle: Controle = Controle.CONGELAVEL) -> Saldo:
    """Aplica um movimento ao saldo lido. Nenhum saldo fica negativo."""
    _servir_ao_controle(m, controle)
    mudancas: dict[str, int] = {}
    if m.de_estado is not None:
        atual = getattr(saldo, m.de_estado.value)
        if atual < m.quantidade:
            raise FaltaEstoque(m.de_estado, atual, m.quantidade)
        mudancas[m.de_estado.value] = atual - m.quantidade
    if m.para_estado is not None:
        base = mudancas.get(m.para_estado.value, getattr(saldo, m.para_estado.value))
        mudancas[m.para_estado.value] = base + m.quantidade
    return replace(saldo, **mudancas)


def saldo_de(livro: Iterable[Movimento]) -> dict[str, Saldo]:
    """Soma o livro por variante, sem checar falta: cada movimento foi validado ao ser gravado."""
    contas: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(Estado, 0))
    for m in livro:
        if m.de_estado is not None:
            contas[m.variante][m.de_estado] -= m.quantidade
        if m.para_estado is not None:
            contas[m.variante][m.para_estado] += m.quantidade
    return {v: Saldo(**{e.value: n for e, n in c.items()}) for v, c in contas.items()}


@dataclass(frozen=True)
class LoteDescongelando:
    variante: str
    quantidade: int
    pronta_as: datetime


@dataclass(frozen=True)
class Descongelamento:
    vencidos: list[Movimento]  # fim_descongelamento a gravar (autor "app")
    pendentes: list[LoteDescongelando]


def descongelamento(livro: Iterable[Movimento], agora: datetime) -> Descongelamento:
    """Fins de descongelamento vencidos e lotes ainda descongelando.

    Cada início abre um lote que fica pronto depois do prazo. Fim, perda e ajuste que tiram
    do estado descongelando consomem os lotes por ordem de início (FIFO).
    """
    prazo = timedelta(hours=DESCONGELAMENTO_H)
    lotes: dict[str, deque[list]] = defaultdict(deque)
    for m in sorted(livro, key=lambda m: m.criado_em):
        if m.para_estado is E.DESCONGELANDO:
            lotes[m.variante].append([m.criado_em, m.quantidade])
        elif m.de_estado is E.DESCONGELANDO:
            falta, fila = m.quantidade, lotes[m.variante]
            while falta and fila:
                usa = min(falta, fila[0][1])
                fila[0][1] -= usa
                falta -= usa
                if fila[0][1] == 0:
                    fila.popleft()
    vencidos, pendentes = [], []
    for variante, fila in lotes.items():
        for inicio, qtd in fila:
            pronta_as = inicio + prazo
            if pronta_as <= agora:
                vencidos.append(
                    Movimento(
                        variante=variante,
                        tipo=Tipo.FIM_DESCONGELAMENTO,
                        quantidade=qtd,
                        de_estado=E.DESCONGELANDO,
                        para_estado=E.PRONTA,
                        autor="app",
                        criado_em=pronta_as,
                    )
                )
            else:
                pendentes.append(LoteDescongelando(variante, qtd, pronta_as))
    return Descongelamento(vencidos, pendentes)
