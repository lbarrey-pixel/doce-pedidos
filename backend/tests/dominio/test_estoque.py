"""Livro de movimentos de estoque (ADR 0003): saldo, transições válidas e descongelamento."""

from datetime import UTC, datetime, timedelta

import pytest

from app.dominio.estoque import (
    Controle,
    Estado,
    FaltaEstoque,
    Lugar,
    Movimento,
    Saldo,
    Tipo,
    aplicar,
    descongelamento,
    saldo_de,
)

T = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
V = "Torta de Limão|Fatia"


def mov(tipo, qtd, de=None, para=None, **kw):
    base = {"variante": V, "autor": "marina", "criado_em": T}
    return Movimento(tipo=tipo, quantidade=qtd, de_estado=de, para_estado=para, **(base | kw))


def test_producao_vai_para_pronta_e_para_congelada():
    livro = [
        mov(Tipo.PRODUCAO, 3, para=Estado.PRONTA),
        mov(Tipo.PRODUCAO, 2, para=Estado.CONGELADA),
    ]
    s = saldo_de(livro)[V]
    assert (s.pronta, s.congelada) == (3, 2)
    assert s.no_lugar(Lugar.LOJA) == 3 and s.no_lugar(Lugar.COZINHA) == 2


def test_descongelando_nao_e_pronta_entrega_ate_o_fim():
    s = Saldo(congelada=2)
    s = aplicar(s, mov(Tipo.INICIO_DESCONGELAMENTO, 1, Estado.CONGELADA, Estado.DESCONGELANDO))
    assert (s.congelada, s.descongelando, s.disponivel_agora) == (1, 1, 0)
    s = aplicar(s, mov(Tipo.FIM_DESCONGELAMENTO, 1, Estado.DESCONGELANDO, Estado.PRONTA))
    assert (s.descongelando, s.pronta) == (0, 1)


def test_venda_direta_baixa_a_pronta_entrega():
    s = aplicar(Saldo(pronta=4), mov(Tipo.VENDA, 2, Estado.PRONTA, pedido_id="p1"))
    assert s.pronta == 2


def test_venda_acima_do_saldo_e_recusada():
    venda = mov(Tipo.VENDA, 2, Estado.PRONTA, pedido_id="p1")
    with pytest.raises(FaltaEstoque) as e:
        aplicar(Saldo(pronta=1), venda)
    assert (e.value.estado, e.value.disponivel, e.value.pedido) == (Estado.PRONTA, 1, 2)


def test_separacao_e_venda():
    s = aplicar(
        Saldo(pronta=5), mov(Tipo.SEPARACAO, 2, Estado.PRONTA, Estado.SEPARADA, pedido_id="a")
    )
    assert (s.pronta, s.separada) == (3, 2)
    s = aplicar(s, mov(Tipo.VENDA, 2, Estado.SEPARADA, pedido_id="a"))
    assert (s.pronta, s.separada) == (3, 0)


@pytest.mark.parametrize(
    ("saldo", "m"),
    [
        (Saldo(pronta=0), mov(Tipo.SEPARACAO, 1, Estado.PRONTA, Estado.SEPARADA, pedido_id="b")),
        (Saldo(pronta=1), mov(Tipo.PERDA, 2, Estado.PRONTA, motivo="caiu")),
        (
            Saldo(congelada=0),
            mov(Tipo.INICIO_DESCONGELAMENTO, 1, Estado.CONGELADA, Estado.DESCONGELANDO),
        ),
        (Saldo(pronta=3), mov(Tipo.AJUSTE, 4, Estado.PRONTA, motivo="contagem")),
    ],
)
def test_nenhum_saldo_fica_negativo(saldo, m):
    with pytest.raises(FaltaEstoque):
        aplicar(saldo, m)


def test_liberacao_devolve_a_pronta_entrega():
    s = Saldo(pronta=0, separada=1)
    s = aplicar(s, mov(Tipo.LIBERACAO_SEPARACAO, 1, Estado.SEPARADA, Estado.PRONTA, pedido_id="a"))
    assert (s.pronta, s.separada) == (1, 0)


def test_reserva_congelada_nunca_e_separada_nem_vendida():
    with pytest.raises(ValueError, match="transição"):
        mov(Tipo.SEPARACAO, 1, Estado.CONGELADA, Estado.SEPARADA, pedido_id="c")
    with pytest.raises(ValueError, match="transição"):
        mov(Tipo.VENDA, 1, Estado.CONGELADA, pedido_id="c")


def test_ajuste_de_contagem_e_perda():
    s = aplicar(Saldo(pronta=5), mov(Tipo.AJUSTE, 1, Estado.PRONTA, motivo="contagem"))
    s = aplicar(s, mov(Tipo.PERDA, 1, Estado.PRONTA, motivo="caiu"))
    s = aplicar(s, mov(Tipo.AJUSTE, 2, para=Estado.CONGELADA, motivo="achado no freezer"))
    assert (s.pronta, s.congelada) == (3, 2)


def test_saldo_e_a_soma_do_livro_por_variante():
    outra = "Brownie de Nozes|Unidade"
    livro = [
        mov(Tipo.PRODUCAO, 3, para=Estado.PRONTA),
        mov(Tipo.PRODUCAO, 4, para=Estado.PRONTA, variante=outra),
        mov(Tipo.VENDA, 1, Estado.PRONTA, pedido_id="x"),
    ]
    saldos = saldo_de(livro)
    assert saldos[V].pronta == 2 and saldos[outra].pronta == 4


@pytest.mark.parametrize(
    ("tipo", "de", "para", "extra", "erro"),
    [
        (Tipo.PRODUCAO, None, Estado.PRONTA, {"quantidade": 0}, "quantidade"),
        (Tipo.PERDA, Estado.PRONTA, None, {}, "motivo"),
        (Tipo.AJUSTE, Estado.PRONTA, None, {}, "motivo"),
        (Tipo.SEPARACAO, Estado.PRONTA, Estado.SEPARADA, {}, "pedido"),
        (Tipo.VENDA, Estado.PRONTA, None, {}, "pedido"),
        (Tipo.LIBERACAO_SEPARACAO, Estado.SEPARADA, Estado.PRONTA, {}, "pedido"),
        (Tipo.PRODUCAO, None, Estado.SEPARADA, {}, "transição"),
        (Tipo.SEPARACAO, Estado.CONGELADA, Estado.SEPARADA, {"pedido_id": "a"}, "transição"),
        (
            Tipo.LIBERACAO_SEPARACAO,
            Estado.SEPARADA,
            Estado.CONGELADA,
            {"pedido_id": "a"},
            "transição",
        ),
        (Tipo.FIM_DESCONGELAMENTO, Estado.CONGELADA, Estado.PRONTA, {}, "transição"),
        (Tipo.AJUSTE, Estado.PRONTA, Estado.CONGELADA, {"motivo": "x"}, "transição"),
    ],
)
def test_movimento_invalido(tipo, de, para, extra, erro):
    kw = {"quantidade": 1} | extra
    with pytest.raises(ValueError, match=erro):
        mov(tipo, kw.pop("quantidade"), de, para, **kw)


def test_movimento_exige_hora_com_fuso_e_autor():
    with pytest.raises(ValueError):
        mov(Tipo.PRODUCAO, 1, para=Estado.PRONTA, criado_em=datetime(2026, 10, 29))
    with pytest.raises(ValueError):
        mov(Tipo.PRODUCAO, 1, para=Estado.PRONTA, autor="")


def test_producao_para_pronta_entrega_ou_reserva_congelada():
    s = aplicar(Saldo(), mov(Tipo.PRODUCAO, 2, para=Estado.PRONTA))
    s = aplicar(s, mov(Tipo.PRODUCAO, 3, para=Estado.CONGELADA))
    assert (s.pronta, s.congelada) == (2, 3)


def test_bebida_tem_estoque_reserva_e_transferencia():
    coca = Controle.RESERVA
    s = aplicar(Saldo(), mov(Tipo.ENTRADA, 12, para=Estado.RESERVA), coca)
    s = aplicar(s, mov(Tipo.TRANSFERENCIA, 6, Estado.RESERVA, Estado.PRONTA), coca)
    assert (s.reserva, s.pronta) == (6, 6)
    assert s.no_lugar(Lugar.COZINHA) == 6 and s.no_lugar(Lugar.LOJA) == 6
    with pytest.raises(FaltaEstoque):
        aplicar(s, mov(Tipo.TRANSFERENCIA, 7, Estado.RESERVA, Estado.PRONTA), coca)


@pytest.mark.parametrize(
    ("controle", "m"),
    [
        (Controle.RESERVA, mov(Tipo.PRODUCAO, 1, para=Estado.CONGELADA)),
        (Controle.RESERVA, mov(Tipo.CONGELAMENTO, 1, Estado.PRONTA, Estado.CONGELADA)),
        (Controle.SIMPLES, mov(Tipo.ENTRADA, 1, para=Estado.RESERVA)),
        (Controle.SIMPLES, mov(Tipo.PRODUCAO, 1, para=Estado.PRONTA)),
        (Controle.CONGELAVEL, mov(Tipo.ENTRADA, 1, para=Estado.PRONTA)),
        (Controle.CONGELAVEL, mov(Tipo.AJUSTE, 1, para=Estado.RESERVA, motivo="x")),
    ],
)
def test_movimento_precisa_servir_ao_controle_da_variante(controle, m):
    with pytest.raises(ValueError, match="controle"):
        aplicar(Saldo(pronta=5), m, controle)


def test_embalagem_so_tem_pronta_entrega():
    s = aplicar(Saldo(), mov(Tipo.ENTRADA, 10, para=Estado.PRONTA), Controle.SIMPLES)
    s = aplicar(s, mov(Tipo.VENDA, 1, Estado.PRONTA, pedido_id="p"), Controle.SIMPLES)
    assert s.pronta == 9


def _inicio(qtd, quando, variante=V):
    return mov(
        Tipo.INICIO_DESCONGELAMENTO,
        qtd,
        Estado.CONGELADA,
        Estado.DESCONGELANDO,
        criado_em=quando,
        variante=variante,
    )


def test_descongelamento_termina_sozinho_2_h_depois():
    as14 = datetime(2026, 10, 30, 17, 0, tzinfo=UTC)  # 14h em São Paulo
    livro = [mov(Tipo.PRODUCAO, 2, para=Estado.CONGELADA), _inicio(1, as14)]
    antes = descongelamento(livro, as14 + timedelta(hours=1, minutes=59))
    assert antes.vencidos == []
    assert [(p.variante, p.quantidade, p.pronta_as) for p in antes.pendentes] == [
        (V, 1, as14 + timedelta(hours=2))
    ]
    depois = descongelamento(livro, as14 + timedelta(hours=2))
    (fim,) = depois.vencidos
    assert (fim.tipo, fim.quantidade, fim.autor) == (Tipo.FIM_DESCONGELAMENTO, 1, "app")
    assert (fim.de_estado, fim.para_estado) == (Estado.DESCONGELANDO, Estado.PRONTA)
    assert fim.criado_em == as14 + timedelta(hours=2) and depois.pendentes == []
    s = saldo_de([*livro, fim])[V]
    assert (s.congelada, s.descongelando, s.pronta) == (1, 0, 1)


def test_lotes_por_ordem_de_inicio_e_sem_repetir_fim_ja_gravado():
    t = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
    outra = "Brownie de Nozes|Unidade"
    livro = [
        _inicio(2, t),
        _inicio(3, t + timedelta(hours=1)),
        _inicio(1, t, variante=outra),
        mov(
            Tipo.FIM_DESCONGELAMENTO,
            2,
            Estado.DESCONGELANDO,
            Estado.PRONTA,
            autor="app",
            criado_em=t + timedelta(hours=2),
        ),
        mov(Tipo.PERDA, 1, Estado.DESCONGELANDO, motivo="caiu", criado_em=t + timedelta(hours=2)),
    ]
    r = descongelamento(livro, t + timedelta(hours=2, minutes=30))
    assert [(m.variante, m.quantidade) for m in r.vencidos] == [(outra, 1)]
    assert [(p.variante, p.quantidade) for p in r.pendentes] == [(V, 2)]  # 3 − 1 perda
    r = descongelamento(livro, t + timedelta(hours=3))
    assert sorted((m.variante, m.quantidade) for m in r.vencidos) == sorted([(V, 2), (outra, 1)])


def test_descongelado_nao_volta_para_reserva_congelada():
    with pytest.raises(ValueError, match="transição"):
        mov(Tipo.CONGELAMENTO, 1, Estado.DESCONGELANDO, Estado.CONGELADA)
