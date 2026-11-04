"""API da loja e pedidos no painel: pedido com Pix, expiração, Encomenda e reconhecimento."""

from datetime import datetime, timedelta

from sqlalchemy import text

from tests.integracao.apoio import ANA, FUSO, TARDE, pedir, produzir, saldo, vid


def test_cardapio_publico_com_disponibilidade(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 5)
    corpo = loja.get("/api/v1/loja/cardapio").json()
    assert corpo["loja_aberta"] is True and corpo["pedido_minimo_centavos"] == 800
    itens = [i for c in corpo["categorias"] for i in c["variantes"]]
    doce = next(i for i in itens if i["id"] == v)
    assert (doce["estado_disponibilidade"], doce["pronta"], doce["preco_centavos"]) == (
        "pronta_entrega",
        5,
        1990,
    )
    assert next(i for i in itens if i["id"] != v)["estado_disponibilidade"] == "encomenda"


def test_cotacao_e_recusas_de_endereco(mundo):
    loja, _ = mundo
    r = loja.post("/api/v1/loja/entrega/cotacao", json={"cep": "12345-678", "numero": "220"})
    assert r.json()["taxa_entrega_centavos"] == 1400 and r.json()["distancia_m"] == 5000
    r = loja.post("/api/v1/loja/entrega/cotacao", json={"cep": "13000-013", "numero": "1"})
    assert r.status_code == 422 and r.json()["erro"] == "sob_consulta"
    assert r.json()["whatsapp_url"].startswith("https://wa.me/5511988887777")
    r = loja.post("/api/v1/loja/entrega/cotacao", json={"cep": "12345-678", "numero": "sem-numero"})
    assert r.json()["erro"] == "endereco_nao_encontrado" and "whatsapp_url" in r.json()


def test_pedido_pix_e_confirmacao(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 5)
    r = pedir(loja, v)
    assert r.status_code == 201
    p = r.json()
    assert (p["subtotal_centavos"], p["taxa_entrega_centavos"], p["total_centavos"]) == (
        3980,
        1400,
        5380,
    )
    assert p["estado"] == "aguardando_pagamento" and "540553.80" in p["pix"]["copia_e_cola"]
    assert p["whatsapp_url"].startswith("https://wa.me/5511988887777?text=")
    assert (saldo(painel, v)["pronta"], saldo(painel, v)["separada"]) == (3, 2)
    acompanhar = loja.get(f"/api/v1/loja/pedidos/{p['id']}").json()
    assert acompanhar["pix"]["copia_e_cola"] == p["pix"]["copia_e_cola"]  # recarregar a página
    novos = painel.get("/api/v1/painel/pedidos").json()["pedidos"]
    assert novos[0]["numero"] == p["numero"] and novos[0]["cliente"]["nome"] == ANA["nome"]
    r = painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": 5380},
    )
    assert r.status_code == 200 and r.json()["estado"] == "pago"
    assert (saldo(painel, v)["pronta"], saldo(painel, v)["separada"]) == (3, 0)
    depois = loja.get(f"/api/v1/loja/pedidos/{p['id']}").json()
    assert depois["estado"] == "pago" and depois["pix"] is None


def test_valor_diferente_recusado_ou_aceito_com_diferenca(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 5)
    p = pedir(loja, v).json()
    url = f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento"
    r = painel.post(url, json={"valor_recebido_centavos": 5300})
    assert r.status_code == 422 and r.json()["erro"] == "valor_divergente"
    assert r.json()["esperado_centavos"] == 5380
    r = painel.post(url, json={"valor_recebido_centavos": 5300, "aceitar_diferenca": True})
    assert r.json()["estado"] == "pago" and r.json()["diferenca_pagamento_centavos"] == -80


def test_expira_em_30_min_e_confirmacao_tardia(mundo, engine, relogio):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 2)
    a = pedir(loja, v, qtd=1).json()
    b = pedir(loja, v, qtd=1).json()
    relogio.agora = TARDE + timedelta(minutes=30)
    assert loja.get(f"/api/v1/loja/pedidos/{a['id']}").json()["estado"] == "cancelado"
    assert saldo(painel, v)["pronta"] == 2  # as duas voltaram
    # a pagou e o operador confirma depois de expirar: ainda há unidade, separa de novo
    r = painel.post(
        f"/api/v1/painel/pedidos/{a['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": a["total_centavos"]},
    )
    assert r.json()["estado"] == "pago" and saldo(painel, v)["pronta"] == 1
    baixa = painel.post(
        "/api/v1/painel/estoque/movimentos",
        json={
            "variante_id": v,
            "tipo": "perda",
            "quantidade": 1,
            "de_estado": "pronta",
            "motivo": "caiu",
        },
    )
    assert baixa.status_code == 200
    r = painel.post(
        f"/api/v1/painel/pedidos/{b['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": b["total_centavos"]},
    )
    assert r.status_code == 409 and r.json()["erro"] == "unidade_indisponivel"


def test_loja_fechada_aceita_so_encomenda(mundo, engine, relogio):
    loja, _ = mundo
    relogio.agora = datetime(2026, 11, 3, 0, 30, tzinfo=FUSO)
    v = vid(engine, "Torta de Limão", "Inteira")
    r = pedir(loja, v, qtd=1)
    assert r.status_code == 422 and r.json()["erro"] == "loja_fechada"
    assert r.json()["primeira_encomenda"] == "2026-11-03T12:30:00-03:00"
    r = pedir(loja, v, qtd=1, tipo_entrega="encomenda", entrega_em="2026-11-03T12:30:00-03:00")
    assert r.status_code == 201 and r.json()["tipo_entrega"] == "encomenda"


def test_minimo_e_sem_estoque(mundo, engine):
    loja, painel = mundo
    calda = vid(engine, "Palha Italiana", "Unidade")
    produzir(painel, calda, 3)
    r = pedir(loja, calda, qtd=1)
    assert r.json()["erro"] == "abaixo_do_minimo" and r.json()["falta_centavos"] == 310
    r = pedir(loja, vid(engine), qtd=1)
    assert r.status_code == 422 and r.json()["erro"] == "sem_estoque"
    assert r.json()["disponivel"] == 0 and "primeira_encomenda" in r.json()


def test_retirada(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 1)
    r = pedir(loja, v, qtd=1, recebimento="retirada", endereco=None)
    assert r.status_code == 201
    assert (r.json()["taxa_entrega_centavos"], r.json()["total_centavos"]) == (0, 1990)


def test_reconhece_pelo_telefone_e_primeiro_nome(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 3)
    pedir(loja, v, qtd=1)
    url = "/api/v1/loja/cliente/reconhecer"
    r = loja.post(url, json={"telefone": "11 99999 1234", "nome": "ana"}).json()
    assert r["endereco_mascarado"] == "R. da••• Acácias, 2••, Jardim Azul"
    # a taxa do endereço anterior vem junto, sem revelar o endereço
    assert r["taxa_entrega_centavos"] == 1400
    assert "220" not in str(r) and "das Acácias" not in str(r) and "lat" not in r
    assert loja.post(url, json={"telefone": "11999991234", "nome": "Carlos"}).json() == {}
    r = pedir(loja, v, qtd=1, endereco=None, usar_endereco_anterior=True)
    assert r.status_code == 201 and r.json()["taxa_entrega_centavos"] == 1400


def test_pix_nao_configurado_nao_cria_pedido(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 2)
    with engine.begin() as c:
        c.execute(text("UPDATE doce.configuracao_loja SET pix_chave = ''"))
    r = pedir(loja, v)
    assert r.status_code == 503 and r.json()["erro"] == "pix_nao_configurado"
    assert saldo(painel, v)["pronta"] == 2


def test_cancelado_depois_de_pago_volta_ao_estoque(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 2)
    p = pedir(loja, v, qtd=2).json()
    painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": p["total_centavos"]},
    )
    r = painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/estado",
        json={"estado": "cancelado", "devolucao_centavos": 5380},
    )
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert saldo(painel, v)["pronta"] == 2
    with engine.connect() as c:
        assert c.execute(text("SELECT devolvido_centavos FROM doce.pedido")).scalar_one() == 5380
    r = painel.post(f"/api/v1/painel/pedidos/{p['id']}/estado", json={"estado": "saiu"})
    assert r.status_code == 422 and r.json()["erro"] == "transicao_invalida"


def test_pronta_entrega_agendada_para_hoje(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 3)
    corpo = loja.get("/api/v1/loja/cardapio").json()
    assert corpo["primeiro_agendamento"] == "2026-11-02T15:30:00-03:00"  # 15h + 30 min
    assert corpo["tempo_preparo_min"] == 30
    r = pedir(loja, v, qtd=1, entrega_em="2026-11-02T15:00:00-03:00")
    assert r.status_code == 422 and r.json()["erro"] == "agendamento_horario"
    assert r.json()["primeiro_agendamento"] == "2026-11-02T15:30:00-03:00"
    assert saldo(painel, v)["pronta"] == 3  # recusa não separa
    p = pedir(loja, v, qtd=1, entrega_em="2026-11-02T18:00:00-03:00").json()
    assert p["tipo_entrega"] == "pronta_entrega"
    assert p["entrega_a_partir_de"] == "2026-11-02T18:00:00-03:00"
    assert (saldo(painel, v)["pronta"], saldo(painel, v)["separada"]) == (2, 1)
    painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": p["total_centavos"]},
    )
    no_painel = painel.get("/api/v1/painel/pedidos").json()["pedidos"][0]
    pago = datetime.fromisoformat(no_painel["entrega_a_partir_de"])
    assert pago == datetime(2026, 11, 2, 18, 0, tzinfo=FUSO)  # pago antes do horário, mantém


def test_loja_fechada_agenda_hoje_a_partir_da_abertura(mundo, engine, relogio):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 2)
    relogio.agora = datetime(2026, 11, 2, 11, 0, tzinfo=FUSO)  # abre às 12h
    corpo = loja.get("/api/v1/loja/cardapio").json()
    assert corpo["loja_aberta"] is False
    assert corpo["primeiro_agendamento"] == "2026-11-02T12:30:00-03:00"
    assert pedir(loja, v, qtd=1).json()["erro"] == "loja_fechada"  # "agora" segue fechado
    r = pedir(loja, v, qtd=1, entrega_em="2026-11-02T12:30:00-03:00")
    assert r.status_code == 201 and r.json()["tipo_entrega"] == "pronta_entrega"
    assert saldo(painel, v)["separada"] == 1


def test_cep_mostra_a_rua_antes_do_numero(mundo):
    loja, _ = mundo
    r = loja.get("/api/v1/loja/cep/12345-678")
    assert r.status_code == 200
    assert r.json() == {
        "cep": "12345678",
        "logradouro": "R. das Acácias",
        "bairro": "Jardim Azul",
        "cidade": "Campinas",
        "uf": "SP",
    }
    r = loja.get("/api/v1/loja/cep/99999-999")
    assert r.status_code == 422 and r.json()["erro"] == "cep_nao_encontrado"


def test_observacao_do_pedido_chega_ao_painel_e_ao_whatsapp(mundo, engine):
    loja, painel = mundo
    v = vid(engine)
    produzir(painel, v, 2)
    obs = "Presente: entregar para Maria na recepção do hospital, quarto 302"
    p = pedir(loja, v, qtd=1, observacao=obs).json()
    assert "Obs.%3A%20Presente" in p["whatsapp_url"]
    no_painel = painel.get("/api/v1/painel/pedidos").json()["pedidos"][0]
    assert no_painel["observacao"] == obs
    assert pedir(loja, v, qtd=1, observacao="x" * 301).status_code == 422


def test_cep_com_servico_fora_do_ar_avisa_para_tentar_de_novo(mundo, monkeypatch):
    loja, _ = mundo

    def fora(_cep):
        raise RuntimeError("não deu para consultar o CEP (brasilapi: 503)")

    monkeypatch.setattr(loja.app.state.roteador, "endereco_do_cep", fora)
    r = loja.get("/api/v1/loja/cep/12345-678")
    assert r.status_code == 503 and r.json()["erro"] == "mapa_indisponivel"
    assert r.json()["mensagem"] == "O CEP não respondeu. Tente de novo."


def test_pagamento_vem_da_porta_injetada(mundo, engine):
    from app.portas.pagamento import Cobranca

    class Falso:
        def cobrar(self, numero_pedido, valor_centavos):
            return Cobranca(txid=f"T{numero_pedido}", copia_e_cola=f"PIX-FALSO-{valor_centavos}")

    loja, painel = mundo
    loja.app.state.pagamento = lambda chave, nome, cidade: Falso()
    v = vid(engine)
    produzir(painel, v, 2)
    p = pedir(loja, v, qtd=1).json()
    assert p["pix"]["copia_e_cola"] == f"PIX-FALSO-{p['total_centavos']}"
