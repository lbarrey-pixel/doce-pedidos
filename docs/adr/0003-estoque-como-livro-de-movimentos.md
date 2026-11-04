# 0003. Estoque como livro de movimentos

## Contexto

O estoque precisa bater com a contagem física, e cada diferença precisa ter explicação:
produção, venda, perda, doce separado para um pedido. Um saldo editável diretamente esconde
esse histórico.

## Decisão

Nenhum saldo é alterado à mão. Todo efeito é um **movimento** imutável (tipo, quantidade, estado
de origem e de destino, autor, motivo, horário) e o saldo de cada variante é a soma dos
movimentos. Para ler rápido, o saldo é materializado na tabela `saldo`, atualizada na mesma
transação do movimento, com a linha travada por `SELECT ... FOR UPDATE`; `conferir_saldos`
recalcula pela soma do livro e deve devolver lista vazia.

Os estados são `pronta`, `separada`, `congelada`, `descongelando` e `reserva`, e cada variante
tem um tipo de controle (`congelavel`, `reserva`, `simples`) que define quais estados e quais
movimentos fazem sentido. A validação mora no domínio (`dominio/estoque.py`); o banco reforça
com `CHECK (... >= 0)` e com permissões: o papel da API só insere e lê em `movimento`.

## Consequências

- Correção é sempre um movimento de ajuste com motivo, nunca edição.
- Dois pedidos disputando a última unidade se resolvem pela trava da linha: um separa, o outro
  recebe falta de estoque (há teste de concorrência com threads).
- O saldo materializado é uma redundância a vigiar; por isso existe a conferência.
