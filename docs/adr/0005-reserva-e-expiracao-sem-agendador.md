# 0005. Reserva de estoque e expiração calculadas na leitura, sem agendador

## Contexto

Quando o cliente fecha o pedido, as unidades ficam reservadas até o Pix ser confirmado. Se ele
desiste, a reserva precisa voltar ao estoque. O mesmo vale para o descongelamento, que termina
sozinho depois de um prazo. A hospedagem escolhida dorme quando ociosa e não garante cron.

## Decisão

Pedido aguardando pagamento guarda `expira_em`. Toda rota que lê ou escreve estoque ou pedidos
chama antes `liberar_expirados`: pedidos vencidos viram cancelados e as unidades separadas
voltam para a pronta entrega, em movimentos gravados na mesma transação. O descongelamento segue
a mesma ideia: `atualizar_descongelamentos` grava os fins vencidos ao ler o estoque. As duas
operações são idempotentes e usam `FOR UPDATE SKIP LOCKED` quando há concorrência.

Se o dinheiro entrar depois do prazo, o operador ainda pode confirmar o pagamento: se houver
unidade, ela é separada de novo; se não houver, a API responde 409 com a instrução de oferecer
Encomenda ou devolver o Pix.

## Consequências

- Nenhum processo em segundo plano para manter, monitorar ou pagar.
- O estado "real" só aparece quando alguém olha: um relatório que lê direto do banco precisa
  aplicar a mesma regra de expiração.
- A primeira requisição depois de um período parado paga o custo de liberar o que venceu.
