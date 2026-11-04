from app.regras import config


def test_faixas_crescentes_e_em_centavos():
    limites = [m for m, _ in config.FAIXAS_DISTANCIA]
    taxas = [c for _, c in config.FAIXAS_DISTANCIA]
    assert limites == sorted(limites) and len(set(limites)) == len(limites)
    assert taxas == [1000, 1400, 1700, 2000, 2500]
    assert all(isinstance(c, int) for c in taxas)


def test_valores_padrao():
    assert config.PEDIDO_MINIMO_CENTAVOS == 800
    assert config.FAIXAS_DISTANCIA[-1][0] == 12_000
    assert config.PREVISAO_PRONTA_MIN == 40


def test_regras_de_estoque_e_encomenda():
    assert config.DESCONGELAMENTO_H == 2
    assert config.ALERTA_ENCOMENDA_DIAS_ANTES == 1
    assert config.ENCOMENDA_COM_LOJA_FECHADA is True
    assert config.CONTROLE_POR_CATEGORIA["Bebidas"] == "reserva"
    assert config.CONTROLE_POR_CATEGORIA["Embalagens"] == "simples"
    assert not hasattr(config, "ENCOMENDA_MAX_DIAS")
