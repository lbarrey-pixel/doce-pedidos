import { useCallback, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';

type EstadoDoLink = 'aguardando' | 'pago' | 'expirado';

const NOME_DO_ESTADO: Record<EstadoDoLink, string> = {
  aguardando: 'Aguardando pagamento do link',
  pago: 'Paga pelo link',
  expirado: 'Link expirado sem pagamento',
};

const CONSULTA_MS = 10_000;

// Link de pagamento da venda lançada no painel: cria o link de 30 minutos, deixa copiar ou
// mandar pelo WhatsApp e acompanha se foi pago ou expirou.
export function LinkDaVenda({
  token,
  vendaId,
  numero,
}: {
  token: string;
  vendaId: string;
  numero: number;
}) {
  const [link, setLink] = useState<{ url: string; whatsapp_url: string } | null>(null);
  const [estado, setEstado] = useState<EstadoDoLink>('aguardando');
  const [erro, setErro] = useState('');
  const [copiado, setCopiado] = useState(false);
  const [gerando, setGerando] = useState(false);

  const consultar = useCallback(
    () =>
      chamarApi<{ pedidos: { id: string; pagamento_link?: EstadoDoLink | null }[] }>(
        '/painel/pedidos',
        { token },
      )
        .then((r) => {
          const atual = r.pedidos.find((p) => p.id === vendaId)?.pagamento_link;
          if (atual) setEstado(atual);
        })
        .catch(() => undefined),
    [token, vendaId],
  );

  useEffect(() => {
    if (!link || estado !== 'aguardando') return;
    consultar();
    const vez = setInterval(consultar, CONSULTA_MS);
    return () => clearInterval(vez);
  }, [link, estado, consultar]);

  async function gerar() {
    setErro('');
    setGerando(true);
    try {
      const r = await chamarApi<{ url: string; whatsapp_url: string }>(
        `/painel/vendas/${vendaId}/link`,
        { method: 'POST', token },
      );
      setLink(r);
      setEstado('aguardando');
      setCopiado(false);
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para gerar o link. Tente de novo.');
    } finally {
      setGerando(false);
    }
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(link?.url ?? '');
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <section className="cartao pedido" aria-label={`Link de pagamento da venda nº ${numero}`}>
      <h2 className="estoque__nome">Pagamento da venda nº {numero}</h2>
      {link && (
        <>
          <label className="campo">
            <span className="campo__rotulo">Link de pagamento (vale 30 minutos)</span>
            <input className="campo__entrada" readOnly value={link.url} />
          </label>
          <div className="pedido__acoes">
            <button type="button" className="botao" onClick={copiar}>
              {copiado ? 'Link copiado' : 'Copiar'}
            </button>
            <a
              className="botao botao--contorno"
              href={link.whatsapp_url}
              target="_blank"
              rel="noreferrer"
            >
              Mandar pelo WhatsApp
            </a>
          </div>
          <p className={estado === 'expirado' ? 'pedido__alerta' : 'pedido__linha'}>
            {NOME_DO_ESTADO[estado]}
          </p>
        </>
      )}
      {estado === 'expirado' && (
        <p className="pedido__linha">
          Venda cancelada e estoque devolvido. Para cobrar de novo, lance a venda outra vez.
        </p>
      )}
      {!link && (
        <button type="button" className="botao" disabled={gerando} onClick={gerar}>
          Gerar link
        </button>
      )}
      {erro && (
        <p className="formulario__erro" role="alert">
          {erro}
        </p>
      )}
    </section>
  );
}
