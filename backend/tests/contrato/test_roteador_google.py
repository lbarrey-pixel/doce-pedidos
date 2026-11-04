"""Adaptador de CEP (BrasilAPI) e endereço e rota (Google Maps Platform) — ADR 0014.

Sem rede: respx intercepta o httpx. Formatos conforme a documentação pública da Geocoding API
e da Routes API (computeRoutes).
"""

import httpx
import pytest
import respx

from app.adaptadores.roteador_google import BRASILAPI, GEOCODE, ROTAS, RoteadorGoogle
from app.portas.roteador import Coordenadas, Endereco, Roteador

CEP = {
    "cep": "12345678",
    "state": "SP",
    "city": "Campinas",
    "neighborhood": "Vila Nova",
    "street": "Rua das Acácias",
}
ENDERECO = Endereco("12345678", "Rua das Acácias", "Vila Nova", "Campinas", "SP")


def geocode(tipo="ROOFTOP", parcial=False, numero=True, status="OK"):
    componentes = [{"long_name": "Rua das Acácias", "types": ["route"]}]
    if numero:
        componentes.insert(0, {"long_name": "150", "types": ["street_number"]})
    resultado = {
        "address_components": componentes,
        "geometry": {"location": {"lat": -22.9071, "lng": -47.0632}, "location_type": tipo},
        "types": ["street_address"],
    }
    if parcial:
        resultado["partial_match"] = True
    return {"status": status, "results": [resultado] if status == "OK" else []}


@pytest.fixture
def roteador():
    return RoteadorGoogle(chave="segredo-de-teste", cliente=httpx.Client())


def test_cumpre_a_porta(roteador):
    assert isinstance(roteador, Roteador)


@respx.mock
def test_cep(roteador):
    respx.get(f"{BRASILAPI}/cep/v2/12345678").respond(json=CEP)
    respx.get(f"{BRASILAPI}/cep/v2/99999999").respond(404, json={})
    assert roteador.endereco_do_cep("12345-678") == ENDERECO
    assert roteador.endereco_do_cep("99999-999") is None
    assert roteador.endereco_do_cep("123") is None


@respx.mock
@pytest.mark.parametrize("tipo", ["ROOFTOP", "RANGE_INTERPOLATED"])
def test_endereco_com_precisao_de_numero(roteador, tipo):
    rota = respx.get(GEOCODE).respond(json=geocode(tipo))
    assert roteador.geocodificar(ENDERECO, "150") == Coordenadas(-22.9071, -47.0632)
    params = rota.calls.last.request.url.params
    assert "150" in params["address"] and "Campinas" in params["address"]
    assert params["components"] == "country:BR|postal_code:12345-678"
    assert params["language"] == "pt-BR"


@respx.mock
@pytest.mark.parametrize(
    "resposta",
    [
        geocode("GEOMETRIC_CENTER"),
        geocode("APPROXIMATE"),
        geocode(parcial=True),
        geocode(numero=False),
        geocode(status="ZERO_RESULTS"),
    ],
)
def test_sem_numero_exato_nao_estima(roteador, resposta):
    """Sem o número da casa, o App encaminha ao WhatsApp."""
    respx.get(GEOCODE).respond(json=resposta)
    assert roteador.geocodificar(ENDERECO, "150") is None


@respx.mock
@pytest.mark.parametrize("status", ["REQUEST_DENIED", "OVER_QUERY_LIMIT", "INVALID_REQUEST"])
def test_chave_ou_cota_viram_erro_claro_sem_a_chave(roteador, status):
    respx.get(GEOCODE).respond(json={"status": status, "results": []})
    with pytest.raises(RuntimeError, match=f"google-geocode: {status}") as e:
        roteador.geocodificar(ENDERECO, "150")
    assert "segredo" not in str(e.value) and e.value.__cause__ is None


@respx.mock
def test_distancia_de_carro_em_metros(roteador):
    rota = respx.post(ROTAS).respond(json={"routes": [{"distanceMeters": 5021}]})
    assert (
        roteador.distancia_metros(Coordenadas(-22.90, -47.06), Coordenadas(-22.86, -47.03)) == 5021
    )
    pedido = rota.calls.last.request
    assert pedido.headers["X-Goog-Api-Key"] == "segredo-de-teste"
    assert pedido.headers["X-Goog-FieldMask"] == "routes.distanceMeters"
    assert "segredo" not in str(pedido.url)
    corpo = pedido.read().decode()
    assert '"travelMode":"DRIVE"' in corpo.replace(" ", "")


@respx.mock
@pytest.mark.parametrize("resposta", [httpx.Response(403), httpx.Response(200, json={})])
def test_sem_rota_vira_erro_claro(roteador, resposta):
    respx.post(ROTAS).mock(return_value=resposta)
    with pytest.raises(RuntimeError, match="rota"):
        roteador.distancia_metros(Coordenadas(0, 0), Coordenadas(1, 1))


@respx.mock
def test_falha_da_brasilapi(roteador):
    respx.get(f"{BRASILAPI}/cep/v2/12345678").respond(500)
    with pytest.raises(RuntimeError, match="CEP"):
        roteador.endereco_do_cep("12345678")


@respx.mock
def test_distancia_zero_vem_sem_o_campo(roteador):
    """O Google omite distanceMeters quando é 0 (mesmo ponto): é 0, não falha."""
    respx.post(ROTAS).respond(json={"routes": [{}]})
    assert roteador.distancia_metros(Coordenadas(-22.90, -47.06), Coordenadas(-22.90, -47.06)) == 0
