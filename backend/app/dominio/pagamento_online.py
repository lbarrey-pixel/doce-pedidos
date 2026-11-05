"""Pagamento online: quando um pedido pode ser dado por pago.

Puro, sem banco nem rede (ADR 0002). `decidir` recebe a situação do pedido e a conferência do
gateway e diz o que fazer. O aviso do gateway nunca é prova: só conta o que a conferência
confirma, com valor cobrado igual ao do pedido e valor pago igual ou maior só pelos juros do
parcelamento no cartão (ADR 0007).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.portas.pagamento import Conferencia

FUSO = ZoneInfo("America/Sao_Paulo")
ESTADOS_VENDIDOS = frozenset({"pago", "em_preparo", "saiu", "entregue"})
FORMAS = ("pix", "cartao", "pix_manual")


class Situacao(StrEnum):
    AGUARDANDO = "aguardando"
    PAGO = "pago"  # já pago (inclusive pela confirmação manual) ou adiante
    EXPIRADO = "expirado"
    CANCELADO_PELO_OPERADOR = "cancelado_pelo_operador"


class Resultado(StrEnum):
    CONFIRMADO = "confirmado"
    PAGO_DEPOIS_DE_EXPIRAR = "pago_depois_de_expirar"
    REPETIDO = "repetido"
    NAO_CONFIRMADO = "nao_confirmado"
    VALOR_RECUSADO = "valor_recusado"
    A_ESTORNAR = "a_estornar"
    A_DECIDIR = "a_decidir"  # pago depois de expirar sem estoque: o operador decide


def _e_pix(conferencia: Conferencia) -> bool:
    return "pix" in conferencia.capture_method.lower()


def decidir(
    *,
    situacao: Situacao,
    total_centavos: int,
    nsu_ja_registrado: bool,
    conferencia: Conferencia,
) -> Resultado:
    if not (conferencia.success and conferencia.paid):
        return Resultado.NAO_CONFIRMADO
    if conferencia.amount != total_centavos or conferencia.paid_amount < conferencia.amount:
        return Resultado.VALOR_RECUSADO
    if _e_pix(conferencia) and conferencia.paid_amount != conferencia.amount:
        return Resultado.VALOR_RECUSADO  # Pix não tem juros: só valor igual
    if nsu_ja_registrado:
        return Resultado.REPETIDO
    if situacao is Situacao.AGUARDANDO:
        return Resultado.CONFIRMADO
    if situacao is Situacao.EXPIRADO:
        return Resultado.PAGO_DEPOIS_DE_EXPIRAR
    return Resultado.A_ESTORNAR  # cancelado pelo operador, ou outro pagamento já confirmado


def forma_do_pagamento(conferencia: Conferencia) -> tuple[str, str, int]:
    """(forma do pedido, método do gateway, parcelas) a partir da conferência."""
    parcelas = conferencia.installments if conferencia.installments >= 1 else 1
    return ("pix", "pix", 1) if _e_pix(conferencia) else ("cartao", "credit_card", parcelas)


def taxa_estimada_centavos(valor_centavos: int, tarifa_bps: int) -> int:
    """Tarifa em pontos-base (420 = 4,20%) sobre o valor, arredondada ao centavo mais próximo."""
    return (valor_centavos * tarifa_bps + 5_000) // 10_000


@dataclass(frozen=True)
class VendaPaga:
    forma_pagamento: str
    estado: str
    pago_em: datetime
    total_centavos: int


def resumir_por_forma(
    vendas: Iterable[VendaPaga],
    *,
    de: date,
    ate: date,
    tarifa_cartao_bps: int,
    tarifa_pix_bps: int,
) -> dict[str, dict[str, int]]:
    """Quanto entrou por Pix, cartão e Pix manual no período, com a taxa estimada.

    Conta o pedido na data do pagamento e só nos estados vendidos; venda lançada no painel
    (forma `externo`) fica fora. Parcelado usa a tarifa do à vista: o juros é do cliente."""
    tarifas = {"pix": tarifa_pix_bps, "cartao": tarifa_cartao_bps, "pix_manual": 0}
    saida = {f: {"pedidos": 0, "valor_centavos": 0, "taxa_estimada_centavos": 0} for f in FORMAS}
    for v in vendas:
        if v.forma_pagamento not in saida or v.estado not in ESTADOS_VENDIDOS:
            continue
        if not de <= v.pago_em.astimezone(FUSO).date() <= ate:
            continue
        linha = saida[v.forma_pagamento]
        linha["pedidos"] += 1
        linha["valor_centavos"] += v.total_centavos
    for forma, linha in saida.items():
        linha["taxa_estimada_centavos"] = taxa_estimada_centavos(
            linha["valor_centavos"], tarifas[forma]
        )
    return saida
