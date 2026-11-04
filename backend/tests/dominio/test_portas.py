"""Portas: contratos mínimos que todo adaptador cumpre (ADR 0002)."""

from app.adaptadores.pix_manual import PixManual
from app.adaptadores.roteador_fake import RoteadorFake
from app.adaptadores.roteador_google import RoteadorGoogle
from app.portas.pagamento import Cobranca, ProvedorDePagamento
from app.portas.roteador import Roteador


class PagamentoFalso:
    def cobrar(self, numero_pedido: int, valor_centavos: int) -> Cobranca:
        return Cobranca(txid=f"DA{numero_pedido}", copia_e_cola="000201...")


def test_adaptadores_cumprem_as_portas():
    assert isinstance(RoteadorFake(), Roteador)
    assert isinstance(RoteadorGoogle(""), Roteador)
    assert isinstance(PagamentoFalso(), ProvedorDePagamento)
    assert isinstance(PixManual("chave", "NOME", "CIDADE"), ProvedorDePagamento)


def test_roteador_fake_acha_cep_conhecido_e_recusa_o_resto():
    r = RoteadorFake()
    assert r.endereco_do_cep("12345-678").cidade == "Campinas"
    assert r.endereco_do_cep("00000-000") is None


def test_roteador_fake_mede_a_distancia_do_cep():
    r = RoteadorFake()
    origem = r.geocodificar(r.endereco_do_cep("12345-678"), "10")
    # a distância sai da diferença de longitude: a origem da loja está em longitude -47.0
    loja = type(origem)(-22.9, -47.0)
    assert r.distancia_metros(loja, origem) == 5000
    assert r.geocodificar(r.endereco_do_cep("12345-678"), "sem-numero") is None
