"""Encomenda e estoque.

A produção da Encomenda já sai separada para ela: não fica na pronta entrega e ninguém mais
consegue baixar essas unidades. A baixa (venda) é quando a Encomenda sai ou é retirada. O
operador pode desfazer a separação e o doce volta à pronta entrega.
"""

from app.adaptadores import repositorio_pedidos
from tests.integracao.apoio import pedir, produzir, saldo, vid

GRANDE = ("Torta de Limão", "Inteira")
COCA = ("Refrigerante de Guaraná", "Lata 350 ml")


def encomenda_paga(loja, painel, variante, qtd=2):
    p = pedir(
        loja,
        variante,
        qtd=qtd,
        tipo_entrega="encomenda",
        entrega_em="2026-11-03T15:00:00-03:00",
    ).json()
    r = painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": p["total_centavos"]},
    )
    assert r.status_code == 200
    return p


def separar(painel, pedido, variante, qtd, origem="producao"):
    return painel.post(
        f"/api/v1/painel/pedidos/{pedido['id']}/separacao",
        json={"variante_id": variante, "quantidade": qtd, "origem": origem},
    )


def estado(painel, pedido, novo):
    return painel.post(f"/api/v1/painel/pedidos/{pedido['id']}/estado", json={"estado": novo})


def test_producao_para_a_encomenda_fica_separada_e_baixa_ao_sair(mundo, engine):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande)
    assert saldo(painel, grande) == {
        "pronta": 0,
        "separada": 0,
        "congelada": 0,
        "descongelando": 0,
        "reserva": 0,
    }
    r = separar(painel, p, grande, 2)
    assert r.status_code == 200, r.json()
    assert (saldo(painel, grande)["pronta"], saldo(painel, grande)["separada"]) == (0, 2)
    perda = painel.post(
        "/api/v1/painel/estoque/movimentos",
        json={
            "variante_id": grande,
            "tipo": "perda",
            "quantidade": 1,
            "de_estado": "pronta",
            "motivo": "caiu",
        },
    )
    assert perda.status_code == 422  # a unidade da Encomenda não está na pronta entrega
    assert estado(painel, p, "em_preparo").status_code == 200
    assert estado(painel, p, "saiu").status_code == 200
    assert saldo(painel, grande)["separada"] == 0  # baixou como venda


def test_sair_sem_a_encomenda_separada_avisa_o_que_falta(mundo, engine):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande)
    separar(painel, p, grande, 1)
    estado(painel, p, "em_preparo")
    r = estado(painel, p, "saiu")
    assert r.status_code == 422 and r.json()["erro"] == "encomenda_sem_separacao"
    assert r.json()["faltando"] == [{"variante_id": grande, "quantidade": 1}]


def test_usar_da_pronta_entrega_e_desfazer(mundo, engine):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande)
    produzir(painel, grande, 3)
    assert separar(painel, p, grande, 2, origem="pronta").status_code == 200
    assert (saldo(painel, grande)["pronta"], saldo(painel, grande)["separada"]) == (1, 2)
    r = separar(painel, p, grande, 1, origem="liberar")
    assert r.status_code == 200
    assert (saldo(painel, grande)["pronta"], saldo(painel, grande)["separada"]) == (2, 1)
    assert separar(painel, p, grande, 2, origem="liberar").status_code == 422  # só há 1


def test_nao_separa_mais_do_que_a_encomenda_pede(mundo, engine):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande, qtd=1)
    r = separar(painel, p, grande, 2)
    assert r.status_code == 422 and r.json()["erro"] == "separacao_invalida"
    outro = vid(engine)
    assert separar(painel, p, outro, 1).status_code == 422  # item fora da Encomenda


def test_cancelar_encomenda_paga_devolve_a_separacao(mundo, engine):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande)
    separar(painel, p, grande, 2)
    r = painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/estado",
        json={"estado": "cancelado", "devolucao_centavos": p["total_centavos"]},
    )
    assert r.status_code == 200
    assert (saldo(painel, grande)["pronta"], saldo(painel, grande)["separada"]) == (2, 0)


def test_bebida_da_encomenda_entra_como_entrada_e_separa(mundo, engine):
    loja, painel = mundo
    grande, coca = vid(engine, *GRANDE), vid(engine, *COCA)
    corpo = {
        "cliente": {"nome": "Ana Paula", "telefone": "(11) 90000-0001"},
        "recebimento": "retirada",
        "itens": [
            {"variante_id": grande, "quantidade": 1},
            {"variante_id": coca, "quantidade": 1},
        ],
        "tipo_entrega": "encomenda",
        "entrega_em": "2026-11-03T15:00:00-03:00",
    }
    p = loja.post("/api/v1/loja/pedidos", json=corpo).json()
    painel.post(
        f"/api/v1/painel/pedidos/{p['id']}/confirmar-pagamento",
        json={"valor_recebido_centavos": p["total_centavos"]},
    )
    assert separar(painel, p, coca, 1).status_code == 200
    assert saldo(painel, coca)["separada"] == 1


def test_producao_mostra_quanto_ja_esta_separado(mundo, engine):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande)
    separar(painel, p, grande, 1)
    (e,) = painel.get("/api/v1/painel/producao?dia=2026-11-03").json()["encomendas"]
    assert e["id"] == p["id"]
    assert e["itens"] == [
        {
            "variante_id": grande,
            "nome": "Torta de Limão · Inteira",
            "quantidade": 2,
            "separado": 1,
        }
    ]


def test_movimento_recusado_pelo_livro_e_erro_de_negocio(mundo, engine, monkeypatch):
    loja, painel = mundo
    grande = vid(engine, *GRANDE)
    p = encomenda_paga(loja, painel, grande)

    def recusa(*_args, **_kw):
        raise ValueError("estado fora do controle")

    monkeypatch.setattr(repositorio_pedidos, "separar_para_encomenda", recusa)
    r = separar(painel, p, grande, 1)
    assert r.status_code == 422 and r.json()["erro"] == "movimento_invalido"
