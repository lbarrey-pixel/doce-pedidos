"""Mensagem do pedido para o WhatsApp da loja."""

import re
from datetime import datetime
from urllib.parse import quote

from app.dominio.dinheiro import formatar
from app.dominio.horario import FUSO


def mensagem_do_pedido(
    *,
    numero: int,
    itens: list[tuple[str, int]],
    cliente_nome: str,
    telefone: str,
    endereco: str | None,
    total_centavos: int,
    entrega_a_partir_de: datetime,
    observacao: str | None = None,
) -> str:
    quando = entrega_a_partir_de.astimezone(FUSO)
    linhas = [
        f"Pedido nº {numero} — Doce Ateliê",
        *(f"{q}× {nome}" for nome, q in itens),
        f"Cliente: {cliente_nome} · {telefone}",
        f"Entrega: {endereco}" if endereco else "Retirada na loja",
        f"Total: {formatar(total_centavos)} (Pix)",
        f"A partir de {quando:%d/%m} às {quando.hour}h{quando.minute:02d}",
    ]
    if observacao:
        linhas.append(f"Obs.: {observacao}")
    return "\n".join(linhas)


def url_whatsapp(numero: str, texto: str) -> str:
    digitos = re.sub(r"\D", "", numero)
    return f"https://wa.me/{digitos}?text={quote(texto)}"
