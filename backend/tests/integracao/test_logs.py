"""Nenhum log com dado do cliente.

Percorre o caminho que mais carrega dado pessoal (reconhecer, cotar, pedir, confirmar, mapa
fora do ar) com o log no nível mais baixo e procura nome, telefone, endereço e CPF.
"""

import logging

from tests.integracao.apoio import pedir, produzir, vid

NOME, SOBRENOME = "Marina", "Figueiredo"
TELEFONE = "11900000006"
CPF = "00000000000"
NUMERO_DA_CASA = "4321"
COMPLEMENTO = "apto 908 bloco Z"
CLIENTE = {"nome": f"{NOME} {SOBRENOME}", "telefone": "(11) 90000-0006", "cpf": "000.000.000-00"}
PROIBIDOS = (NOME, SOBRENOME, TELEFONE, "90000-0006", CPF, "000.000", COMPLEMENTO, "12345")


class MapaFora:
    def endereco_do_cep(self, cep):
        raise RuntimeError("brasilapi: HTTP 503")


def test_nenhum_log_com_dado_do_cliente(mundo, engine, caplog):
    loja, painel = mundo
    caplog.set_level(logging.DEBUG)
    doce = vid(engine)
    produzir(painel, doce, 3)
    loja.post("/api/v1/loja/cliente/reconhecer", json={"telefone": TELEFONE, "nome": NOME})
    endereco = {"cep": "12345-678", "numero": NUMERO_DA_CASA, "complemento": COMPLEMENTO}
    loja.post("/api/v1/loja/entrega/cotacao", json=endereco)
    p = pedir(loja, doce, qtd=1, cliente=CLIENTE, endereco=endereco).json()
    painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": p["total_centavos"]},
    )
    painel.get("/api/v1/painel/pedidos")
    pedir(loja, doce, qtd=1, cliente=CLIENTE | {"telefone": "x"})  # 422 de validação
    loja.app.state.roteador = MapaFora()
    r = pedir(loja, doce, qtd=1, cliente=CLIENTE, endereco=endereco)
    assert r.status_code == 503  # o caminho do log de aviso foi exercitado

    assert caplog.records, "o teste precisa ver algum log para valer"
    texto = "\n".join(f"{r.name} {r.getMessage()} {r.args}" for r in caplog.records)
    vazou = [p for p in PROIBIDOS if p.lower() in texto.lower()]
    assert vazou == [], f"dado do cliente no log: {vazou}"


def test_access_log_do_uvicorn_nao_mostra_o_codigo_do_aviso(caplog):
    import app.main  # noqa: F401  (instala o filtro do access log)

    caplog.set_level(logging.INFO, logger="uvicorn.access")
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:5000",
        "POST",
        "/api/v1/gateway/checkout/aviso?c=codigo-secreto-123",
        "1.1",
        200,
    )
    assert "codigo-secreto-123" not in caplog.text
    assert "/api/v1/gateway/checkout/aviso" in caplog.text
