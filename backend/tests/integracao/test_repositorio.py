"""Repositório SQL: carga do cardápio, livro de estoque e separação concorrente."""

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.adaptadores import repositorio_sql as repo
from app.dominio.catalogo import ler_cardapio
from app.dominio.estoque import Estado, FaltaEstoque, Movimento, Tipo

CARDAPIO = Path(__file__).resolve().parents[2] / "dados" / "cardapio.csv"
AGORA = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


@pytest.fixture
def catalogo():
    return ler_cardapio(CARDAPIO)


@pytest.fixture
def carregado(engine, catalogo):
    with engine.begin() as c:
        repo.carregar_catalogo(c, catalogo)
    return engine


def _id(engine, produto, tamanho):
    with engine.connect() as c:
        return repo.id_da_variante(c, produto, tamanho)


def _pedido(engine):
    with engine.begin() as c:
        return c.execute(
            text(
                "INSERT INTO doce.pedido (canal, subtotal_centavos, total_centavos,"
                " forma_pagamento, estado) VALUES ('app', 1990, 1990, 'pix_manual',"
                " 'aguardando_pagamento') RETURNING id"
            )
        ).scalar_one()


def mov(variante_id, tipo, qtd, de=None, para=None, **kw):
    return Movimento(
        variante=str(variante_id),
        tipo=tipo,
        quantidade=qtd,
        de_estado=de,
        para_estado=para,
        autor="teste",
        criado_em=AGORA,
        **kw,
    )


def test_carga_do_cardapio(carregado, catalogo):
    with carregado.connect() as c:
        n = c.execute(
            text(
                "SELECT (SELECT count(*) FROM doce.categoria), (SELECT count(*) FROM doce.produto),"
                " (SELECT count(*) FROM doce.variante), (SELECT count(*) FROM doce.saldo)"
            )
        ).one()
        preco = c.execute(
            text(
                "SELECT v.preco_centavos FROM doce.variante v JOIN doce.produto p"
                " ON p.id = v.produto_id WHERE p.nome = 'Bolo de Pote Red Velvet'"
                " AND v.tamanho = 'Individual'"
            )
        ).one()
    assert tuple(n) == (6, 13, 15, 15)
    assert preco.preco_centavos == 2190


def test_carga_e_idempotente_e_atualiza_preco(carregado, catalogo):
    with carregado.begin() as c:
        repo.carregar_catalogo(c, catalogo)
    with carregado.connect() as c:
        assert c.execute(text("SELECT count(*) FROM doce.variante")).scalar_one() == 15


def test_livro_e_saldo(carregado):
    v = _id(carregado, "Torta de Limão", "Fatia")
    with carregado.begin() as c:
        repo.registrar_movimento(c, mov(v, Tipo.PRODUCAO, 3, para=Estado.PRONTA))
        repo.registrar_movimento(c, mov(v, Tipo.PRODUCAO, 2, para=Estado.CONGELADA))
    with carregado.connect() as c:
        s = repo.saldos(c)[str(v)]
        assert (s.pronta, s.congelada) == (3, 2)
        assert repo.conferir_saldos(c) == []  # materializado == soma do livro


def test_venda_acima_do_saldo_e_recusada(carregado):
    """Só vende o que há; nada fica negativo."""
    v = _id(carregado, "Bolo de Pote Red Velvet", "Individual")
    p = _pedido(carregado)
    with pytest.raises(FaltaEstoque), carregado.begin() as c:
        repo.registrar_movimento(c, mov(v, Tipo.VENDA, 2, Estado.PRONTA, pedido_id=str(p)))
    with carregado.connect() as c:
        assert repo.saldos(c)[str(v)].pronta == 0 and repo.conferir_saldos(c) == []


def test_banco_tambem_recusa_saldo_negativo(carregado):
    v = _id(carregado, "Bolo de Pote Red Velvet", "Individual")
    with pytest.raises(IntegrityError), carregado.begin() as c:
        c.execute(text("UPDATE doce.saldo SET pronta = -1 WHERE variante_id = :v"), {"v": v})


def test_controle_de_estoque_inicial_por_categoria(carregado):
    """Bebidas com estoque reserva, embalagens só com pronta entrega, o resto congelável."""
    with carregado.connect() as c:
        contagem = dict(
            c.execute(text("SELECT controle_estoque, count(*) FROM doce.variante GROUP BY 1")).all()
        )
    assert contagem == {"congelavel": 11, "reserva": 2, "simples": 2}


def test_bebida_com_estoque_reserva(carregado):
    coca = _id(carregado, "Refrigerante de Guaraná", "Lata 350 ml")
    with carregado.begin() as c:
        repo.registrar_movimento(c, mov(coca, Tipo.ENTRADA, 12, para=Estado.RESERVA))
        repo.registrar_movimento(c, mov(coca, Tipo.TRANSFERENCIA, 6, Estado.RESERVA, Estado.PRONTA))
    with pytest.raises(ValueError, match="controle"), carregado.begin() as c:
        repo.registrar_movimento(c, mov(coca, Tipo.PRODUCAO, 1, para=Estado.CONGELADA))
    with carregado.connect() as c:
        s = repo.saldos(c)[str(coca)]
        assert (s.reserva, s.pronta) == (6, 6) and repo.conferir_saldos(c) == []


def test_fim_do_descongelamento_gravado_sozinho(carregado):
    v = _id(carregado, "Cheesecake de Frutas Vermelhas", "Fatia")
    with carregado.begin() as c:
        repo.registrar_movimento(c, mov(v, Tipo.PRODUCAO, 2, para=Estado.CONGELADA))
        repo.registrar_movimento(
            c, mov(v, Tipo.INICIO_DESCONGELAMENTO, 1, Estado.CONGELADA, Estado.DESCONGELANDO)
        )
    with carregado.begin() as c:
        pendentes = repo.atualizar_descongelamentos(c, AGORA + timedelta(minutes=90))
    assert [(p.variante, p.quantidade) for p in pendentes] == [(str(v), 1)]
    for _ in range(2):  # idempotente: a segunda leitura não grava de novo
        with carregado.begin() as c:
            assert repo.atualizar_descongelamentos(c, AGORA + timedelta(hours=2)) == []
    with carregado.connect() as c:
        s = repo.saldos(c)[str(v)]
        assert (s.congelada, s.descongelando, s.pronta) == (1, 0, 1)
        fim = c.execute(
            text(
                "SELECT autor, criado_em FROM doce.movimento"
                " WHERE tipo = 'fim_descongelamento' AND variante_id = :v"
            ),
            {"v": v},
        ).one()
        assert fim.autor == "app" and fim.criado_em == AGORA + timedelta(hours=2)
        assert repo.conferir_saldos(c) == []


def test_livro_e_imutavel_para_a_api(carregado):
    v = _id(carregado, "Brownie de Nozes", "Unidade")
    with carregado.begin() as c:
        repo.registrar_movimento(c, mov(v, Tipo.PRODUCAO, 1, para=Estado.PRONTA))
    with pytest.raises(ProgrammingError), carregado.begin() as c:
        c.execute(text("UPDATE doce.movimento SET quantidade = 9"))
    with pytest.raises(ProgrammingError), carregado.begin() as c:
        c.execute(text("DELETE FROM doce.movimento"))


def test_api_nao_enxerga_public(carregado):
    with pytest.raises(ProgrammingError), carregado.begin() as c:
        c.execute(text("CREATE TABLE public.intrusa (x int)"))


def test_dois_pedidos_pela_ultima_unidade(carregado):
    """Exatamente um separa; o outro recebe falta de estoque (FOR UPDATE no saldo)."""
    estado_inicial, de, para = Estado.PRONTA, Estado.PRONTA, Estado.SEPARADA
    v = _id(carregado, "Torta de Limão", "Inteira")
    with carregado.begin() as c:
        repo.registrar_movimento(c, mov(v, Tipo.PRODUCAO, 1, para=estado_inicial))
    pedidos = [_pedido(carregado), _pedido(carregado)]
    travou = threading.Event()
    resultados: dict[int, str] = {}

    def tentar(i):
        try:
            with carregado.begin() as c:
                repo.registrar_movimento(
                    c, mov(v, Tipo.SEPARACAO, 1, de, para, pedido_id=str(pedidos[i]))
                )
                if i == 0:
                    travou.set()
                    time.sleep(0.5)  # segura a trava enquanto o segundo tenta
            resultados[i] = "separou"
        except FaltaEstoque:
            resultados[i] = "sem_estoque"

    a = threading.Thread(target=tentar, args=(0,))
    a.start()
    travou.wait(5)
    b = threading.Thread(target=tentar, args=(1,))
    b.start()
    a.join()
    b.join()
    assert resultados == {0: "separou", 1: "sem_estoque"}
    with carregado.connect() as c:
        s = repo.saldos(c)[str(v)]
        assert getattr(s, de.value) == 0 and getattr(s, para.value) == 1
