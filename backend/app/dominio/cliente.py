"""Reconhecimento do cliente por telefone e primeiro nome, sem conta nem senha.

O app devolve só o endereço mascarado do último pedido; o endereço completo nunca sai da API
antes de o cliente confirmar que quer usá-lo.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

TIPOS_DE_LOGRADOURO = {
    "r",
    "rua",
    "av",
    "avenida",
    "tv",
    "travessa",
    "al",
    "alameda",
    "estr",
    "estrada",
    "pc",
    "praca",
    "praça",
    "rod",
    "rodovia",
    "beco",
    "largo",
}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def chave(telefone: str, nome: str) -> tuple[str, str]:
    """(telefone só com dígitos, primeiro nome sem maiúscula, acento e espaços)."""
    partes = nome.split()
    primeiro = _sem_acento(partes[0]).lower() if partes else ""
    return re.sub(r"\D", "", telefone), primeiro


def mascarar(endereco: dict) -> str:
    """Duas primeiras letras do logradouro e o primeiro dígito do número; bairro à vista."""
    palavras = endereco.get("logradouro", "").split()
    i = 1 if palavras and palavras[0].rstrip(".").lower() in TIPOS_DE_LOGRADOURO else 0
    if i < len(palavras):
        palavras[i] = palavras[i][:2] + "•••"
    numero = str(endereco.get("numero", ""))
    numero = numero[:1] + "•" * (len(numero) - 1) if numero else ""
    partes = [" ".join(palavras), numero, endereco.get("bairro", "")]
    return ", ".join(p for p in partes if p)


@dataclass(frozen=True)
class Anterior:
    telefone: str
    nome: str
    endereco: dict
    criado_em: datetime


def endereco_reconhecido(anteriores: list[Anterior], telefone: str, nome: str) -> dict | None:
    """Endereço do último pedido daquele telefone com aquele primeiro nome; outro nome no mesmo
    telefone é outra pessoa e não recebe nada."""
    alvo = chave(telefone, nome)
    if not all(alvo):
        return None
    meus = [a for a in anteriores if chave(a.telefone, a.nome) == alvo and a.endereco]
    return max(meus, key=lambda a: a.criado_em).endereco if meus else None
