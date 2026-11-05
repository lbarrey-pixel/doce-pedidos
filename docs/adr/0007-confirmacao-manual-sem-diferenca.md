# 0007. Confirmação manual só com o valor exato

## Contexto

O ADR 0004 permitia confirmar um Pix manual com valor diferente, aceitando a diferença de forma
explícita. Com o pagamento online, a regra do dinheiro ficou mais rígida: o que entra tem de ser
igual ao que foi cobrado, ou vira pendência para o operador resolver fora do fluxo.

## Decisão

- A confirmação manual aceita só o valor exato do pedido. Valor diferente é recusado (409 `valor_divergente`) e não
  altera o pedido; o operador confere o extrato e combina a devolução ou a cobrança do resto.
- Pedido que tem link de pagamento não é confirmado à mão (409 `pagamento_pelo_gateway`): o
  operador usa "Conferir pagamento", que consulta o gateway.
- O parâmetro de aceitar diferença saiu da API e da tela.

## Consequências

- O total cobrado, o total pago e o resumo por forma de pagamento nunca divergem em silêncio.
- Pix pago a menos ou a mais precisa de uma ação deliberada do operador, não de um clique.
