# 0004. Pix "copia e cola" gerado localmente, confirmado pelo operador

## Contexto

O cliente paga por Pix e a loja não quer, por enquanto, contratar um provedor de pagamento nem
pagar taxa por transação.

## Decisão

O backend monta o BR Code estático do Pix (`dominio/pix.py`) com a chave da loja, o valor exato
do pedido e um `txid` derivado do número do pedido, seguindo o manual do Banco Central
(campos em TLV e CRC-16/CCITT-FALSE sobre o payload terminado em `6304`; os testes conferem os
exemplos do manual). O cliente copia o código ou lê o QR e paga; quem opera a loja confirma o
recebimento no painel, informando o valor que entrou. Valor diferente do cobrado é recusado (ADR 0007).

O gerador fica atrás da porta `ProvedorDePagamento` (ADR 0002), com o adaptador `pix_manual`.

## Consequências

- Custo zero e nenhuma conta nova de integração.
- Sem confirmação automática: depende de alguém olhar o extrato. O pagamento online com
  confirmação automática entrou depois, como outra porta (ADR 0006), sem mexer no domínio.
- Sem chave Pix cadastrada na configuração da loja, o pedido não é criado (503) e a separação
  de estoque é desfeita na mesma transação.
