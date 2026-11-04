import qrcode from 'qrcode-generator';
import { useEffect, useMemo, useState } from 'react';
import { chamarApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { lerPedido } from './carrinho';
import type { PedidoCriado } from './tipos';

const FUSO = { timeZone: 'America/Sao_Paulo' } as const;

function hora(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString('pt-BR', { ...FUSO, hour: '2-digit', minute: '2-digit' });
}

// Pagamento e acompanhamento: Pix copia e cola, QR, WhatsApp e o estado.
export function Pagamento({ id }: { id: string }) {
  const guardado = useMemo(() => lerPedido<PedidoCriado>(id), [id]);
  const [pedido, setPedido] = useState<PedidoCriado | null>(guardado);
  const [copiado, setCopiado] = useState(false);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    let ativo = true;
    let espera: ReturnType<typeof setTimeout>;
    async function buscar() {
      try {
        const r = await chamarApi<PedidoCriado>(`/loja/pedidos/${encodeURIComponent(id)}`);
        if (!ativo) return;
        setPedido((antes) => ({ ...antes, ...r, whatsapp_url: antes?.whatsapp_url ?? null }));
        if (r.estado === 'aguardando_pagamento') espera = setTimeout(buscar, 10_000);
      } catch {
        if (ativo) setFalhou(true);
      }
    }
    buscar();
    return () => {
      ativo = false;
      clearTimeout(espera);
    };
  }, [id]);

  const pix = pedido?.pix?.copia_e_cola ?? null;
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
          <p className="obra__texto">
            Pague com Pix copiando o código abaixo no app do seu banco. A loja confirma o pagamento
            e o seu pedido começa a ser preparado.
          </p>
          {pix && (
            <>
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
          Este pedido foi cancelado. Se você já pagou, fale com a loja pelo WhatsApp.
        </p>
      )}

      {pedido.whatsapp_url && (
        <a
          className="botao botao--contorno"
          href={pedido.whatsapp_url}
          target="_blank"
          rel="noreferrer"
        >
          Enviar no WhatsApp da loja
        </a>
      )}
    </section>
  );
}
