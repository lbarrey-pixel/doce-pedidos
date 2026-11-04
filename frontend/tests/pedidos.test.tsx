import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Pedidos } from '../src/painel/Pedidos';
import { apiFalsa } from './estoque-fixtures';

vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: { auth: { signOut: vi.fn() } },
}));

afterEach(() => vi.unstubAllGlobals());

const BASE = {
  canal: 'app',
  recebimento: 'entrega',
  tipo_entrega: 'pronta_entrega',
  cliente: { nome: 'Ana Paula', telefone: '11999991234' },
  endereco: { logradouro: 'R. das Acácias', numero: '220', bairro: 'Jardim Azul' },
  itens: [{ nome: 'Bolo de Pote Red Velvet · Individual', quantidade: 2 }],
  subtotal_centavos: 3980,
  desconto_centavos: 0,
  taxa_entrega_centavos: 1400,
  total_centavos: 5380,
  diferenca_pagamento_centavos: 0,
  devolvido_centavos: 0,
  criado_em: '2026-11-02T18:00:00+00:00',
  expira_em: '2026-11-02T18:30:00+00:00',
  entrega_a_partir_de: '2026-11-02T18:40:00+00:00',
};
const LISTA = {
  pedidos: [
    { ...BASE, id: 'a', numero: 42, estado: 'aguardando_pagamento' },
    { ...BASE, id: 'b', numero: 41, estado: 'pago' },
  ],
};

it('destaca o novo e confirma o Pix com o valor esperado', async () => {
  const chamadas = apiFalsa({
    'GET /painel/pedidos': () => [200, LISTA],
    'POST /painel/pedidos/a/confirmar-pagamento': () => [200, { estado: 'pago' }],
  });
  render(<Pedidos token="t" />);
  const novo = await screen.findByRole('article', { name: /Pedido nº 42/ });
  expect(within(novo).getByText('Esperando o Pix')).toBeInTheDocument();
  expect(within(novo).getByText(/R\. das Acácias, 220/)).toBeInTheDocument();
  await userEvent.click(within(novo).getByRole('button', { name: 'Recebi R$ 53,80' }));
  expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({
    valor_recebido_centavos: 5380,
  });
});

it('valor diferente pede confirmação explícita da diferença', async () => {
  const chamadas = apiFalsa({
    'GET /painel/pedidos': () => [200, LISTA],
    'POST /painel/pedidos/a/confirmar-pagamento': () => [200, { estado: 'pago' }],
  });
  render(<Pedidos token="t" />);
  const novo = await screen.findByRole('article', { name: /Pedido nº 42/ });
  await userEvent.click(within(novo).getByRole('button', { name: 'Entrou outro valor' }));
  await userEvent.type(within(novo).getByLabelText('Valor que entrou'), '53');
  await userEvent.click(within(novo).getByRole('button', { name: /Confirmar com diferença/ }));
  expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({
    valor_recebido_centavos: 5300,
    aceitar_diferenca: true,
  });
});

it('avança o estado do pedido pago', async () => {
  const chamadas = apiFalsa({
    'GET /painel/pedidos': () => [200, LISTA],
    'POST /painel/pedidos/b/estado': () => [200, { estado: 'em_preparo' }],
  });
  render(<Pedidos token="t" />);
  const pago = await screen.findByRole('article', { name: /Pedido nº 41/ });
  await userEvent.click(within(pago).getByRole('button', { name: 'Começar preparo' }));
  expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({ estado: 'em_preparo' });
});

it('saída com entregador escolhido e previsão de entregue', async () => {
  const emPreparo = { ...BASE, id: 'c', numero: 43, estado: 'em_preparo' };
  const chamadas = apiFalsa({
    'GET /painel/pedidos': () => [200, { pedidos: [emPreparo] }],
    'GET /painel/entregadores': () => [
      200,
      { entregadores: [{ nome: 'Coop. Motoboys Express', telefone: '1133334444' }] },
    ],
    'POST /painel/pedidos/c/estado': () => [200, { estado: 'saiu' }],
  });
  render(<Pedidos token="t" />);
  const card = await screen.findByRole('article', { name: /Pedido nº 43/ });
  await userEvent.click(within(card).getByRole('button', { name: 'Saiu para entrega' }));
  await userEvent.click(
    await within(card).findByRole('button', { name: 'Coop. Motoboys Express' }),
  );
  expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({
    estado: 'saiu',
    entregador: { nome: 'Coop. Motoboys Express', telefone: '1133334444' },
  });
});

it('mostra quem levou e quando vira entregue', async () => {
  const saiu = {
    ...BASE,
    id: 'd',
    numero: 44,
    estado: 'saiu',
    entregador: { nome: 'Carlos', telefone: '11999990000' },
    entregue_previsto_em: '2026-11-02T18:30:00+00:00',
  };
  apiFalsa({ 'GET /painel/pedidos': () => [200, { pedidos: [saiu] }] });
  render(<Pedidos token="t" />);
  const card = await screen.findByRole('article', { name: /Pedido nº 44/ });
  expect(within(card).getByText(/Saiu com Carlos; vira entregue às 15:30/)).toBeInTheDocument();
});

it('mostra a observação que o cliente escreveu', async () => {
  apiFalsa({
    'GET /painel/pedidos': () => [
      200,
      {
        pedidos: [
          {
            ...BASE,
            id: 'c',
            numero: 43,
            estado: 'pago',
            observacao: 'Hospital: entregar para Maria na recepção',
          },
        ],
      },
    ],
  });
  render(<Pedidos token="t" />);
  const pedido = await screen.findByRole('article', { name: /Pedido nº 43/ });
  expect(
    within(pedido).getByText('Obs.: Hospital: entregar para Maria na recepção'),
  ).toBeInTheDocument();
});
