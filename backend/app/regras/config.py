"""Parâmetros de negócio da loja.

Dinheiro em centavos inteiros; distância em metros. Os valores que o operador pode mudar
(horário, faixas, Pix, pedido mínimo) ficam na tabela `configuracao_loja`; o que está aqui
é o padrão do domínio e o que não precisa de tela.
"""

from datetime import time

# Faixas de distância: (até metros, inclusivo; taxa em centavos). Um metro acima do limite
# já cai na faixa seguinte. Acima do último limite a entrega é combinada à parte.
FAIXAS_DISTANCIA: tuple[tuple[int, int], ...] = (
    (3_000, 1_000),
    (6_000, 1_400),
    (8_000, 1_700),
    (10_000, 2_000),
    (12_000, 2_500),
)

# Pedido mínimo sobre os itens, antes do desconto e sem a taxa de entrega.
PEDIDO_MINIMO_CENTAVOS = 800

# Horário padrão: 12h às 24h. Fechamento 00:00 significa meia-noite (fim exclusivo).
ABRE = time(12, 0)
FECHA = time(0, 0)

# Previsão de pronta entrega: preparo + tempo médio de trajeto.
PREVISAO_PRONTA_MIN = 40

# Retirada na loja fica pronta pouco depois do Pix confirmado.
PREPARO_RETIRADA_MIN = 10

# Pronta entrega agendada para hoje: o primeiro horário é agora + este tempo, arredondado
# para a meia hora seguinte. Editável na configuração da loja.
TEMPO_PREPARO_PADRAO_MIN = 30

# Pedido que saiu vira "entregue" sozinho depois do tempo médio de entrega. É só controle
# visual do painel, sem confirmação do entregador.
TEMPO_ENTREGA_MIN = 30

# Encomenda precisa de antecedência mínima; não há prazo máximo.
ANTECEDENCIA_ENCOMENDA_H = 12
ALERTA_ENCOMENDA_DIAS_ANTES = 1
ENCOMENDA_COM_LOJA_FECHADA = True

# Descongelamento: depois deste tempo o lote vira pronta entrega sem ação do operador.
DESCONGELAMENTO_H = 2

# Pedido sem Pix confirmado expira e devolve a separação ao estoque.
EXPIRACAO_PAGAMENTO_MIN = 30

# Desconto do app arredonda para baixo no centavo (15% de 1990 = 298, não 299).
DESCONTO_ARREDONDA_PARA_BAIXO = True

# Controle de estoque inicial por categoria do cardápio; o padrão vale para o que congela.
CONTROLE_POR_CATEGORIA = {
    "Bebidas": "reserva",
    "Embalagens": "simples",
}
CONTROLE_PADRAO = "congelavel"
