// Dados de teste no formato de GET /painel/estoque.
export const ESTOQUE = {
  variantes: [
    {
      id: 'lc-medio',
      produto: 'Torta de Limão',
      tamanho: 'Fatia',
      categoria: 'Tortas',
      controle_estoque: 'congelavel',
      preco_centavos: 6990,
      ativa: true,
      foto: '',
      saldo: { pronta: 3, separada: 0, congelada: 2, descongelando: 1, reserva: 0 },
      descongelando: [{ quantidade: 1, pronta_as: '2026-10-30T19:00:00+00:00' }],
    },
    {
      id: 'doce-ind',
      produto: 'Bolo de Pote Red Velvet',
      tamanho: 'Individual',
      categoria: 'Bolos de pote',
      controle_estoque: 'congelavel',
      preco_centavos: 1990,
      ativa: true,
      foto: '',
      saldo: { pronta: 1, separada: 0, congelada: 0, descongelando: 0, reserva: 0 },
      descongelando: [],
    },
    {
      id: 'coca',
      produto: 'Refrigerante de Guaraná',
      tamanho: 'Lata 350 ml',
      categoria: 'Bebidas',
      controle_estoque: 'reserva',
      preco_centavos: 890,
      ativa: true,
      foto: '',
      saldo: { pronta: 6, separada: 0, congelada: 0, descongelando: 0, reserva: 6 },
      descongelando: [],
    },
  ],
};

export type Chamada = { url: string; metodo: string; corpo: unknown };

export function apiFalsa(respostas: Record<string, (corpo: unknown) => [number, unknown]>) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? 'GET';
      const corpo =
        typeof init?.body === 'string' ? JSON.parse(init.body) : (init?.body ?? undefined);
      chamadas.push({ url: String(url), metodo, corpo });
      const chave = Object.keys(respostas).find((k) => {
        const [m, caminho] = k.split(' ');
        return m === metodo && String(url).endsWith(caminho);
      });
      const [status, resposta] = chave ? respostas[chave](corpo) : [404, {}];
      return Promise.resolve(
        new Response(JSON.stringify(resposta), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  return chamadas;
}
