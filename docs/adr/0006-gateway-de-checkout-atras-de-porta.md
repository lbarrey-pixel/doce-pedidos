# 0006. Gateway de checkout atrás de uma porta, com conferência no servidor

## Contexto

O Pix copia e cola (ADR 0004) depende de alguém olhar o extrato. A loja quis aceitar cartão e
Pix com confirmação automática, sem guardar dado de cartão e sem prender o domínio a um
fornecedor. O gateway escolhido hospeda a página de pagamento (checkout) e avisa por webhook,
mas o aviso não é assinado: qualquer um que descubra a URL pode postar um corpo qualquer.

## Decisão

1. **Porta `GatewayDePagamento`** (`portas/pagamento.py`) com três operações: `criar_link`,
   `conferir` e `codigo_do_aviso`. O adaptador HTTP (`gateway_checkout.py`) e o simulador
   (`gateway_simulado.py`) a implementam; o domínio e as rotas só conhecem a porta. O contrato
   HTTP está em [`docs/contracts/gateway-checkout.md`](../contracts/gateway-checkout.md).
2. **O corpo do aviso nunca é confiado.** A rota `POST /gateway/checkout/aviso` só usa dele o
   identificador da transação e chama `conferir` no gateway. Quem decide é a resposta da
   conferência, aplicada pela função pura `decidir` (`dominio/pagamento_online.py`):
   valor pago menor que o cobrado, valor cobrado diferente do total do pedido, Pix com valor
   diferente do cobrado, transação já registrada, pagamento depois de expirar e pagamento sem
   estoque têm resultado próprio.
3. **Código na URL do aviso.** Como não há assinatura, cada link leva `?c=` com um HMAC do id do
   pedido (32 caracteres). Código errado responde sem consultar o gateway.
4. **Idempotência no banco.** Índice único parcial em `transaction_nsu` nos resultados que
   efetivam algo, `SELECT ... FOR UPDATE` no pedido e um savepoint em volta do registro e dos
   efeitos. Aviso repetido, aviso concorrente e conferência manual do mesmo pagamento não
   confirmam duas vezes.
5. **Pagamento tardio não perde dinheiro.** Pago depois de expirar, o pedido é reativado se
   ainda há estoque; se não há, vira pendência de estorno (`a_estornar` ou `a_decidir`) para o
   operador. O estorno é feito no painel do gateway; o sistema só avisa e registra.
6. **Fallback.** Sem gateway configurado, ou se ele falhar ao criar o link, o pedido nasce com o
   Pix copia e cola. A chave da API nunca aparece em log, erro ou `repr`.
7. **Valores em centavos e tarifas em pontos-base** (420 = 4,20%). O resumo por forma de
   pagamento mostra a taxa estimada com a tarifa à vista configurada.

## Consequências

- Trocar de gateway é escrever outro adaptador e a mesma suíte de contrato; o domínio não muda.
- Cada aviso custa uma chamada de conferência. É o preço de não confiar em corpo sem assinatura.
- Sem agendador, o link vencido é tratado quando o pedido ou o estoque é lido (ADR 0005).
- O simulador (`GATEWAY=simulado`) permite rodar o fluxo inteiro sem conta em nenhum gateway.
