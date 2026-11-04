import { ErroDaApi, chamarApi } from '../src/comum/api';

function responder(status: number, corpo: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(corpo), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('chamarApi', () => {
  it('devolve o JSON e usa o prefixo /api/v1', async () => {
    const fetch = responder(200, { total_centavos: 5380 });
    vi.stubGlobal('fetch', fetch);
    await expect(chamarApi('/loja/cardapio')).resolves.toEqual({ total_centavos: 5380 });
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/loja/cardapio');
  });

  it('transforma o erro da API em mensagem legível', async () => {
    vi.stubGlobal(
      'fetch',
      responder(422, { erro: 'abaixo_do_minimo', mensagem: 'Pedido mínimo de R$ 17,90' }),
    );
    const erro = (await chamarApi('/loja/pedidos', { method: 'POST', corpo: {} }).catch(
      (e: unknown) => e,
    )) as ErroDaApi;
    expect(erro).toBeInstanceOf(ErroDaApi);
    expect(erro.codigo).toBe('abaixo_do_minimo');
    expect(erro.message).toBe('Pedido mínimo de R$ 17,90');
  });

  it('mensagem padrão quando a API não responde no formato', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('oops', { status: 500 })));
    const erro = (await chamarApi('/x').catch((e: unknown) => e)) as ErroDaApi;
    expect(erro.codigo).toBe('erro_inesperado');
  });

  it('envia o token do Operador no painel', async () => {
    const fetch = responder(200, {});
    vi.stubGlobal('fetch', fetch);
    await chamarApi('/painel/estoque', { token: 'abc' });
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer abc');
  });
});
