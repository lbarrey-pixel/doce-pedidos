// Cliente HTTP da loja e do painel. Erros da API vêm como {"erro", "mensagem"}.
const BASE = (import.meta.env.VITE_API_URL ?? '') + '/api/v1';

export class ErroDaApi extends Error {
  constructor(
    readonly codigo: string,
    mensagem: string,
    readonly status: number,
    readonly extra: Record<string, unknown> = {}, // campos a mais do erro (ex.: disponivel)
  ) {
    super(mensagem);
  }
}

type Opcoes = { method?: string; corpo?: unknown; token?: string };

export async function chamarApi<T = unknown>(caminho: string, opcoes: Opcoes = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (opcoes.corpo !== undefined) headers['Content-Type'] = 'application/json';
  if (opcoes.token) headers.Authorization = `Bearer ${opcoes.token}`;
  const resposta = await fetch(BASE + caminho, {
    method: opcoes.method ?? 'GET',
    headers,
    body: opcoes.corpo === undefined ? undefined : JSON.stringify(opcoes.corpo),
  });
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    if (corpo && typeof corpo.erro === 'string' && typeof corpo.mensagem === 'string') {
      const { erro, mensagem, ...extra } = corpo;
      throw new ErroDaApi(erro, mensagem, resposta.status, extra);
    }
    throw new ErroDaApi('erro_inesperado', 'Algo deu errado. Tente de novo.', resposta.status);
  }
  return corpo as T;
}
