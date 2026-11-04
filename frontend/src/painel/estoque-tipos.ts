// Contrato de GET /painel/estoque e lançamentos do operador.
export type Controle = 'congelavel' | 'reserva' | 'simples';
export type EstadoSaldo = 'pronta' | 'separada' | 'congelada' | 'descongelando' | 'reserva';
export type Saldo = Record<EstadoSaldo, number>;

export interface VarianteEstoque {
  id: string;
  produto: string;
  tamanho: string;
  categoria: string;
  controle_estoque: Controle;
  preco_centavos: number;
  ativa: boolean;
  foto: string;
  saldo: Saldo;
  descongelando: { quantidade: number; pronta_as: string }[];
}

export const NOME_DO_ESTADO: Record<EstadoSaldo, string> = {
  pronta: 'Pronta entrega',
  separada: 'Separada',
  congelada: 'Reserva congelada',
  descongelando: 'Descongelando',
  reserva: 'Estoque reserva',
};

// Estados que cada controle mostra e em que perda e ajuste podem mexer.
export const ESTADOS_DO_CONTROLE: Record<Controle, EstadoSaldo[]> = {
  congelavel: ['pronta', 'congelada', 'descongelando'],
  reserva: ['pronta', 'reserva'],
  simples: ['pronta'],
};

export interface Acao {
  id: string;
  rotulo: string;
  tipo: string;
  para?: EstadoSaldo; // estado de destino fixo (produção, entrada)
  escolheEstado?: 'de' | 'ajuste'; // perda escolhe de onde sai; ajuste escolhe estado e sentido
}

const PERDA: Acao = { id: 'perda', rotulo: 'Perda', tipo: 'perda', escolheEstado: 'de' };
const AJUSTE: Acao = { id: 'ajuste', rotulo: 'Ajuste', tipo: 'ajuste', escolheEstado: 'ajuste' };

export const ACOES: Record<Controle, Acao[]> = {
  congelavel: [
    { id: 'prod-pronta', rotulo: 'Produção pronta', tipo: 'producao', para: 'pronta' },
    { id: 'prod-congelada', rotulo: 'Produção congelada', tipo: 'producao', para: 'congelada' },
    { id: 'descongelar', rotulo: 'Começar a descongelar', tipo: 'inicio_descongelamento' },
    { id: 'congelar', rotulo: 'Congelar', tipo: 'congelamento' },
    PERDA,
    AJUSTE,
  ],
  reserva: [
    { id: 'entrada-pronta', rotulo: 'Entrada na loja', tipo: 'entrada', para: 'pronta' },
    { id: 'entrada-reserva', rotulo: 'Entrada na reserva', tipo: 'entrada', para: 'reserva' },
    { id: 'transferir', rotulo: 'Transferir para a loja', tipo: 'transferencia' },
    PERDA,
    AJUSTE,
  ],
  simples: [{ id: 'entrada', rotulo: 'Entrada', tipo: 'entrada', para: 'pronta' }, PERDA, AJUSTE],
};

export function nomeDaVariante(v: Pick<VarianteEstoque, 'produto' | 'tamanho'>): string {
  return v.tamanho ? `${v.produto} · ${v.tamanho}` : v.produto;
}

export function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Sao_Paulo',
  });
}
