import { useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { irPara } from '../comum/rotas';

// Página de pagamento de mentira, só para demonstração (backend com GATEWAY=simulado). No lugar
// do gateway de verdade, escolhe como "pagar" e volta ao app com os dados que a URL de retorno
// traria.
export function Simulador({ id }: { id: string }) {
  const [parcelas, setParcelas] = useState(1);
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);

  async function pagar(metodo: 'pix' | 'credit_card') {
    setErro('');
    setEnviando(true);
    try {
      const r = await chamarApi<{ transaction_nsu: string; slug: string }>(
        '/gateway/simulado/pagar',
        {
          method: 'POST',
          corpo: { pedido_id: id, metodo, parcelas: metodo === 'pix' ? 1 : parcelas },
        },
      );
      const volta = new URLSearchParams({ transaction_nsu: r.transaction_nsu, slug: r.slug });
      irPara(`/pedido/${id}?${volta.toString()}`);
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para pagar. Tente de novo.');
      setEnviando(false);
    }
  }

  return (
    <section className="pagamento">
      <h1 className="checkout__titulo">Pagamento simulado</h1>
      <p className="obra__texto">
        Esta página faz o papel do gateway de checkout na demonstração. Nada é cobrado.
      </p>
      <button type="button" className="botao" disabled={enviando} onClick={() => pagar('pix')}>
        Pagar com Pix
      </button>
      <label className="campo">
        <span className="campo__rotulo">Parcelas no cartão</span>
        <select
          className="campo__entrada"
          value={parcelas}
          onChange={(e) => setParcelas(Number(e.target.value))}
        >
          {[1, 2, 3, 6, 12].map((n) => (
            <option key={n} value={n}>
              {n}x
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="botao botao--contorno"
        disabled={enviando}
        onClick={() => pagar('credit_card')}
      >
        Pagar com cartão
      </button>
      {erro && (
        <p className="formulario__erro" role="alert">
          {erro}
        </p>
      )}
    </section>
  );
}
