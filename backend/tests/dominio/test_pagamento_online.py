"""Regra pura de confirmação do pagamento online (`decidir`) e do resumo por forma.

Exemplo: 2 bolos de pote (R$ 39,80) + entrega de R$ 14,00, total R$ 53,80. Dinheiro em
centavos inteiros.
"""

from datetime import UTC, date, datetime

import pytest

from app.dominio.pagamento_online import (
    Resultado,
    Situacao,
    VendaPaga,
    decidir,
    forma_do_pagamento,
    resumir_por_forma,
    taxa_estimada_centavos,
)
from app.portas.pagamento import Conferencia

TOTAL = 5380


def conferencia(**mudanca) -> Conferencia:
    base = {
        "success": True,
        "paid": True,
        "amount": TOTAL,
        "paid_amount": TOTAL,
        "installments": 1,
        "capture_method": "pix",
    }
    return Conferencia(**(base | mudanca))


def decisao(situacao=Situacao.AGUARDANDO, *, ja_registrado=False, conf=None) -> Resultado:
    return decidir(
        situacao=situacao,
        total_centavos=TOTAL,
        nsu_ja_registrado=ja_registrado,
        conferencia=conf or conferencia(),
    )


# --- tabela de `decidir`, uma linha por teste ---------------------------------------------


@pytest.mark.parametrize("campo", ["success", "paid"])
def test_gateway_que_nao_confirma_vira_nao_confirmado(campo):
    assert decisao(conf=conferencia(**{campo: False})) is Resultado.NAO_CONFIRMADO


def test_nao_confirmado_vem_antes_de_qualquer_outra_regra():
    conf = conferencia(paid=False, amount=1)  # valor errado, mas o gateway nem confirma
    assert decisao(Situacao.PAGO, ja_registrado=True, conf=conf) is Resultado.NAO_CONFIRMADO


def test_valor_recusado_quando_amount_difere_do_total():
    assert (
        decisao(conf=conferencia(amount=TOTAL - 1, paid_amount=TOTAL)) is Resultado.VALOR_RECUSADO
    )
    assert decisao(conf=conferencia(amount=TOTAL + 1, paid_amount=TOTAL + 1)) is (
        Resultado.VALOR_RECUSADO
    )


def test_valor_recusado_quando_pago_menor_que_cobrado():
    assert decisao(conf=conferencia(paid_amount=TOTAL - 1)) is Resultado.VALOR_RECUSADO


def test_pago_maior_que_cobrado_e_aceito_no_cartao_por_causa_dos_juros():
    conf = conferencia(paid_amount=5660, installments=3, capture_method="credit_card")
    assert decisao(conf=conf) is Resultado.CONFIRMADO


def test_valor_recusado_nao_muda_o_pedido_nem_com_pedido_expirado():
    conf = conferencia(paid_amount=TOTAL - 1)
    assert decisao(Situacao.EXPIRADO, conf=conf) is Resultado.VALOR_RECUSADO


def test_pix_com_valor_pago_maior_que_o_cobrado_nao_confirma():
    conf = conferencia(paid_amount=TOTAL + 10, capture_method="pix", installments=1)
    assert decisao(conf=conf) is Resultado.VALOR_RECUSADO


def test_mesmo_nsu_ja_registrado_vira_repetido():
    assert decisao(Situacao.PAGO, ja_registrado=True) is Resultado.REPETIDO


def test_repetido_vem_depois_do_valor():
    assert decisao(ja_registrado=True, conf=conferencia(amount=1)) is Resultado.VALOR_RECUSADO


def test_pedido_aguardando_confirma():
    assert decisao(Situacao.AGUARDANDO) is Resultado.CONFIRMADO


def test_pedido_expirado_vira_pago_depois_de_expirar():
    assert decisao(Situacao.EXPIRADO) is Resultado.PAGO_DEPOIS_DE_EXPIRAR


def test_pago_depois_de_cancelado_pelo_operador_fica_a_estornar():
    assert decisao(Situacao.CANCELADO_PELO_OPERADOR) is Resultado.A_ESTORNAR


def test_segundo_pagamento_de_pedido_ja_pago_fica_a_estornar():
    assert decisao(Situacao.PAGO) is Resultado.A_ESTORNAR


# --- forma do pagamento -------------------------------------------------------------------


def test_forma_pix():
    assert forma_do_pagamento(conferencia()) == ("pix", "pix", 1)


def test_forma_cartao_a_vista():
    conf = conferencia(capture_method="credit_card", installments=1)
    assert forma_do_pagamento(conf) == ("cartao", "credit_card", 1)


def test_forma_cartao_parcelado_em_3x():
    conf = conferencia(capture_method="credit_card", installments=3)
    assert forma_do_pagamento(conf) == ("cartao", "credit_card", 3)


def test_forma_parcelas_invalidas_viram_a_vista():
    assert forma_do_pagamento(conferencia(installments=0))[2] == 1


# --- taxa estimada ------------------------------------------------------------------------


def test_taxa_estimada_420_bps_de_5380_e_226():
    assert taxa_estimada_centavos(5380, 420) == 226


def test_taxa_estimada_pix_gratis():
    assert taxa_estimada_centavos(5380, 0) == 0


def test_taxa_estimada_arredonda_para_o_centavo_mais_proximo():
    assert taxa_estimada_centavos(1000, 420) == 42  # 42,0
    assert taxa_estimada_centavos(1190, 420) == 50  # 49,98


# --- resumo por forma ---------------------------------------------------------------------


def venda(forma, total, estado="pago", dia=2) -> VendaPaga:
    return VendaPaga(forma, estado, datetime(2026, 11, dia, 15, 0, tzinfo=UTC), total)


def test_resumo_separa_pix_cartao_e_pix_manual_com_taxa():
    vendas = [
        venda("pix", 5380),
        venda("cartao", 5380),
        venda("cartao", 2000),
        venda("pix_manual", 3000),
        venda("externo", 9999),  # venda lançada no painel fica fora
        venda("cartao", 7777, estado="cancelado"),  # cancelado não conta
        venda("cartao", 1111, dia=9),  # fora do período
    ]
    r = resumir_por_forma(
        vendas,
        de=date(2026, 11, 2),
        ate=date(2026, 11, 8),
        tarifa_cartao_bps=420,
        tarifa_pix_bps=0,
    )
    assert r["pix"] == {"pedidos": 1, "valor_centavos": 5380, "taxa_estimada_centavos": 0}
    assert r["cartao"] == {"pedidos": 2, "valor_centavos": 7380, "taxa_estimada_centavos": 310}
    assert r["pix_manual"] == {"pedidos": 1, "valor_centavos": 3000, "taxa_estimada_centavos": 0}
    assert set(r) == {"pix", "cartao", "pix_manual"}


def test_resumo_sem_vendas_traz_as_tres_formas_zeradas():
    r = resumir_por_forma(
        [], de=date(2026, 11, 2), ate=date(2026, 11, 8), tarifa_cartao_bps=420, tarifa_pix_bps=0
    )
    zero = {"pedidos": 0, "valor_centavos": 0, "taxa_estimada_centavos": 0}
    assert r == {"pix": zero, "cartao": zero, "pix_manual": zero}


def test_resumo_usa_a_data_local_do_pagamento():
    # 01:30 UTC de 3/11 ainda é 2/11 à noite no fuso da loja
    tarde = VendaPaga("pix", "pago", datetime(2026, 11, 3, 1, 30, tzinfo=UTC), 1000)
    r = resumir_por_forma(
        [tarde], de=date(2026, 11, 2), ate=date(2026, 11, 2), tarifa_cartao_bps=0, tarifa_pix_bps=0
    )
    assert r["pix"]["pedidos"] == 1
