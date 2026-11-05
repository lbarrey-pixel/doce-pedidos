import qrcode from 'qrcode-generator';
import { useEffect, useMemo, useState } from 'react';
import { chamarApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { abrirPagamento } from '../comum/rotas';
import { lerPedido } from './carrinho';
import type { PedidoCriado } from './tipos';

const FUSO = { timeZone: 'America/Sao_Paulo' } as const;

function hora(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString('pt-BR', { ...FUSO, hour: '2-digit', minute: '2-digit' });
}

const CONSULTA_MS = 5_000;

// Dados que o gateway devolve na URL de volta ao app. Lidos uma vez e tirados da barra de
// endereço, para recarregar a página não conferir de novo.
function lerVolta(): { transaction_nsu: string; slug: string } | null {
  const q = new URLSearchParams(window.location.search);
  const transaction_nsu = q.get('transaction_nsu');
  const slug = q.get('slug');
  if (!q.has('transaction_nsu') && !q.has('slug') && !q.has('order_nsu')) return null;
  window.history.replaceState(null, '', window.location.pathname);
  return transaction_nsu && slug ? { transaction_nsu, slug } : null;
}

// Pagamento e acompanhamento: pagar no gateway, Pix copia e cola de reserva, WhatsApp e o estado.
export function Pagamento({ id }: { id: string }) {
  const guardado = useMemo(() => lerPedido<PedidoCriado>(id), [id]);
  const [pedido, setPedido] = useState<PedidoCriado | null>(guardado);
  const [copiado, setCopiado] = useState(false);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    let ativo = true;
    let espera: ReturnType<typeof setTimeout>;
    const volta = lerVolta();
    const caminho = `/loja/pedidos/${encodeURIComponent(id)}`;
    function aplicar(r: PedidoCriado) {
      setPedido((antes) => ({
        ...antes,
        ...r,
        whatsapp_url: r.whatsapp_url ?? antes?.whatsapp_url ?? null,
      }));
    }
    async function buscar() {
      try {
        const r = await chamarApi<PedidoCriado>(caminho);
        if (!ativo) return;
        aplicar(r);
        if (r.estado === 'aguardando_pagamento') espera = setTimeout(buscar, CONSULTA_MS);
      } catch {
        if (ativo) setFalhou(true);
      }
    }
    async function iniciar() {
      if (volta) {
        try {
          const r = await chamarApi<PedidoCriado>(`${caminho}/conferir`, {
            method: 'POST',
            corpo: volta,
          });
          if (ativo) aplicar(r);
        } catch {
          /* a consulta abaixo mostra o estado de verdade */
        }
      }
      if (ativo) buscar();
    }
    iniciar();
    return () => {
      ativo = false;
      clearTimeout(espera);
    };
  }, [id]);

  const pix = pedido?.pix?.copia_e_cola ?? null;
  const link = pedido?.pagamento?.tipo === 'link' ? pedido.pagamento.url : null;
  const svg = useMemo(() => {
    if (!pix) return '';
    const qr = qrcode(0, 'M');
    qr.addData(pix);
    qr.make();
    return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }, [pix]);

  if (!pedido) {
    return <p className="obra__aviso">{falhou ? 'Pedido não encontrado.' : 'Abrindo o pedido…'}</p>;
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(pix ?? '');
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }

  const retirada = pedido.recebimento === 'retirada';
  return (
    <section className="pagamento">
      <h1 className="checkout__titulo">Pedido nº {pedido.numero}</h1>
      <p className="pagamento__total">{formatarCentavos(pedido.total_centavos)}</p>

      {pedido.estado === 'aguardando_pagamento' && (
        <>
          <p className="pagamento__estado">Aguardando pagamento</p>
          {link ? (
            <>
              <p className="obra__texto">
                Pague por Pix ou cartão na página de pagamento. Quando o pagamento for confirmado, o
                seu pedido começa a ser preparado.
              </p>
              <button type="button" className="botao" onClick={() => abrirPagamento(link)}>
                Pagar
              </button>
            </>
          ) : (
            pix && (
              <>
                <p className="obra__texto">
                  Pague com Pix copiando o código abaixo no app do seu banco. A loja confirma o
                  pagamento e o seu pedido começa a ser preparado.
                </p>
                <code className="pagamento__codigo">{pix}</code>
                <button type="button" className="botao" onClick={copiar}>
                  {copiado ? 'Código copiado' : 'Copiar código Pix'}
                </button>
                <div
                  className="pagamento__qr"
                  aria-label="QR code do Pix"
                  role="img"
                  dangerouslySetInnerHTML={{ __html: svg }}
                />
              </>
            )
          )}
          {pedido.expira_em && (
            <p className="obra__nota">O pedido fica reservado até as {hora(pedido.expira_em)}.</p>
          )}
        </>
      )}

      {['pago', 'em_preparo'].includes(pedido.estado) && (
        <p className="pagamento__estado">
          Pagamento confirmado.{' '}
          {pedido.tipo_entrega === 'encomenda'
            ? 'Sua Encomenda está agendada.'
            : retirada
              ? `Pronto para retirar a partir das ${hora(pedido.entrega_a_partir_de)}.`
              : `Chega até as ${hora(pedido.entrega_a_partir_de)}.`}
        </p>
      )}
      {pedido.estado === 'saiu' && <p className="pagamento__estado">Saiu para entrega.</p>}
      {pedido.estado === 'entregue' && <p className="pagamento__estado">Entregue. Bom apetite!</p>}
      {pedido.estado === 'cancelado' && (
        <p className="pagamento__estado">
          {pedido.a_estornar
            ? 'Este pedido foi cancelado. Fale com a loja pelo WhatsApp para o estorno.'
            : 'Este pedido foi cancelado. Se você já pagou, fale com a loja pelo WhatsApp.'}
        </p>
      )}

      {pedido.whatsapp_url && (
        <a
          className="botao botao--contorno"
          href={pedido.whatsapp_url}
          target="_blank"
          rel="noreferrer"
        >
          {pedido.a_estornar ? 'Falar com a loja no WhatsApp' : 'Enviar no WhatsApp da loja'}
        </a>
      )}
    </section>
  );
}
