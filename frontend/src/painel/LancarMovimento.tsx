import { type FormEvent, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import {
  ACOES,
  ESTADOS_DO_CONTROLE,
  type EstadoSaldo,
  NOME_DO_ESTADO,
  type Saldo,
  type VarianteEstoque,
} from './estoque-tipos';
import { Quantidade } from './Quantidade';

// Um lançamento de estoque para uma Variante: escolhe a ação, a quantidade e, em perda e
// ajuste, o lugar e o motivo. Quem decide se cabe é a API (saldo nunca fica negativo).
export function LancarMovimento({
  variante,
  token,
  aoLancar,
}: {
  variante: VarianteEstoque;
  token: string;
  aoLancar: (saldo: Saldo, tipo: string) => void;
}) {
  const acoes = ACOES[variante.controle_estoque];
  const estados = ESTADOS_DO_CONTROLE[variante.controle_estoque];
  const [acaoId, setAcaoId] = useState(acoes[0].id);
  const [quantidade, setQuantidade] = useState(1);
  const [estado, setEstado] = useState<EstadoSaldo>('pronta');
  const [somar, setSomar] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [mensagem, setMensagem] = useState<{ tipo: 'ok' | 'erro'; texto: string } | null>(null);
  const [enviando, setEnviando] = useState(false);
  const acao = acoes.find((a) => a.id === acaoId) ?? acoes[0];
  const nome = `acao-${variante.id}`;

  async function confirmar(e: FormEvent) {
    e.preventDefault();
    if (acao.escolheEstado && !motivo.trim()) {
      setMensagem({ tipo: 'erro', texto: 'Diga o motivo.' });
      return;
    }
    const corpo: Record<string, unknown> = {
      variante_id: variante.id,
      tipo: acao.tipo,
      quantidade,
    };
    if (acao.para) corpo.para_estado = acao.para;
    if (acao.escolheEstado === 'de' || (acao.escolheEstado === 'ajuste' && !somar))
      corpo.de_estado = estado;
    if (acao.escolheEstado === 'ajuste' && somar) corpo.para_estado = estado;
    if (acao.escolheEstado) corpo.motivo = motivo.trim();
    setEnviando(true);
    setMensagem(null);
    try {
      const r = await chamarApi<{ saldo: Saldo }>('/painel/estoque/movimentos', {
        method: 'POST',
        token,
        corpo,
      });
      setMensagem({ tipo: 'ok', texto: 'Lançado.' });
      setQuantidade(1);
      setMotivo('');
      aoLancar(r.saldo, acao.tipo);
    } catch (erro) {
      setMensagem({
        tipo: 'erro',
        texto: erro instanceof ErroDaApi ? erro.message : 'Não deu para lançar. Tente de novo.',
      });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="lancar" onSubmit={confirmar} noValidate>
      <fieldset className="lancar__acoes">
        <legend className="campo__rotulo">O que aconteceu</legend>
        {acoes.map((a) => (
          <label key={a.id} className="chip">
            <input
              type="radio"
              name={nome}
              value={a.id}
              checked={a.id === acaoId}
              onChange={() => {
                setAcaoId(a.id);
                setMensagem(null);
              }}
            />
            <span>{a.rotulo}</span>
          </label>
        ))}
      </fieldset>

      {acao.escolheEstado === 'ajuste' && (
        <fieldset className="lancar__acoes">
          <legend className="campo__rotulo">Sentido</legend>
          {[
            [false, 'Tirar'],
            [true, 'Somar'],
          ].map(([valor, texto]) => (
            <label key={String(valor)} className="chip">
              <input
                type="radio"
                name={`${nome}-sentido`}
                checked={somar === valor}
                onChange={() => setSomar(valor as boolean)}
              />
              <span>{texto as string}</span>
            </label>
          ))}
        </fieldset>
      )}

      {acao.escolheEstado && estados.length > 1 && (
        <label className="campo">
          <span className="campo__rotulo">Onde</span>
          <select
            className="campo__entrada"
            value={estado}
            onChange={(e) => setEstado(e.target.value as EstadoSaldo)}
          >
            {estados.map((s) => (
              <option key={s} value={s}>
                {NOME_DO_ESTADO[s]}
              </option>
            ))}
          </select>
        </label>
      )}

      <Quantidade valor={quantidade} aoMudar={setQuantidade} />

      {acao.escolheEstado && (
        <label className="campo">
          <span className="campo__rotulo">Motivo</span>
          <input
            className="campo__entrada"
            maxLength={500}
            value={motivo}
            placeholder={acao.tipo === 'perda' ? 'caiu, venceu…' : 'contagem…'}
            onChange={(e) => setMotivo(e.target.value)}
          />
        </label>
      )}

      <p
        className={mensagem?.tipo === 'ok' ? 'lancar__ok' : 'formulario__erro'}
        role={mensagem?.tipo === 'erro' ? 'alert' : 'status'}
        aria-live="polite"
      >
        {mensagem?.texto}
      </p>
      <button className="botao" type="submit" disabled={enviando}>
        {enviando ? 'Lançando…' : 'Confirmar'}
      </button>
    </form>
  );
}
