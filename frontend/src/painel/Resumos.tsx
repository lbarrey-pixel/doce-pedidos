import { useEffect, useState } from 'react';
import { chamarApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { Topo } from './Topo';

const FORMAS = [
  ['pix', 'Pix'],
  ['cartao', 'Cartão'],
  ['pix_manual', 'Pix manual'],
] as const;

interface PorForma {
  pedidos: number;
  valor_centavos: number;
  taxa_estimada_centavos: number;
}

interface Resumo {
  de: string;
  ate: string;
  por_forma: Record<(typeof FORMAS)[number][0], PorForma>;
}

const data = (iso: string) => iso.split('-').reverse().join('/');

// Quanto entrou por forma de pagamento nos últimos 7 dias, com a taxa estimada do gateway.
export function Resumos({ token }: { token: string }) {
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [erro, setErro] = useState('');

  useEffect(() => {
    chamarApi<Resumo>('/painel/resumos', { token })
      .then(setResumo)
      .catch(() => setErro('O servidor está acordando. Recarregue em um minuto.'));
  }, [token]);

  const taxaTotal = Object.values(resumo?.por_forma ?? {}).reduce(
    (t, f) => t + f.taxa_estimada_centavos,
    0,
  );

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        <section className="obra__abertura obra__abertura--curta">
          <h1 className="obra__titulo">Resumos</h1>
          {resumo && (
            <p className="obra__texto">
              De {data(resumo.de)} a {data(resumo.ate)}, pela data do pagamento.
            </p>
          )}
        </section>
        {erro && <p className="obra__aviso">{erro}</p>}
        {resumo && (
          <section className="secao" aria-label="Por forma de pagamento">
            <h2 className="secao__titulo">Por forma de pagamento</h2>
            {FORMAS.filter(([f]) => resumo.por_forma[f].pedidos > 0).map(([f, nome]) => (
              <article key={f} className="cartao" aria-label={nome}>
                <h3 className="estoque__nome">{nome}</h3>
                <p className="pedido__linha">
                  {resumo.por_forma[f].pedidos}{' '}
                  {resumo.por_forma[f].pedidos === 1 ? 'pedido' : 'pedidos'} ·{' '}
                  <strong>{formatarCentavos(resumo.por_forma[f].valor_centavos)}</strong>
                </p>
                <p className="pedido__linha">
                  Taxa estimada {formatarCentavos(resumo.por_forma[f].taxa_estimada_centavos)}
                </p>
              </article>
            ))}
            {FORMAS.every(([f]) => resumo.por_forma[f].pedidos === 0) && (
              <p className="obra__aviso">Nenhum pagamento no período.</p>
            )}
            <p className="obra__nota">
              Taxa estimada do gateway no período: {formatarCentavos(taxaTotal)}. É uma estimativa
              pelas tarifas da Configuração.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
