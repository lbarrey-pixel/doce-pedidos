# Glossário

Termos usados no código, nos testes e na tela.

| Termo | Significado |
| --- | --- |
| Produto, variante | Produto agrupa os tamanhos de um mesmo doce; variante é o que se vende (produto + tamanho, com preço). |
| Pronta entrega | Unidades prontas na loja, vendáveis agora. |
| Encomenda | Pedido para uma data futura, com antecedência mínima (12 h) e sem prazo máximo. |
| Reserva congelada | Unidades congeladas na cozinha; só viram pronta entrega depois de descongelar. |
| Separada | Unidade reservada para um pedido ainda não baixado. |
| Movimento | Registro imutável de uma mudança de estoque; o saldo é a soma dos movimentos. |
| Faixa de distância | Intervalo de distância de rua até a loja, com a taxa de entrega em centavos. |
| Operador | Pessoa com acesso ao painel; o dono da loja tem papel `dono`. |
| Gateway de checkout | Serviço externo que hospeda a página de pagamento (cartão e Pix) e avisa o resultado. Fica atrás da porta `GatewayDePagamento`. |
| Link de pagamento | Endereço da página do gateway para um pedido, com valor, validade e volta para a loja. |
| Aviso | Chamada do gateway à API dizendo que algo foi pago. Não é confiável por si: o servidor sempre confere o pagamento no gateway. |
| Conferência | Consulta ao gateway pelo `transaction_nsu` que decide se o pagamento vale (`decidir`). |
| Pagamento pendente | Pagamento conferido que o sistema não efetiva sozinho (valor diferente, depois de expirar, sem estoque) e que o operador resolve. |
| Estorno pendente | Valor pago que precisa voltar ao cliente; é feito no painel do gateway e marcado como resolvido no painel. |
| Venda | Pedido lançado pelo operador no painel (canal balcão), com link de pagamento de 30 min enviável por WhatsApp. |
| Taxa estimada | Valor do pedido vezes a tarifa à vista do gateway (em pontos-base); aparece nos resumos por forma de pagamento. |
