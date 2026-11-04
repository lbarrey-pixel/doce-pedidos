"""Catálogo lido do CSV do cardápio."""

from pathlib import Path

import pytest

from app.dominio.catalogo import Variante, centavos_de_texto, ler_cardapio

CSV = Path(__file__).resolve().parents[2] / "dados" / "cardapio.csv"


@pytest.fixture(scope="module")
def catalogo():
    return ler_cardapio(CSV)


def test_contagens_do_cardapio(catalogo):
    assert len(catalogo.categorias) == 6
    assert len(catalogo.variantes) == 15
    assert len(catalogo.produtos) == 13


def test_preco_em_centavos(catalogo):
    assert catalogo.variante("Torta de Limão", "Fatia").preco_centavos == 1690
    assert catalogo.variante("Torta de Limão", "Inteira").preco_centavos == 12900


def test_edicao_limitada_vem_da_observacao(catalogo):
    assert catalogo.variante("Palha Italiana", "Unidade").edicao_limitada
    assert not catalogo.variante("Brownie de Nozes", "Unidade").edicao_limitada


def test_categoria_fica_na_variante(catalogo):
    assert catalogo.variante("Torta de Limão", "Fatia").categoria == "Tortas"
    assert catalogo.variante("Brigadeiro de Pistache", "Caixa com 12").categoria == "Brigadeiros"


def test_ordem_das_categorias_segue_o_arquivo(catalogo):
    assert catalogo.categorias[0] == "Brigadeiros"
    assert catalogo.categorias[-1] == "Embalagens"


def test_item_sem_peso_fica_vazio(catalogo):
    assert catalogo.variante("Sacola Presente", "Unidade").peso_g is None


def test_variante_repetida_no_arquivo_e_recusada(tmp_path):
    cabecalho = "categoria,produto,tamanho,peso_g,porcoes,preco,descricao,ingredientes,observacao\n"
    linha = "Tortas,Torta,Fatia,100,1,10.00,d,i,\n"
    arquivo = tmp_path / "repetido.csv"
    arquivo.write_text(cabecalho + linha + linha, encoding="utf-8")
    with pytest.raises(ValueError, match="repetida"):
        ler_cardapio(arquivo)


@pytest.mark.parametrize(
    ("texto", "centavos"), [("19.90", 1990), ("7.00", 700), ("189.90", 18990), ("3", 300)]
)
def test_centavos_sem_ponto_flutuante(texto, centavos):
    assert centavos_de_texto(texto) == centavos


@pytest.mark.parametrize("texto", ["", "abc", "1.999", "-1.00", "0.00"])
def test_preco_invalido(texto):
    with pytest.raises(ValueError):
        centavos_de_texto(texto)


def test_variante_recusa_preco_nao_positivo():
    with pytest.raises(ValueError):
        Variante(produto="X", tamanho="Y", categoria="Z", preco_centavos=0)
