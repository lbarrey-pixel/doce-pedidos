import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Loja } from '../src/loja/Loja';
import { Simulador } from '../src/loja/Simulador';
import { apiFalsa } from './estoque-fixtures';
import { CARDAPIO } from './loja-fixtures';

const abrirPagamento = vi.fn();
vi.mock('../src/comum/rotas', async (original) => ({
  ...(await original<typeof import('../src/comum/rotas')>()),
  abrirPagamento: (url: string) => abrirPagamento(url),
}));
vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: { auth: { signOut: vi.fn() } },
}));

beforeEach(() => {
  localStorage.clear();
  abrirPagamento.mockClear();
  window.history.replaceState(null, '', '/');
});
afterEach(() => vi.unstubAllGlobals());

const LINK = 'https://pagar.doceatelie.example/p1';
const PEDIDO = {
  id: 'p1',
  numero: 42,
  estado: 'aguardando_pagamento',
  tipo_entrega: 'pronta_entrega',
  recebimento: 'retirada',
  total_centavos: 3980,
  entrega_a_partir_de: '2026-11-02T18:10:00+00:00',
  expira_em: '2026-11-02T18:30:00+00:00',
  pagamento: { tipo: 'link', url: LINK },
  pix: null,
  whatsapp_url: 'https://wa.me/5511900000002?text=x',
};

async function fecharPedido() {
  await userEvent.click(await screen.findByRole('button', { name: /Bolo de Pote Red Velvet/ }));
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /Adicionar/ }),
  );
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.click(screen.getByRole('radio', { name: /Retirar na loja/ }));
  await userEvent.type(screen.getByLabelText('Seu nome'), 'Ana Paula');
  await userEvent.type(screen.getByLabelText('WhatsApp'), '11900000001');
  await userEvent.click(screen.getByRole('button', { name: 'Fazer pedido e pagar' }));
}

it('fechar o pedido com link leva o cliente ao gateway e deixa o botão Pagar na página', async () => {
  apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'POST /loja/pedidos': () => [201, PEDIDO],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
  render(<Loja />);
  await fecharPedido();
  expect(await screen.findByRole('heading', { name: 'Pedido nº 42' })).toBeInTheDocument();
  expect(abrirPagamento).toHaveBeenCalledWith(LINK);
  expect(screen.getByText('Aguardando pagamento')).toBeInTheDocument();
  expect(screen.queryByText(/Copiar código Pix/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Pagar' }));
  expect(abrirPagamento).toHaveBeenCalledTimes(2);
});

it('sem link (gateway fora do ar) mostra o Pix copia e cola e não sai da página', async () => {
  const reserva = {
    ...PEDIDO,
    pagamento: { tipo: 'pix_manual' },
    pix: { copia_e_cola: '00020126PIXDE39,80' },
  };
  apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'POST /loja/pedidos': () => [201, reserva],
    'GET /loja/pedidos/p1': () => [200, reserva],
  });
  render(<Loja />);
  await fecharPedido();
  expect(await screen.findByText('00020126PIXDE39,80')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Copiar código Pix' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Pagar' })).not.toBeInTheDocument();
  expect(abrirPagamento).not.toHaveBeenCalled();
});

it('na volta do gateway confere o pagamento, limpa a URL e mostra o pedido pago', async () => {
  const pago = { ...PEDIDO, estado: 'pago', pagamento: null, forma_pagamento: 'pix' };
  const chamadas = apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/pedidos/p1/conferir': () => [200, pago],
    'GET /loja/pedidos/p1': () => [200, pago],
  });
  window.history.replaceState(
    null,
    '',
    '/pedido/p1?transaction_nsu=nsu-1&slug=slug-1&order_nsu=p1',
  );
  render(<Loja />);
  expect(await screen.findByText(/Pagamento confirmado/)).toBeInTheDocument();
  expect(chamadas.find((c) => c.url.endsWith('/loja/pedidos/p1/conferir'))?.corpo).toEqual({
    transaction_nsu: 'nsu-1',
    slug: 'slug-1',
  });
  expect(window.location.search).toBe('');
});

it('volta sem os dados do pagamento não confere, só consulta o estado', async () => {
  const chamadas = apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
  window.history.replaceState(null, '', '/pedido/p1?order_nsu=p1');
  render(<Loja />);
  expect(await screen.findByText('Aguardando pagamento')).toBeInTheDocument();
  expect(chamadas.some((c) => c.url.endsWith('/conferir'))).toBe(false);
});

it('pedido cancelado com pagamento a estornar manda falar com a loja', async () => {
  const cancelado = { ...PEDIDO, estado: 'cancelado', pagamento: null, a_estornar: true };
  apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'GET /loja/pedidos/p1': () => [200, cancelado],
  });
  window.history.replaceState(null, '', '/pedido/p1');
  render(<Loja />);
  expect(
    await screen.findByText(/Fale com a loja pelo WhatsApp para o estorno/),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Falar com a loja no WhatsApp' })).toBeInTheDocument();
});

it('o simulador paga e volta ao app com os dados da conferência', async () => {
  const chamadas = apiFalsa({
    'POST /gateway/simulado/pagar': () => [200, { transaction_nsu: 'nsu-9', slug: 'slug-9' }],
  });
  render(<Simulador id="p1" />);
  await userEvent.selectOptions(screen.getByLabelText('Parcelas no cartão'), '3');
  await userEvent.click(screen.getByRole('button', { name: 'Pagar com cartão' }));
  await waitFor(() => expect(window.location.pathname).toBe('/pedido/p1'));
  expect(window.location.search).toBe('?transaction_nsu=nsu-9&slug=slug-9');
  expect(chamadas[0].corpo).toEqual({ pedido_id: 'p1', metodo: 'credit_card', parcelas: 3 });
});

it('o simulador mostra o erro quando o link não existe', async () => {
  apiFalsa({
    'POST /gateway/simulado/pagar': () => [
      404,
      { erro: 'nao_encontrado', mensagem: 'Link de pagamento não encontrado.' },
    ],
  });
  render(<Simulador id="x" />);
  await userEvent.click(screen.getByRole('button', { name: 'Pagar com Pix' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Link de pagamento não encontrado.');
});
