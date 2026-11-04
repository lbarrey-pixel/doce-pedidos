import { useCallback, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { centavosDeTexto, formatarCentavos } from '../comum/dinheiro';
import { hora } from './estoque-tipos';
import { type Entregador, SaidaEntrega } from './SaidaEntrega';
import { Topo } from './Topo';

interface Pedido {
  id: string;
  numero: number;
  canal: string;
  estado: string;
  recebimento: 'entrega' | 'retirada';
  tipo_entrega: 'pronta_entrega' | 'encomenda';
  cliente: { nome: string | null; telefone: string | null };
  endereco: { logradouro: string; numero: string; bairro: string; complemento?: string } | null;
  observacao?: string | null; // detalhes da entrega escritos pelo cliente
  itens: { nome: string; quantidade: number }[];
  total_centavos: number;
  diferenca_pagamento_centavos: number;
  criado_em: string;
  expira_em: string | null;
  entrega_a_partir_de: string | null;
  entregador?: Entregador | null;
  entregue_previsto_em?: string | null;
}

const NOME_DO_ESTADO: Record<string, string> = {
  aguardando_pagamento: 'Esperando o Pix',
  pago: 'Pago',
  em_preparo: 'Em preparo',
  saiu: 'Saiu',
  entregue: 'Entregue',
  cancelado: 'Cancelado',
};
const PROXIMO: Record<string, [string, string] | undefined> = {
  pago: ['em_preparo', 'Começar preparo'],
  em_preparo: ['saiu', 'Saiu para entrega'],
  saiu: ['entregue', 'Entregue'],
};

function CartaoPedido({ p, token, aoMudar }: { p: Pedido; token: string; aoMudar: () => void }) {
  const [outroValor, setOutroValor] = useState<string | null>(null);
  const [erro, setErro] = useState('');

  async function enviar(caminho: string, corpo: unknown) {
    setErro('');
    try {
      await chamarApi(`/painel/pedidos/${p.id}/${caminho}`, { method: 'POST', token, corpo });
      setOutroValor(null);
      aoMudar();
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para salvar. Tente de novo.');
    }
  }

  const proximo = PROXIMO[p.estado];
  const retirada = p.recebimento === 'retirada';
  const quando =
    p.tipo_entrega === 'encomenda'
      ? `Encomenda para ${new Date(p.entrega_a_partir_de ?? '').toLocaleString('pt-BR', {
          timeZone: 'America/Sao_Paulo',
          day: '2-digit',
          month: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })}`
      : retirada
        ? 'Retirada na loja'
        : `Entrega a partir das ${hora(p.entrega_a_partir_de ?? p.criado_em)}`;

  return (
    <article className={`cartao pedido pedido--${p.estado}`} aria-label={`Pedido nº ${p.numero}`}>
      <header className="cartao__cabeca">
        <h3 className="estoque__nome">Pedido nº {p.numero}</h3>
        <span className="cartao__selo">{NOME_DO_ESTADO[p.estado] ?? p.estado}</span>
      </header>
      <p className="pedido__linha">
        {p.canal === 'app' ? `${p.cliente.nome} · ${p.cliente.telefone}` : `Venda ${p.canal}`}
      </p>
      <ul className="pedido__itens">
        {p.itens.map((i) => (
          <li key={i.nome}>
            {i.quantidade}× {i.nome}
          </li>
        ))}
      </ul>
      {p.endereco && (
        <p className="pedido__linha">
          {p.endereco.logradouro}, {p.endereco.numero}
          {p.endereco.complemento ? ` (${p.endereco.complemento})` : ''}, {p.endereco.bairro}
        </p>
      )}
      {p.observacao && <p className="pedido__linha pedido__obs">Obs.: {p.observacao}</p>}
      <p className="pedido__linha">
        {quando}. Total <strong>{formatarCentavos(p.total_centavos)}</strong>
        {p.diferenca_pagamento_centavos !== 0 &&
          ` (diferença registrada: ${formatarCentavos(p.diferenca_pagamento_centavos)})`}
      </p>

      {p.estado === 'aguardando_pagamento' && (
        <div className="pedido__acoes">
          <button
            type="button"
            className="botao"
            onClick={() =>
              enviar('confirmar-pagamento', { valor_recebido_centavos: p.total_centavos })
            }
          >
            Recebi {formatarCentavos(p.total_centavos)}
          </button>
          {outroValor === null ? (
            <button
              type="button"
              className="botao botao--contorno"
              onClick={() => setOutroValor('')}
            >
              Entrou outro valor
            </button>
          ) : (
            <div className="pedido__outro">
              <label className="campo">
                <span className="campo__rotulo">Valor que entrou</span>
                <input
                  className="campo__entrada"
                  inputMode="decimal"
                  value={outroValor}
                  onChange={(e) => setOutroValor(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="botao botao--contorno"
                disabled={centavosDeTexto(outroValor) === null}
                onClick={() =>
                  enviar('confirmar-pagamento', {
                    valor_recebido_centavos: centavosDeTexto(outroValor),
                    aceitar_diferenca: true,
                  })
                }
              >
                Confirmar com diferença
              </button>
            </div>
          )}
          {p.expira_em && <p className="obra__nota">Reservado até as {hora(p.expira_em)}.</p>}
        </div>
      )}
      {p.estado === 'saiu' && (
        <p className="pedido__linha">
          {p.entregador ? `Saiu com ${p.entregador.nome}` : 'Saiu para entrega'}
          {p.entregue_previsto_em &&
            `; vira entregue às ${hora(p.entregue_previsto_em)}, sem precisar confirmar`}
        </p>
      )}
      {proximo && (
        <div className="pedido__acoes">
          {proximo[0] === 'saiu' && !retirada ? (
            <SaidaEntrega
              token={token}
              aoSair={(entregador) => enviar('estado', { estado: 'saiu', entregador })}
            />
          ) : (
            <button
              type="button"
              className="botao"
              onClick={() => enviar('estado', { estado: proximo[0] })}
            >
              {retirada && proximo[0] === 'saiu' ? 'Cliente retirou' : proximo[1]}
            </button>
          )}
        </div>
      )}
      {['aguardando_pagamento', 'pago', 'em_preparo'].includes(p.estado) && p.canal === 'app' && (
        <button
          type="button"
          className="venda__tirar"
          onClick={() =>
            enviar('estado', {
              estado: 'cancelado',
              ...(p.estado !== 'aguardando_pagamento' && { devolucao_centavos: p.total_centavos }),
            })
          }
        >
          {p.estado === 'aguardando_pagamento'
            ? 'Cancelar pedido'
            : 'Cancelar e registrar devolução do Pix'}
        </button>
      )}
      {erro && (
        <p className="formulario__erro" role="alert">
          {erro}
        </p>
      )}
    </article>
  );
}

// Pedidos do app: novos em destaque, confirmação do Pix, mudança de estado.
export function Pedidos({ token }: { token: string }) {
  const [pedidos, setPedidos] = useState<Pedido[] | null>(null);
  const [erro, setErro] = useState('');

  const carregar = useCallback(
    () =>
      chamarApi<{ pedidos: Pedido[] }>('/painel/pedidos', { token })
        .then((r) => setPedidos(r.pedidos))
        .catch(() => setErro('O servidor está acordando. Recarregue em um minuto.')),
    [token],
  );

  useEffect(() => {
    carregar();
    const vez = setInterval(carregar, 30_000); // pedido novo aparece sem recarregar
    return () => clearInterval(vez);
  }, [carregar]);

  const ativos = (pedidos ?? []).filter((p) => !['entregue', 'cancelado'].includes(p.estado));
  const fechados = (pedidos ?? []).filter((p) => ['entregue', 'cancelado'].includes(p.estado));

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        <section className="obra__abertura obra__abertura--curta">
          <h1 className="obra__titulo">Pedidos</h1>
          <p className="obra__texto">Os últimos 7 dias. Pedido novo aparece aqui sozinho.</p>
        </section>
        {erro && <p className="obra__aviso">{erro}</p>}
        {pedidos && ativos.length === 0 && <p className="obra__aviso">Nenhum pedido em aberto.</p>}
        {ativos.map((p) => (
          <CartaoPedido key={p.id} p={p} token={token} aoMudar={carregar} />
        ))}
        {fechados.length > 0 && (
          <section className="secao">
            <h2 className="secao__titulo">Entregues e cancelados</h2>
            {fechados.map((p) => (
              <CartaoPedido key={p.id} p={p} token={token} aoMudar={carregar} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
