import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Estoque } from '../src/painel/Estoque';
import { apiFalsa, ESTOQUE } from './estoque-fixtures';

vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: { auth: { signOut: vi.fn() } },
}));

afterEach(() => vi.unstubAllGlobals());

const SALDO = { pronta: 5, separada: 0, congelada: 2, descongelando: 1, reserva: 0 };

it('mostra o saldo de cada lugar conforme o controle da Variante', async () => {
  apiFalsa({ 'GET /painel/estoque': () => [200, ESTOQUE] });
  render(<Estoque token="t" />);
  const doce = await screen.findByRole('article', { name: /Torta de Limão · Fatia/ });
  expect(within(doce).getByText('Pronta entrega')).toBeInTheDocument();
  expect(within(doce).getByText('Reserva congelada')).toBeInTheDocument();
  expect(within(doce).getByText(/pronto às/)).toBeInTheDocument();
  const coca = screen.getByRole('article', { name: /Refrigerante de Guaraná · Lata 350 ml/ });
  expect(within(coca).getByText('Estoque reserva')).toBeInTheDocument();
  expect(within(coca).queryByText('Reserva congelada')).not.toBeInTheDocument();
});

it('lança produção pronta com a quantidade escolhida', async () => {
  const chamadas = apiFalsa({
    'GET /painel/estoque': () => [200, ESTOQUE],
    'POST /painel/estoque/movimentos': () => [200, { saldo: SALDO }],
  });
  render(<Estoque token="t" />);
  const doce = await screen.findByRole('article', { name: /Torta de Limão · Fatia/ });
  await userEvent.click(within(doce).getByRole('button', { name: 'Lançar' }));
  await userEvent.click(within(doce).getByRole('radio', { name: 'Produção pronta' }));
  await userEvent.click(within(doce).getByRole('button', { name: 'Mais um' }));
  await userEvent.click(within(doce).getByRole('button', { name: 'Confirmar' }));
  const post = chamadas.find((c) => c.metodo === 'POST');
  expect(post?.corpo).toEqual({
    variante_id: 'lc-medio',
    tipo: 'producao',
    quantidade: 2,
    para_estado: 'pronta',
  });
  expect(await within(doce).findByText('Lançado.')).toBeInTheDocument();
});

it('perda pede motivo e mostra a falta de estoque recusada pela API', async () => {
  const chamadas = apiFalsa({
    'GET /painel/estoque': () => [200, ESTOQUE],
    'POST /painel/estoque/movimentos': () => [
      422,
      { erro: 'falta_estoque', mensagem: 'Só há 1 em pronta.', disponivel: 1 },
    ],
  });
  render(<Estoque token="t" />);
  const doce = await screen.findByRole('article', { name: /Red Velvet · Individual/ });
  await userEvent.click(within(doce).getByRole('button', { name: 'Lançar' }));
  await userEvent.click(within(doce).getByRole('radio', { name: 'Perda' }));
  await userEvent.click(within(doce).getByRole('button', { name: 'Mais um' }));
  await userEvent.click(within(doce).getByRole('button', { name: 'Confirmar' }));
  expect(within(doce).getByText('Diga o motivo.')).toBeInTheDocument();
  expect(chamadas.some((c) => c.metodo === 'POST')).toBe(false);
  await userEvent.type(within(doce).getByLabelText('Motivo'), 'caiu');
  await userEvent.click(within(doce).getByRole('button', { name: 'Confirmar' }));
  expect(await within(doce).findByText('Só há 1 em pronta.')).toBeInTheDocument();
  expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toMatchObject({
    tipo: 'perda',
    de_estado: 'pronta',
    motivo: 'caiu',
  });
});

it('bebida oferece entrada e transferência, não produção', async () => {
  apiFalsa({ 'GET /painel/estoque': () => [200, ESTOQUE] });
  render(<Estoque token="t" />);
  const coca = await screen.findByRole('article', { name: /Refrigerante de Guaraná/ });
  await userEvent.click(within(coca).getByRole('button', { name: 'Lançar' }));
  expect(within(coca).getByRole('radio', { name: 'Transferir para a loja' })).toBeInTheDocument();
  expect(within(coca).queryByRole('radio', { name: 'Produção pronta' })).not.toBeInTheDocument();
});

it('busca filtra pelo nome', async () => {
  apiFalsa({ 'GET /painel/estoque': () => [200, ESTOQUE] });
  render(<Estoque token="t" />);
  await screen.findByRole('article', { name: /Refrigerante de Guaraná/ });
  await userEvent.type(screen.getByRole('searchbox'), 'velvet');
  expect(
    screen.queryByRole('article', { name: /Refrigerante de Guaraná/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole('article', { name: /Red Velvet/ })).toBeInTheDocument();
});
