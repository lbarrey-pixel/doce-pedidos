// Contrato da loja (contracts/api.md: /loja/*).
export interface VarianteLoja {
  id: string;
  produto: string;
  tamanho: string;
  descricao: string;
  ingredientes: string;
  porcoes: string;
  peso_g: number | null;
  foto: string;
  preco_centavos: number;
  pronta: number;
  estado_disponibilidade: 'pronta_entrega' | 'encomenda';
}

export interface Cardapio {
  loja_aberta: boolean;
  abre_as: string;
  abre_as_hora?: string; // "12:00"
  fecha_as_hora?: string; // "00:00" = meia-noite
  primeira_encomenda: string;
  primeiro_agendamento?: string | null; // pronta entrega agendada para hoje
  tempo_preparo_min?: number;
  whatsapp_url?: string | null; // botão "Falar com a loja"
  pedido_minimo_centavos: number;
  desconto_app_percentual: number;
  categorias: { nome: string; variantes: VarianteLoja[] }[];
}

// Link do gateway de checkout, ou Pix copia e cola quando não há gateway ou ele está fora do ar.
export type PagamentoDoPedido = { tipo: 'link'; url: string } | { tipo: 'pix_manual' };

export interface PedidoCriado {
  id: string;
  numero: number;
  estado: string;
  tipo_entrega: 'pronta_entrega' | 'encomenda';
  recebimento: 'entrega' | 'retirada';
  total_centavos: number;
  subtotal_centavos?: number;
  desconto_centavos?: number;
  taxa_entrega_centavos?: number;
  entrega_a_partir_de: string | null;
  expira_em?: string;
  pix: { copia_e_cola: string } | null;
  pagamento?: PagamentoDoPedido | null;
  forma_pagamento?: 'pix' | 'cartao' | 'pix_manual' | null;
  a_estornar?: boolean; // pagou e o pedido está cancelado: a loja faz o estorno
  whatsapp_url?: string | null;
}

// Foto do item: URL absoluta vale como veio; caminho relativo é servido pelo próprio site
// (JPEG vira WebP). Sem foto, o cardápio mostra a inicial do produto.
export function urlDaFoto(foto: string): string | null {
  if (!foto) return null;
  if (/^https?:\/\//.test(foto)) return foto;
  return '/' + foto.replace(/\.jpe?g$/i, '.webp');
}
