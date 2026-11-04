"""Roteador real (ADR 0002): CEP pela BrasilAPI; endereço e rota de carro pelo Google.

Endereço só conta com precisão de número (ROOFTOP ou RANGE_INTERPOLATED, sem partial_match);
rua ou bairro aproximado vira "não encontrado" e o App encaminha ao WhatsApp.
A Geocoding API recebe a chave na URL: nada de URL em log ou mensagem de erro.
"""

import logging
import re

import httpx

from app.portas.roteador import Coordenadas, Endereco

BRASILAPI = "https://brasilapi.com.br/api"
GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
ROTAS = "https://routes.googleapis.com/directions/v2:computeRoutes"
TEMPO_LIMITE_S = 10
PRECISAO_DE_NUMERO = {"ROOFTOP", "RANGE_INTERPOLATED"}
log = logging.getLogger("doce.mapa")


def _motivo(servico: str, e: httpx.HTTPError) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"{servico}: HTTP {e.response.status_code}"
    return f"{servico}: {type(e).__name__}"


class RoteadorGoogle:
    def __init__(self, chave: str, cliente: httpx.Client | None = None) -> None:
        self._chave = chave
        self._http = cliente or httpx.Client(timeout=TEMPO_LIMITE_S)

    def endereco_do_cep(self, cep: str) -> Endereco | None:
        digitos = re.sub(r"\D", "", cep)
        if len(digitos) != 8:
            return None
        try:
            r = self._http.get(f"{BRASILAPI}/cep/v2/{digitos}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            d = r.json()
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"não deu para consultar o CEP ({_motivo('brasilapi', e)})"
            ) from None
        return Endereco(
            cep=digitos,
            logradouro=d.get("street") or "",
            bairro=d.get("neighborhood") or "",
            cidade=d.get("city") or "",
            uf=d.get("state") or "",
        )

    def geocodificar(self, endereco: Endereco, numero: str) -> Coordenadas | None:
        cep = f"{endereco.cep[:5]}-{endereco.cep[5:]}"
        try:
            r = self._http.get(
                GEOCODE,
                params={
                    "address": f"{endereco.logradouro}, {numero}, {endereco.bairro}, "
                    f"{endereco.cidade} - {endereco.uf}",
                    "components": f"country:BR|postal_code:{cep}",
                    "language": "pt-BR",
                    "region": "br",
                    "key": self._chave,
                },
            )
            r.raise_for_status()
            dados = r.json()
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"não deu para consultar o mapa ({_motivo('google-geocode', e)})"
            ) from None
        status = dados.get("status")
        if status == "ZERO_RESULTS":
            return None
        if status != "OK":
            raise RuntimeError(f"não deu para consultar o mapa (google-geocode: {status})")
        achado = dados["results"][0]
        tipo = achado["geometry"].get("location_type")
        tem_numero = any("street_number" in c["types"] for c in achado["address_components"])
        if tipo not in PRECISAO_DE_NUMERO or achado.get("partial_match") or not tem_numero:
            # Só a precisão: nada do endereço do cliente vai para o log.
            log.info(
                "geocode sem número: tipo=%s parcial=%s numero=%s",
                tipo,
                bool(achado.get("partial_match")),
                tem_numero,
            )
            return None
        pos = achado["geometry"]["location"]
        return Coordenadas(latitude=pos["lat"], longitude=pos["lng"])

    def distancia_metros(self, origem: Coordenadas, destino: Coordenadas) -> int:
        def ponto(c: Coordenadas) -> dict:
            return {"location": {"latLng": {"latitude": c.latitude, "longitude": c.longitude}}}

        try:
            r = self._http.post(
                ROTAS,
                headers={
                    "X-Goog-Api-Key": self._chave,
                    "X-Goog-FieldMask": "routes.distanceMeters",
                },
                json={
                    "origin": ponto(origem),
                    "destination": ponto(destino),
                    "travelMode": "DRIVE",
                },
            )
            r.raise_for_status()
            # O Google omite distanceMeters quando é 0 (origem e destino no mesmo ponto).
            return int(r.json()["routes"][0].get("distanceMeters", 0))
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"não deu para calcular a rota ({_motivo('google-rota', e)})"
            ) from None
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("não deu para calcular a rota (resposta sem rota)") from None
