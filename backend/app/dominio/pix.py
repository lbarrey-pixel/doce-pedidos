"""Pix copia e cola estático (BR Code), padrão EMV do Banco Central.

Gerado localmente, sem intermediário: a loja recebe direto na própria chave e confirma o
pagamento no painel. Campos: 00 formato, 26 merchant account (GUI + chave), 52 MCC, 53 moeda,
54 valor, 58 país, 59 nome, 60 cidade, 62 txid, 63 CRC16.
"""

import re

_TXID = re.compile(r"[A-Za-z0-9]{1,25}")
_ASCII = re.compile(r"[ -~]+")


def crc16(dados: str) -> str:
    """CRC-16/CCITT-FALSE (polinômio 0x1021, inicial 0xFFFF), 4 hex maiúsculos."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _campo(id_: str, valor: str) -> str:
    if len(valor) > 99:
        raise ValueError(f"campo {id_} com mais de 99 caracteres")
    return f"{id_}{len(valor):02d}{valor}"


def _texto(nome: str, valor: str, limite: int) -> str:
    if not valor or len(valor) > limite or not _ASCII.fullmatch(valor):
        raise ValueError(f"{nome} precisa ter de 1 a {limite} caracteres sem acento")
    return valor


def gerar_copia_e_cola(
    *,
    chave: str,
    nome: str,
    cidade: str,
    valor_centavos: int | None = None,
    txid: str = "***",
) -> str:
    """Monta o BR Code estático. Sem valor, o pagador digita; txid `***` quando não usado."""
    _texto("chave", chave, 77)
    _texto("nome", nome, 25)
    _texto("cidade", cidade, 15)
    if txid != "***" and not _TXID.fullmatch(txid):
        raise ValueError("txid só aceita letras e dígitos, até 25, ou ***")

    payload = _campo("00", "01")
    payload += _campo("26", _campo("00", "br.gov.bcb.pix") + _campo("01", chave))
    payload += _campo("52", "0000") + _campo("53", "986")
    if valor_centavos is not None:
        if not isinstance(valor_centavos, int) or isinstance(valor_centavos, bool):
            raise ValueError("valor em centavos inteiros")
        if valor_centavos <= 0:
            raise ValueError("valor precisa ser positivo")
        payload += _campo("54", f"{valor_centavos // 100}.{valor_centavos % 100:02d}")
    payload += _campo("58", "BR") + _campo("59", nome) + _campo("60", cidade)
    payload += _campo("62", _campo("05", txid))
    payload += "6304"
    return payload + crc16(payload)
