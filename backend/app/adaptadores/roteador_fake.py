"""Roteador em memória para desenvolvimento local e testes: sem rede, sem chave de API.

Cada CEP conhecido tem uma distância fixa até a loja; o número "sem-numero" simula um
endereço que o mapa não encontra. As coordenadas são sintéticas: a longitude carrega a
distância, e a distância entre dois pontos sai da diferença de longitude.
"""

from app.portas.roteador import Coordenadas, Endereco

BASE_LATITUDE = -22.9
BASE_LONGITUDE = -47.0


class RoteadorFake:
    def __init__(self, distancias: dict[str, int] | None = None) -> None:
        self.distancias = distancias or {
            "12345678": 5000,
            "12000001": 2000,
            "99999999": 13000,
        }

    def endereco_do_cep(self, cep: str) -> Endereco | None:
        digitos = "".join(c for c in cep if c.isdigit())
        if digitos not in self.distancias:
            return None
        return Endereco(digitos, "R. das Acácias", "Jardim Azul", "Campinas", "SP")

    def geocodificar(self, endereco: Endereco, numero: str) -> Coordenadas | None:
        if numero == "sem-numero":
            return None
        return Coordenadas(BASE_LATITUDE, BASE_LONGITUDE - self.distancias[endereco.cep] / 1e6)

    def distancia_metros(self, origem: Coordenadas, destino: Coordenadas) -> int:
        return round((BASE_LONGITUDE - destino.longitude) * 1e6)
