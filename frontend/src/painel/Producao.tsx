import { useCallback, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { Topo } from './Topo';

interface Encomenda {
  id: string;
  numero: number;
  estado: string;
  recebimento: 'entrega' | 'retirada';
  entrega_em: string;
  cliente: { nome: string | null; telefone: string | null };
  endereco: { logradouro: string; numero: string; bairro: string; complemento?: string } | null;
  observacao?: string | null; // detalhes da entrega escritos pelo cliente
  itens: { variante_id?: string; nome: string; quantidade: number; separado?: number }[];
  total_centavos: number;
}

const FUSO = 'America/Sao_Paulo';

// "2026-11-03" → mais ou menos um dia, sem passar por fuso.
function somarDia(dia: string, dias: number): string {
  const d = new Date(`${dia}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + dias);
  return d.toISOString().slice(0, 10);
}

function nomeDoDia(dia: string): string {
  return new Date(`${dia}T12:00:00Z`).toLocaleDateString('pt-BR', {
    timeZone: 'UTC',
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function horaDe(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR', {
    timeZone: FUSO,
    hour: '2-digit',
    minute: '2-digit',
  });
}

type Origem = 'producao' | 'pronta' | 'liberar';

// Separação da Encomenda: o doce produzido para ela fica separado e só sai do estoque quando
// a Encomenda sai. O operador pode desfazer.
function Separacao({ e, token, aoMudar }: { e: Encomenda; token: string; aoMudar: () => void }) {
  const [erro, setErro] = useState('');
  async function separar(variante_id: string, quantidade: number, origem: Origem) {
    setErro('');
    try {
      await chamarApi(`/painel/pedidos/${e.id}/separacao`, {
        method: 'POST',
        token,
        corpo: { variante_id, quantidade, origem },
      });
      aoMudar();
    } catch (falha) {
      setErro(falha instanceof ErroDaApi ? falha.message : 'Não deu para salvar.');
    }
  }
  return (
    <ul className="separacao">
      {e.itens.map((i) => {
        const separado = i.separado ?? 0;
        const falta = i.quantidade - separado;
        return (
          <li key={i.nome} className="separacao__item" aria-label={i.nome}>
            <span>
              {i.quantidade}× {i.nome}
              <strong className="separacao__conta">
                {' '}
                {separado} de {i.quantidade} separado{i.quantidade > 1 ? 's' : ''}
              </strong>
            </span>
            {i.variante_id && (
              <span className="separacao__acoes">
                {falta > 0 && (
                  <>
                    <button
                      type="button"
                      className="botao"
                      onClick={() => separar(i.variante_id!, falta, 'producao')}
                    >
                      Produzi {falta}
                    </button>
                    <button
                      type="button"
                      className="botao botao--contorno"
                      onClick={() => separar(i.variante_id!, falta, 'pronta')}
                    >
                      Usar {falta} da pronta entrega
                    </button>
                  </>
                )}
                {separado > 0 && (
                  <button
                    type="button"
                    className="venda__tirar"
                    onClick={() => separar(i.variante_id!, 1, 'liberar')}
                  >
                    Desfazer 1
                  </button>
                )}
              </span>
            )}
          </li>
        );
      })}
      {erro && (
        <li className="formulario__erro" role="alert">
          {erro}
        </li>
      )}
    </ul>
  );
}

function Cartao({ e, token, aoMudar }: { e: Encomenda; token: string; aoMudar: () => void }) {
  const aberta = e.estado === 'pago' || e.estado === 'em_preparo';
  return (
    <article className="cartao pedido" aria-label={`Encomenda nº ${e.numero}`}>
      <header className="cartao__cabeca">
        <h3 className="estoque__nome">{horaDe(e.entrega_em)}</h3>
        <span className="cartao__selo">
          {e.estado === 'entregue'
            ? 'Entregue'
            : e.estado === 'saiu'
              ? 'Saiu'
              : e.recebimento === 'retirada'
                ? 'Retirada'
                : 'Entrega'}
        </span>
      </header>
      {aberta ? (
        <Separacao e={e} token={token} aoMudar={aoMudar} />
      ) : (
        <ul className="pedido__itens">
          {e.itens.map((i) => (
            <li key={i.nome}>
              {i.quantidade}× {i.nome}
            </li>
          ))}
        </ul>
      )}
      <p className="pedido__linha">
        Encomenda nº {e.numero} · {e.cliente.nome} · {e.cliente.telefone}
      </p>
      {e.endereco && (
        <p className="pedido__linha">
          {e.endereco.logradouro}, {e.endereco.numero}
          {e.endereco.complemento ? ` (${e.endereco.complemento})` : ''}, {e.endereco.bairro}
        </p>
      )}
      {e.observacao && <p className="pedido__linha pedido__obs">Obs.: {e.observacao}</p>}
      <p className="pedido__linha">Total {formatarCentavos(e.total_centavos)}</p>
    </article>
  );
}

// Encomendas pagas do dia, em ordem de horário, e aviso das de amanhã.
export function Producao({ token }: { token: string }) {
  const [dia, setDia] = useState<string | null>(null);
  const [lista, setLista] = useState<Encomenda[] | null>(null);
  const [amanha, setAmanha] = useState<Encomenda[]>([]);
  const [semPix, setSemPix] = useState<Encomenda[]>([]);
  const [erro, setErro] = useState('');

  const carregar = useCallback(
    (escolhido: string | null) =>
      chamarApi<{ dia: string; encomendas: Encomenda[] }>(
        escolhido ? `/painel/producao?dia=${escolhido}` : '/painel/producao',
        { token },
      )
        .then((r) => {
          setDia(r.dia);
          setLista(r.encomendas);
        })
        .catch(() => setErro('O servidor está acordando. Recarregue em um minuto.')),
    [token],
  );

  useEffect(() => {
    carregar(null);
    chamarApi<{ encomendas: Encomenda[]; aguardando_pagamento?: Encomenda[] }>('/painel/alertas', {
      token,
    })
      .then((r) => {
        setAmanha(r.encomendas);
        setSemPix(r.aguardando_pagamento ?? []);
      })
      .catch(() => undefined);
  }, [carregar, token]);

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        <section className="obra__abertura obra__abertura--curta">
          <h1 className="obra__titulo">Produção</h1>
          <p className="obra__texto">Encomendas pagas, na ordem do horário de entrega.</p>
        </section>
        {erro && <p className="obra__aviso">{erro}</p>}

        {amanha.length > 0 && (
          <section className="secao producao__alerta" aria-label="Amanhã">
            <h2 className="secao__titulo">Amanhã: {amanha.length} Encomenda(s)</h2>
            <ul className="pedido__itens">
              {amanha.map((e) => (
                <li key={e.id}>
                  {horaDe(e.entrega_em)} · Encomenda nº {e.numero} ·{' '}
                  {e.itens.map((i) => `${i.quantidade}× ${i.nome}`).join(', ')}
                </li>
              ))}
            </ul>
          </section>
        )}

        {semPix.length > 0 && (
          <section
            className="secao producao__alerta producao__alerta--pix"
            aria-label="Amanhã, esperando Pix"
          >
            <h2 className="secao__titulo">Amanhã, esperando Pix: {semPix.length}</h2>
            <p className="obra__nota">Não produza antes de o Pix entrar.</p>
            <ul className="pedido__itens">
              {semPix.map((e) => (
                <li key={e.id}>
                  {horaDe(e.entrega_em)} · Encomenda nº {e.numero} · {e.cliente.nome} ·{' '}
                  {e.cliente.telefone}
                </li>
              ))}
            </ul>
          </section>
        )}

        {dia && (
          <section className="secao">
            <div className="producao__dia">
              <button
                type="button"
                className="botao botao--contorno"
                onClick={() => carregar(somarDia(dia, -1))}
              >
                Dia anterior
              </button>
              <h2 className="secao__titulo">{nomeDoDia(dia)}</h2>
              <button
                type="button"
                className="botao botao--contorno"
                onClick={() => carregar(somarDia(dia, 1))}
              >
                Próximo dia
              </button>
            </div>
            {lista && lista.length === 0 && (
              <p className="obra__aviso">Nenhuma Encomenda para este dia.</p>
            )}
            {lista?.map((e) => (
              <Cartao key={e.id} e={e} token={token} aoMudar={() => carregar(dia)} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
