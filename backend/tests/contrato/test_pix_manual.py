"""Adaptador pix_manual: cobrança com valor exato e txid do pedido."""

import pytest

from app.adaptadores.pix_manual import PixManual
from app.dominio.pix import crc16
from app.portas.pagamento import PagamentoNaoConfigurado, ProvedorDePagamento


def test_cobranca_com_valor_exato_e_txid_do_pedido():
    pix = PixManual(chave="12345678000195", nome="DOCE ATELIE", cidade="CAMPINAS")
    assert isinstance(pix, ProvedorDePagamento)
    c = pix.cobrar(42, 5380)
    assert c.txid == "DA42"
    assert "540553.80" in c.copia_e_cola and "0504DA42" in c.copia_e_cola
    assert c.copia_e_cola[-4:] == crc16(c.copia_e_cola[:-4])


def test_sem_chave_nao_cobra():
    with pytest.raises(PagamentoNaoConfigurado):
        PixManual(chave="", nome="DOCE ATELIE", cidade="CAMPINAS").cobrar(1, 100)
