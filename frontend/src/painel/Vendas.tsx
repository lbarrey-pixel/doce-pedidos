import { useCallback, useEffect, useMemo, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { nomeDaVariante, type VarianteEstoque } from './estoque-tipos';
import { LinkDaVenda } from './LinkDaVenda';
import { Quantidade } from './Quantidade';
import { Topo } from './Topo';

interface VendaLancada {
  id: string;
  numero: number;
  total_centavos: number;
}

// Venda feita fora do app (balcão, WhatsApp, Instagram): sai da pronta entrega na hora e pode
// ganhar um link de pagamento para o cliente pagar à distância.
export function Vendas({ token }: { token: string }) {
  const [variantes, setVariantes] = useState<VarianteEstoque[] | null>(null);
  const [itens, setItens] = useState<Record<string, number>>({});
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [lancadas, setLancadas] = useState<VendaLancada[]>([]);

  const carregar = useCallback(
    () =>
      chamarApi<{ variantes: VarianteEstoque[] }>('/painel/estoque', { token })
        .then((r) => setVariantes(r.variantes.filter((v) => v.ativa)))
        .catch(() => setErro('O servidor está acordando. Recarregue em um minuto.')),
    [token],
  );
  useEffect(() => {
    carregar();
  }, [carregar]);

  const porId = useMemo(() => new Map((variantes ?? []).map((v) => [v.id, v])), [variantes]);
  const linhas = Object.entries(itens).filter(([id]) => porId.has(id));
  const total = linhas.reduce((t, [id, q]) => t + porId.get(id)!.preco_centavos * q, 0);

  async function lancar() {
    setErro('');
    setEnviando(true);
    try {
      const r = await chamarApi<VendaLancada>('/painel/vendas', {
        method: 'POST',
        token,
        corpo: { itens: linhas.map(([variante_id, quantidade]) => ({ variante_id, quantidade })) },
      });
      setLancadas((l) => [r, ...l]);
      setItens({});
      carregar();
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para lançar. Tente de novo.');
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        <section className="obra__abertura obra__abertura--curta">
          <h1 className="obra__titulo">Vendas</h1>
          <p className="obra__texto">
            Venda fora do app. Sai da pronta entrega ao lançar; se o cliente for pagar por link,
            gere o link depois.
          </p>
        </section>
        {erro && (
          <p className="formulario__erro" role="alert">
            {erro}
          </p>
        )}
        {lancadas.map((v) => (
          <LinkDaVenda key={v.id} token={token} vendaId={v.id} numero={v.numero} />
        ))}
        {linhas.length > 0 && (
          <ul className="venda__itens" aria-label="Itens da venda">
            {linhas.map(([id, q]) => {
              const v = porId.get(id)!;
              return (
                <li key={id} className="venda__item">
                  <span className="venda__nome">
                    {nomeDaVariante(v)}
                    <small>{formatarCentavos(v.preco_centavos * q)}</small>
                  </span>
                  <Quantidade
                    valor={q}
                    maximo={v.saldo.pronta}
                    rotulo={`Quantidade de ${nomeDaVariante(v)}`}
                    aoMudar={(n) => setItens((m) => ({ ...m, [id]: n }))}
                  />
                  <button
                    type="button"
                    className="venda__tirar"
                    onClick={() =>
                      setItens((m) =>
                        Object.fromEntries(Object.entries(m).filter(([k]) => k !== id)),
                      )
                    }
                  >
                    Tirar
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {linhas.length > 0 && (
          <button type="button" className="botao" disabled={enviando} onClick={lancar}>
            Lançar venda · {formatarCentavos(total)}
          </button>
        )}
        <h2 className="secao__titulo venda__cardapio">Cardápio</h2>
        <ul className="venda__opcoes">
          {(variantes ?? []).map((v) => (
            <li key={v.id}>
              <button
                type="button"
                className="venda__opcao"
                disabled={v.saldo.pronta === 0 || v.id in itens}
                onClick={() => setItens((m) => ({ ...m, [v.id]: 1 }))}
              >
                {nomeDaVariante(v)}
                <span className="venda__info">
                  {formatarCentavos(v.preco_centavos)} · {v.saldo.pronta} na pronta entrega
                </span>
              </button>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
