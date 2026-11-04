# 0001. Site instalável (PWA) em vez de app nas lojas

## Contexto

A loja precisa de uma tela para o cliente pedir e de um painel para quem opera. O público usa
quase só o celular, e a equipe é pequena demais para manter dois aplicativos nativos, contas de
desenvolvedor e o ciclo de revisão das lojas.

## Decisão

Um único site responsivo em React + Vite, instalável como PWA (`vite-plugin-pwa`). O service
worker guarda o aplicativo e os ícones; as chamadas à API nunca entram no cache, para que preço
e estoque venham sempre do servidor. A loja é pública e sem conta. O painel carrega sob demanda
(`lazy`), então o cliente não baixa o código do operador nem o cliente do Supabase Auth.

## Consequências

- Um código só para cliente e operador, publicação imediata, sem taxa de loja.
- Sem presença nas lojas de aplicativos e com notificação limitada no iPhone. O aviso do pedido
  sai por mensagem de WhatsApp, que não depende de push.
- Versão nova no ar recarrega o app sozinha, exceto no meio de carrinho, pagamento ou troca de
  senha (`comum/atualizacao.ts`).
