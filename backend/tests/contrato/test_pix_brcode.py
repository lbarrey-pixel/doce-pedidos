"""Contrato do Pix copia e cola (contracts/pix-brcode.md), valores do manual do Banco Central."""

import pytest

from app.dominio.pix import crc16, gerar_copia_e_cola

EXEMPLO_263 = (
    "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-426655440000"
    "5204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D"
)
CHAVE = "123e4567-e12b-12d1-a456-426655440000"


def test_crc_de_verificacao_padrao():
    assert crc16("123456789") == "29B1"


def test_exemplo_estatico_do_manual_263():
    codigo = gerar_copia_e_cola(chave=CHAVE, nome="Fulano de Tal", cidade="BRASILIA")
    assert codigo == EXEMPLO_263
    assert len(codigo) == 137


def test_valor_de_100_50_vira_campo_54():
    codigo = gerar_copia_e_cola(
        chave=CHAVE, nome="Fulano de Tal", cidade="BRASILIA", valor_centavos=10050
    )
    assert "5303986" + "5406100.50" + "5802BR" in codigo
    assert codigo[-4:] == crc16(codigo[:-4])


def test_valor_de_um_pedido_real():
    codigo = gerar_copia_e_cola(
        chave=CHAVE, nome="DOCE ATELIE", cidade="CAMPINAS", valor_centavos=5380, txid="DA123"
    )
    assert "540553.80" in codigo
    assert "62090505DA123" in codigo


@pytest.mark.parametrize("txid", ["DP-1", "D P1", "Ç1", "A" * 26, ""])
def test_txid_invalido_e_recusado(txid):
    with pytest.raises(ValueError):
        gerar_copia_e_cola(chave=CHAVE, nome="X", cidade="Y", txid=txid)


def test_txid_de_25_caracteres_e_aceito():
    codigo = gerar_copia_e_cola(chave=CHAVE, nome="X", cidade="Y", txid="D" * 25)
    assert "6229" + "0525" + "D" * 25 in codigo


@pytest.mark.parametrize("campo", [{"nome": "N" * 26}, {"cidade": "C" * 16}, {"chave": ""}])
def test_limites_de_tamanho(campo):
    args = {"chave": CHAVE, "nome": "Nome", "cidade": "Cidade"} | campo
    with pytest.raises(ValueError):
        gerar_copia_e_cola(**args)


@pytest.mark.parametrize("valor", [0, -1, 10.5])
def test_valor_precisa_ser_centavos_positivos(valor):
    with pytest.raises(ValueError):
        gerar_copia_e_cola(chave=CHAVE, nome="X", cidade="Y", valor_centavos=valor)
