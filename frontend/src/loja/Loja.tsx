import { useEffect, useMemo, useState } from 'react';
import { chamarApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { irPara, useCaminho } from '../comum/rotas';
import { Marca } from '../comum/Marca';
import { Calda } from '../painel/Calda';
import { CardapioLoja } from './CardapioLoja';
import { guardarPedido, useCarrinho } from './carrinho';
import { Checkout } from './Checkout';
import { Pagamento } from './Pagamento';
import type { Cardapio } from './tipos';

const FUSO = { timeZone: 'America/Sao_Paulo' } as const;

// App do cliente: cardápio, pedido e pagamento, sem conta.
export function Loja() {
  const caminho = useCaminho();
  const { itens, mudar, somar, esvaziar } = useCarrinho();
  const [cardapio, setCardapio] = useState<Cardapio | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    chamarApi<Cardapio>('/loja/cardapio')
      .then(setCardapio)
      .catch(() => setErro(true));
  }, [caminho]);

  const pedidoId = caminho.match(/^\/pedido\/([\w-]+)$/)?.[1];
  const tela = pedidoId ? 'pagamento' : caminho === '/carrinho' ? 'carrinho' : 'cardapio';
  const precoPorId = useMemo(
    () =>
      new Map(
        (cardapio?.categorias ?? [])
          .flatMap((c) => c.variantes)
          .map((v) => [v.id, v.preco_centavos]),
      ),
    [cardapio],
  );
  const quantos = Object.values(itens).reduce((a, b) => a + b, 0);
  const total = Object.entries(itens).reduce((t, [id, q]) => t + (precoPorId.get(id) ?? 0) * q, 0);

  const estado = cardapio
    ? cardapio.loja_aberta
      ? !cardapio.fecha_as_hora || cardapio.fecha_as_hora === '00:00'
        ? 'Aberto até meia-noite'
        : `Aberto até as ${cardapio.fecha_as_hora}`
      : `Fechado agora. Abre às ${new Date(cardapio.abre_as).toLocaleTimeString('pt-BR', { ...FUSO, hour: '2-digit', minute: '2-digit' })}; Encomendas a qualquer hora`
    : '';

  return (
    <div className="loja">
      <header className="loja__topo">
        <a
          className="loja__marca"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            irPara('/');
          }}
        >
          <Marca tamanho={56} />
        </a>
        <div>
          <p className="loja__titulo">Doce Ateliê</p>
          <p className={`loja__estado${cardapio?.loja_aberta ? ' loja__estado--aberto' : ''}`}>
            {estado}
          </p>
        </div>
        <Calda />
      </header>

      <main className="loja__corpo">
        {erro && <p className="obra__aviso">Não deu para abrir o cardápio. Recarregue a página.</p>}
        {!cardapio && !erro && tela !== 'pagamento' && (
          <p className="obra__aviso" role="status">
            Abrindo o cardápio…
          </p>
        )}
        {cardapio && tela === 'cardapio' && (
          <CardapioLoja cardapio={cardapio} aoAdicionar={somar} />
        )}
        {cardapio && tela === 'carrinho' && (
          <>
            <a
              className="acesso__link"
              href="/"
              onClick={(e) => {
                e.preventDefault();
                irPara('/');
              }}
            >
              Voltar ao cardápio
            </a>
            <Checkout
              cardapio={cardapio}
              carrinho={itens}
              aoMudar={mudar}
              aoCriar={(p) => {
                guardarPedido(p.id, p);
                esvaziar();
                irPara(`/pedido/${p.id}`);
              }}
            />
          </>
        )}
        {pedidoId && <Pagamento id={pedidoId} />}
      </main>

      {cardapio?.whatsapp_url && tela !== 'pagamento' && (
        <a
          className={`falar${tela === 'cardapio' && quantos > 0 ? ' falar--acima' : ''}`}
          href={cardapio.whatsapp_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Falar com a loja no WhatsApp"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path
              d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.2 3.6c-.5.4-1.3.1-1.3-.6V16A2.5 2.5 0 0 1 4 13.5z"
              fill="currentColor"
            />
          </svg>
          <span>WhatsApp</span>
        </a>
      )}

      {tela === 'cardapio' && quantos > 0 && (
        <div className="barra">
          <button type="button" className="botao barra__botao" onClick={() => irPara('/carrinho')}>
            <span>
              Ver pedido ({quantos} {quantos === 1 ? 'item' : 'itens'})
            </span>
            <span>{formatarCentavos(total)}</span>
          </button>
        </div>
      )}
    </div>
  );
}
