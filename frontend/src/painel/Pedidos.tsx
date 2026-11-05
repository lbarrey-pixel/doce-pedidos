import { useCallback, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { hora } from './estoque-tipos';
import { PendenciasPagamento } from './PendenciasPagamento';
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
  forma_pagamento?: 'pix' | 'cartao' | 'pix_manual' | 'externo' | null;
  parcelas?: number | null;
  valor_pago_centavos?: number | null;
  pago_apos_expirar?: boolean;
  paga_pelo_link?: boolean; // pedido do app com link: só o gateway confirma
  pagamento_link?: 'aguardando' | 'pago' | 'expirado' | null; // venda lançada no painel
}

interface Estorno {
  valor_centavos: number;
  mensagem: string;
}

function formaLegivel(p: Pedido): string | null {
  if (p.forma_pagamento === 'pix') return 'Pix';
  if (p.forma_pagamento === 'pix_manual') return 'Pix manual';
  if (p.forma_pagamento === 'cartao')
    return p.parcelas && p.parcelas > 1 ? `Cartão em ${p.parcelas}x` : 'Cartão';
  return null;
}

const NOME_DO_ESTADO: Record<string, string> = {
  aguardando_pagamento: 'Esperando o pagamento',
  pago: 'Pago',
  em_preparo: 'Em preparo',
  saiu: 'Saiu',
  entregue: 'Entregue',
  cancelado: 'Cancelado',
};
const NOME_DO_LINK = {
  aguardando: 'Aguardando pagamento do link',
  pago: 'Paga pelo link',
  expirado: 'Link expirado sem pagamento',
} as const;
const RESULTADO_DA_CONFERENCIA: Record<string, string> = {
  confirmado: 'Pagamento confirmado.',
  pago_depois_de_expirar: 'Pagamento confirmado.',
  repetido: 'Pagamento confirmado.',
  nao_confirmado: 'O gateway ainda não confirmou o pagamento deste pedido.',
  valor_recusado: 'O gateway mostra um valor diferente do pedido. Confira no painel do gateway.',
  a_estornar: 'Este pagamento está em Pagamentos para conferir, para estorno.',
  a_decidir: 'Pago depois de expirar e sem estoque: decida em Pagamentos para conferir.',
};
const PROXIMO: Record<string, [string, string] | undefined> = {
  pago: ['em_preparo', 'Começar preparo'],
  em_preparo: ['saiu', 'Saiu para entrega'],
  saiu: ['entregue', 'Entregue'],
};

function CartaoPedido({
  p,
  token,
  aoMudar,
  aoEstornar,
}: {
  p: Pedido;
  token: string;
  aoMudar: () => void;
  aoEstornar: (numero: number, estorno: Estorno) => void;
}) {
  const [erro, setErro] = useState('');
  const [conferido, setConferido] = useState('');

  async function enviar(caminho: string, corpo: unknown) {
    setErro('');
    try {
      const r = await chamarApi<{ estorno?: Estorno } | null>(
        `/painel/pedidos/${p.id}/${caminho}`,
        { method: 'POST', token, corpo },
      );
      if (r?.estorno) aoEstornar(p.numero, r.estorno);
      aoMudar();
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para salvar. Tente de novo.');
    }
  }

  // Confere no gateway; vale também para pedido cancelado, que pode ter sido pago depois.
  async function conferirPagamento() {
    setErro('');
    setConferido('');
    try {
      const r = await chamarApi<{ estado?: string; resultado?: string } | null>(
        `/painel/pedidos/${p.id}/conferir-pagamento`,
        { method: 'POST', token },
      );
      setConferido(
        (r?.resultado && RESULTADO_DA_CONFERENCIA[r.resultado]) ||
          RESULTADO_DA_CONFERENCIA.nao_confirmado,
      );
      aoMudar();
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para conferir. Tente de novo.');
    }
  }

  const forma = formaLegivel(p);
  const pagoPeloGateway = p.forma_pagamento === 'pix' || p.forma_pagamento === 'cartao';
  const valorPago = pagoPeloGateway ? (p.valor_pago_centavos ?? null) : null;
  // Pago pelo gateway o aviso de estorno vem do backend; a devolução só se registra no Pix manual.
  const devolveuNaMao = p.estado !== 'aguardando_pagamento' && !pagoPeloGateway;

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

      {forma && <p className="pedido__linha">Pagamento: {forma}</p>}
      {valorPago !== null && (
        <p className="pedido__linha">
          Valor do pedido {formatarCentavos(p.total_centavos)} · pago pelo cliente{' '}
          {formatarCentavos(valorPago)}
        </p>
      )}
      {p.pago_apos_expirar && <p className="pedido__alerta">Pago depois de expirar</p>}
      {p.pagamento_link && !(p.estado === 'cancelado' && p.pagamento_link === 'aguardando') && (
        <p className={p.pagamento_link === 'expirado' ? 'pedido__alerta' : 'pedido__linha'}>
          {NOME_DO_LINK[p.pagamento_link]}
        </p>
      )}
      {conferido && (
        <p className="pedido__linha" role="status">
          {conferido}
        </p>
      )}

      {p.canal === 'app' && ['aguardando_pagamento', 'cancelado'].includes(p.estado) && (
        <button type="button" className="botao botao--contorno" onClick={conferirPagamento}>
          Conferir pagamento
        </button>
      )}
      {p.estado === 'aguardando_pagamento' && !p.paga_pelo_link && (
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
              ...(devolveuNaMao && { devolucao_centavos: p.total_centavos }),
            })
          }
        >
          {devolveuNaMao ? 'Cancelar e registrar devolução do Pix' : 'Cancelar pedido'}
        </button>
      )}
      {p.canal === 'balcao' && ['pago', 'em_preparo'].includes(p.estado) && (
        <button
          type="button"
          className="venda__tirar"
          onClick={() => enviar('estado', { estado: 'cancelado' })}
        >
          Cancelar venda
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
  const [estorno, setEstorno] = useState<{ numero: number; estorno: Estorno } | null>(null);
  const [versao, setVersao] = useState(0); // muda a cada consulta, para as pendências recarregarem

  const carregar = useCallback(
    () =>
      chamarApi<{ pedidos: Pedido[] }>('/painel/pedidos', { token })
        .then((r) => {
          setPedidos(r.pedidos);
          setVersao((v) => v + 1);
        })
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
        {estorno && (
          <div className="pedido__alerta" role="status">
            <p>
              Pedido nº {estorno.numero} cancelado. {estorno.estorno.mensagem}
            </p>
            <button
              type="button"
              className="botao botao--contorno"
              onClick={() => setEstorno(null)}
            >
              Entendi
            </button>
          </div>
        )}
        <PendenciasPagamento token={token} versao={versao} />
        {pedidos && ativos.length === 0 && <p className="obra__aviso">Nenhum pedido em aberto.</p>}
        {ativos.map((p) => (
          <CartaoPedido
            key={p.id}
            p={p}
            token={token}
            aoMudar={carregar}
            aoEstornar={(numero, e) => setEstorno({ numero, estorno: e })}
          />
        ))}
        {fechados.length > 0 && (
          <section className="secao">
            <h2 className="secao__titulo">Entregues e cancelados</h2>
            {fechados.map((p) => (
              <CartaoPedido
                key={p.id}
                p={p}
                token={token}
                aoMudar={carregar}
                aoEstornar={(numero, e) => setEstorno({ numero, estorno: e })}
              />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
