import { useEffect, useState } from 'react';
import { chamarApi } from '../comum/api';

export interface Entregador {
  nome: string;
  telefone: string;
}

// Saída com o entregador: escolher um já usado, digitar um novo ou
// sair sem informar. O Pedido vira Entregue sozinho depois do tempo médio de entrega.
export function SaidaEntrega({
  token,
  aoSair,
}: {
  token: string;
  aoSair: (entregador: Entregador | null) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [lista, setLista] = useState<Entregador[]>([]);
  const [nome, setNome] = useState('');
  const [telefone, setTelefone] = useState('');

  useEffect(() => {
    if (!aberto) return;
    chamarApi<{ entregadores: Entregador[] }>('/painel/entregadores', { token })
      .then((r) => setLista(r.entregadores))
      .catch(() => setLista([]));
  }, [aberto, token]);

  if (!aberto) {
    return (
      <button type="button" className="botao" onClick={() => setAberto(true)}>
        Saiu para entrega
      </button>
    );
  }
  return (
    <div className="saida" role="group" aria-label="Quem levou">
      {lista.map((e) => (
        <button
          key={`${e.nome}-${e.telefone}`}
          type="button"
          className="botao botao--contorno"
          onClick={() => aoSair(e)}
        >
          {e.nome}
        </button>
      ))}
      <label className="campo">
        <span className="campo__rotulo">Entregador ou cooperativa</span>
        <input className="campo__entrada" value={nome} onChange={(e) => setNome(e.target.value)} />
      </label>
      <label className="campo">
        <span className="campo__rotulo">Telefone do entregador</span>
        <input
          className="campo__entrada"
          inputMode="tel"
          value={telefone}
          onChange={(e) => setTelefone(e.target.value)}
        />
      </label>
      <button
        type="button"
        className="botao"
        disabled={!nome.trim()}
        onClick={() => aoSair({ nome: nome.trim(), telefone })}
      >
        Saiu com esse entregador
      </button>
      <button type="button" className="venda__tirar" onClick={() => aoSair(null)}>
        Saiu sem informar o entregador
      </button>
    </div>
  );
}
