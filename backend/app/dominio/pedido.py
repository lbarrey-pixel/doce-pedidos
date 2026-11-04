"""Pedido do app: valores, pedido mínimo, entrega ou retirada, horário e pagamento.

Puro: recebe o cardápio com a pronta entrega já lida e devolve o pedido montado ou uma
Recusa com o código que a API traduz em mensagem.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from app.dominio.dinheiro import percentual
from app.dominio.entrega import taxa_de_entrega
from app.dominio.horario import (
    HORARIO_PADRAO,
    Horario,
    abre_as,
    agendamento_valido,
    encomenda_valida,
    loja_aberta,
    primeira_encomenda,
    primeiro_agendamento,
)
from app.regras import config

Recebimento = Literal["entrega", "retirada"]
TipoEntrega = Literal["pronta_entrega", "encomenda"]


class Recusa(Exception):
    def __init__(self, codigo: str, **dados: object) -> None:
        super().__init__(codigo)
        self.codigo, self.dados = codigo, dados


class ValorDivergente(Exception):
    def __init__(self, esperado: int, recebido: int) -> None:
        super().__init__(f"esperado {esperado}, recebido {recebido}")
        self.esperado, self.recebido = esperado, recebido


@dataclass(frozen=True)
class ItemCatalogo:
    variante: str
    nome: str
    preco_centavos: int
    pronta: int
    ativa: bool = True


@dataclass(frozen=True)
class Escolha:
    variante: str
    quantidade: int

    def __post_init__(self) -> None:
        if not isinstance(self.quantidade, int) or self.quantidade <= 0:
            raise ValueError("quantidade precisa ser inteiro positivo")


@dataclass(frozen=True)
class ItemDoPedido:
    variante: str
    nome: str
    quantidade: int
    preco_unitario_centavos: int

    @property
    def total_centavos(self) -> int:
        return self.quantidade * self.preco_unitario_centavos


@dataclass(frozen=True)
class PedidoMontado:
    itens: tuple[ItemDoPedido, ...]
    recebimento: Recebimento
    tipo_entrega: TipoEntrega
    subtotal_centavos: int
    desconto_centavos: int
    taxa_entrega_centavos: int
    entrega_a_partir_de: datetime
    expira_em: datetime
    separar: list[tuple[str, int]] = field(default_factory=list)

    @property
    def total_centavos(self) -> int:
        return self.subtotal_centavos - self.desconto_centavos + self.taxa_entrega_centavos


def montar_pedido(
    escolhas: list[Escolha],
    catalogo: dict[str, ItemCatalogo],
    *,
    agora: datetime,
    recebimento: Recebimento,
    distancia_m: int | None,
    desconto_pct: int,
    tipo_entrega: TipoEntrega,
    entrega_em: datetime | None,
    pedido_minimo_centavos: int = config.PEDIDO_MINIMO_CENTAVOS,
    faixas: tuple[tuple[int, int], ...] | list = config.FAIXAS_DISTANCIA,
    horario: Horario = HORARIO_PADRAO,
    expiracao_min: int = config.EXPIRACAO_PAGAMENTO_MIN,
    tempo_preparo_min: int = config.TEMPO_PREPARO_PADRAO_MIN,
) -> PedidoMontado:
    if not escolhas:
        raise Recusa("carrinho_vazio")
    quantidades: Counter[str] = Counter()
    for e in escolhas:
        quantidades[e.variante] += e.quantidade
    itens = []
    for variante, qtd in quantidades.items():
        c = catalogo.get(variante)
        if c is None or not c.ativa:
            raise Recusa("variante_indisponivel", variante=variante)
        itens.append(ItemDoPedido(variante, c.nome, qtd, c.preco_centavos))
    subtotal = sum(i.total_centavos for i in itens)
    if subtotal < pedido_minimo_centavos:  # antes do desconto e sem a taxa
        raise Recusa("abaixo_do_minimo", falta_centavos=pedido_minimo_centavos - subtotal)

    if recebimento == "retirada":
        taxa = 0
    elif distancia_m is None:
        raise Recusa("endereco_nao_encontrado")  # nunca estima: o cliente combina à parte
    else:
        taxa = taxa_de_entrega(distancia_m, faixas)
        if taxa is None:
            raise Recusa("sob_consulta")

    if tipo_entrega == "pronta_entrega":
        if entrega_em is None and not loja_aberta(agora, horario):  # agendada vale fechada
            raise Recusa(
                "loja_fechada",
                abre_as=abre_as(agora, horario),
                primeira_encomenda=primeira_encomenda(agora, horario),
            )
        for i in itens:  # só o que está pronto na loja é vendido para agora
            if i.quantidade > catalogo[i.variante].pronta:
                raise Recusa(
                    "sem_estoque",
                    variante=i.variante,
                    disponivel=catalogo[i.variante].pronta,
                    primeira_encomenda=primeira_encomenda(agora, horario),
                )
        minutos = (
            config.PREPARO_RETIRADA_MIN if recebimento == "retirada" else config.PREVISAO_PRONTA_MIN
        )
        a_partir_de = agora + timedelta(minutes=minutos)
        if entrega_em is not None:  # pronta entrega agendada para hoje
            if not agendamento_valido(agora, entrega_em, horario, tempo_preparo_min):
                raise Recusa(
                    "agendamento_horario",
                    primeiro_agendamento=primeiro_agendamento(agora, horario, tempo_preparo_min),
                    primeira_encomenda=primeira_encomenda(agora, horario),
                )
            a_partir_de = entrega_em
        separar = [(i.variante, i.quantidade) for i in itens]
    else:
        if entrega_em is None or not encomenda_valida(agora, entrega_em, horario):
            raise Recusa(
                "encomenda_antecedencia", primeira_encomenda=primeira_encomenda(agora, horario)
            )
        a_partir_de, separar = entrega_em, []

    return PedidoMontado(
        itens=tuple(itens),
        recebimento=recebimento,
        tipo_entrega=tipo_entrega,
        subtotal_centavos=subtotal,
        desconto_centavos=percentual(subtotal, desconto_pct),
        taxa_entrega_centavos=taxa,
        entrega_a_partir_de=a_partir_de,
        expira_em=agora + timedelta(minutes=expiracao_min),
        separar=separar,
    )


def confirmar_pagamento(esperado: int, recebido: int, *, aceitar_diferenca: bool) -> int:
    """Diferença registrada (recebido − esperado). Sem aceitar, valor diferente é recusado."""
    if recebido != esperado and not aceitar_diferenca:
        raise ValorDivergente(esperado, recebido)
    return recebido - esperado


def expirou(estado: str, expira_em: datetime | None, agora: datetime) -> bool:
    return estado == "aguardando_pagamento" and expira_em is not None and agora >= expira_em
