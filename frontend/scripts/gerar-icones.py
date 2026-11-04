"""Gera os ícones PNG do PWA (doce em camadas sobre fundo creme), sem dependências.

    python3 scripts/gerar-icones.py

A marca é provisória; troque os arquivos de public/icones por arte própria quando houver.
"""

import struct
import zlib
from pathlib import Path

CREME, CARAMELO, DOURADO, CEREJA = (245, 238, 220), (149, 59, 26), (217, 139, 74), (179, 38, 30)
DESTINO = Path(__file__).resolve().parents[1] / "public" / "icones"


def desenhar(tamanho: int, margem: float) -> bytes:
    """Fundo creme cheio; o doce ocupa (1 - 2 * margem) do lado. Maskable usa margem maior."""
    linhas = []
    escala = tamanho * (1 - 2 * margem) / 96
    deslocar = tamanho * margem
    for y in range(tamanho):
        linha = bytearray([0])
        for x in range(tamanho):
            u, v = (x - deslocar) / escala, (y - deslocar) / escala  # coordenadas 0..96
            cor = CREME
            if 22 <= u <= 74 and 54 <= v <= 83 and abs(u - 48) <= 26 - (v - 54) * 0.17:
                cor = CARAMELO  # copo
            elif (u - 48) ** 2 / 22**2 + (v - 54) ** 2 / 24**2 <= 1 and v <= 54:
                cor = DOURADO  # cúpula
            if (u - 48) ** 2 + (v - 24) ** 2 <= 25:
                cor = CEREJA
            linha += bytes(cor)
        linhas.append(bytes(linha))
    return b"".join(linhas)


def png(tamanho: int, margem: float) -> bytes:
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo))

    cabecalho = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", cabecalho)
        + bloco(b"IDAT", zlib.compress(desenhar(tamanho, margem), 9))
        + bloco(b"IEND", b"")
    )


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, tamanho, margem in [
        ("icone-192.png", 192, 0.06),
        ("icone-512.png", 512, 0.06),
        ("icone-maskable-512.png", 512, 0.2),
        ("apple-touch-icon.png", 180, 0.06),
    ]:
        (DESTINO / nome).write_bytes(png(tamanho, margem))
        print("gerado", nome)
