# Glossary

Terms used in the code, in the tests and on screen.

| Term | Meaning |
| --- | --- |
| Produto, variante (product, variant) | A product groups the sizes of the same sweet; a variant is what is sold (product + size, with a price). |
| Pronta entrega (ready now) | Units ready in the store, sellable now. |
| Encomenda (pre-order) | An order for a future date, with a minimum lead time (12 h) and no maximum deadline. |
| Reserva congelada (frozen reserve) | Units frozen in the kitchen; they become ready to sell only after thawing. |
| Separada (set aside) | A unit reserved for an order that has not yet been deducted. |
| Movimento (movement) | An immutable record of a stock change; the balance is the sum of the movements. |
| Faixa de distância (distance band) | A range of street distance to the store, with the delivery fee in cents. |
| Operador (operator) | A person with access to the panel; the store owner has the role `dono`. |
| Gateway de checkout (checkout gateway) | An external service that hosts the payment page (card and Pix, Brazil's instant payment system) and notifies the result. It sits behind the `GatewayDePagamento` port. |
| Link de pagamento (payment link) | The address of the gateway's page for an order, with the amount, the expiry and the return to the store. |
| Aviso (notice) | A call from the gateway to the API saying that something was paid. It is not trustworthy on its own: the server always checks the payment with the gateway. |
| Conferência (check) | A query to the gateway by `transaction_nsu` that decides whether the payment counts (`decidir`). |
| Pagamento pendente (pending payment) | A checked payment that the system does not apply on its own (different amount, after expiry, out of stock) and that the operator resolves. |
| Estorno pendente (pending refund) | An amount paid that needs to go back to the customer; it is done in the gateway's panel and marked as resolved in the panel. |
| Venda (sale) | An order entered by the operator in the panel (counter channel), with a 30-minute payment link that can be sent by WhatsApp. |
| Taxa estimada (estimated fee) | The order amount times the gateway's à vista tariff (paid in full, not in installments), in basis points; it appears in the summaries by payment method. |
