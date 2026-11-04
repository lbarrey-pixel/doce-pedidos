"""Porta Roteador: CEP, coordenadas e distância por rota de rua (ADR 0002)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Coordenadas:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Endereco:
    cep: str
    logradouro: str
    bairro: str
    cidade: str
    uf: str


@runtime_checkable
class Roteador(Protocol):
    def endereco_do_cep(self, cep: str) -> Endereco | None: ...

    def geocodificar(self, endereco: Endereco, numero: str) -> Coordenadas | None:
        """None quando o endereço não é encontrado: o App pede correção, sem estimar."""
        ...

    def distancia_metros(self, origem: Coordenadas, destino: Coordenadas) -> int:
        """Rota de carro, em metros inteiros."""
        ...
