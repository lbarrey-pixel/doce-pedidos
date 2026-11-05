import { type FormEvent, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { Topo } from './Topo';

interface Tarifas {
  tarifa_cartao_bps: number;
  tarifa_pix_bps: number;
}

// Pontos-base ⇄ percentual na tela: 420 = "4,20".
export function percentualDeBps(bps: number): string {
  return (bps / 100).toFixed(2).replace('.', ',');
}

export function bpsDePercentual(texto: string): number | null {
  const m = texto.trim().match(/^(\d{1,3})(?:[.,](\d{1,2}))?$/);
  if (!m) return null;
  const bps = Number(m[1]) * 100 + Number((m[2] ?? '0').padEnd(2, '0'));
  return bps <= 10_000 ? bps : null;
}

// Tarifas do gateway, usadas só na taxa estimada dos resumos.
export function Configuracao({ token }: { token: string }) {
  const [cartao, setCartao] = useState('');
  const [pix, setPix] = useState('');
  const [erro, setErro] = useState('');
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    chamarApi<Tarifas>('/painel/configuracao', { token })
      .then((t) => {
        setCartao(percentualDeBps(t.tarifa_cartao_bps));
        setPix(percentualDeBps(t.tarifa_pix_bps));
      })
      .catch(() => setErro('O servidor está acordando. Recarregue em um minuto.'));
  }, [token]);

  const bpsCartao = bpsDePercentual(cartao);
  const bpsPix = bpsDePercentual(pix);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setErro('');
    setSalvo(false);
    try {
      await chamarApi('/painel/configuracao', {
        method: 'PUT',
        token,
        corpo: { tarifa_cartao_bps: bpsCartao, tarifa_pix_bps: bpsPix },
      });
      setSalvo(true);
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para salvar. Tente de novo.');
    }
  }

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        <section className="obra__abertura obra__abertura--curta">
          <h1 className="obra__titulo">Configuração</h1>
          <p className="obra__texto">
            Tarifas do gateway de pagamento, em % do valor. Servem só para a taxa estimada dos
            resumos.
          </p>
        </section>
        <form className="cartao" onSubmit={salvar}>
          <label className="campo">
            <span className="campo__rotulo">Tarifa do cartão (%)</span>
            <input
              className="campo__entrada"
              inputMode="decimal"
              value={cartao}
              aria-invalid={bpsCartao === null}
              onChange={(e) => setCartao(e.target.value)}
            />
          </label>
          <label className="campo">
            <span className="campo__rotulo">Tarifa do Pix (%)</span>
            <input
              className="campo__entrada"
              inputMode="decimal"
              value={pix}
              aria-invalid={bpsPix === null}
              onChange={(e) => setPix(e.target.value)}
            />
          </label>
          <button className="botao" type="submit" disabled={bpsCartao === null || bpsPix === null}>
            Salvar tarifas
          </button>
          {salvo && <p role="status">Tarifas salvas.</p>}
          {erro && (
            <p className="formulario__erro" role="alert">
              {erro}
            </p>
          )}
        </form>
      </main>
    </div>
  );
}
