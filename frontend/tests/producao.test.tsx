import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Producao } from '../src/painel/Producao';
import { apiFalsa } from './estoque-fixtures';

vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: { auth: { signOut: vi.fn() } },
}));

afterEach(() => vi.unstubAllGlobals());

const ENCOMENDA = {
  id: 'e1',
  numero: 77,
  estado: 'pago',
  recebimento: 'entrega',
  entrega_em: '2026-11-03T15:00:00-03:00',
  cliente: { nome: 'Ana Paula', telefone: '11999991234' },
  endereco: { logradouro: 'R. das Acácias', numero: '220', bairro: 'Jardim Azul' },
  itens: [{ nome: 'Torta de Limão · Inteira', quantidade: 1 }],
  total_centavos: 15590,
};

it('mostra a produção do dia e avisa as Encomendas de amanhã', async () => {
  apiFalsa({
    'GET /painel/producao': () => [200, { dia: '2026-11-03', encomendas: [ENCOMENDA] }],
    'GET /painel/alertas': () => [
      200,
      {
        amanha: '2026-11-04',
        encomendas: [{ ...ENCOMENDA, id: 'e2', numero: 78 }],
        aguardando_pagamento: [
          { ...ENCOMENDA, id: 'e3', numero: 79, estado: 'aguardando_pagamento' },
        ],
      },
    ],
  });
  render(<Producao token="t" />);
  const alerta = await screen.findByRole('region', { name: 'Amanhã' });
  expect(within(alerta).getByText(/Encomenda nº 78/)).toBeInTheDocument();
  const semPix = screen.getByRole('region', { name: 'Amanhã, esperando Pix' });
  expect(within(semPix).getByText(/Encomenda nº 79/)).toBeInTheDocument();
  expect(within(alerta).queryByText(/nº 79/)).toBeNull();
  const hoje = screen.getByRole('article', { name: 'Encomenda nº 77' });
  expect(within(hoje).getByText('15:00')).toBeInTheDocument();
  expect(within(hoje).getByText(/1× Torta de Limão · Inteira/)).toBeInTheDocument();
  expect(within(hoje).getByText(/Ana Paula/)).toBeInTheDocument();
});

it('navega para o dia seguinte', async () => {
  const chamadas = apiFalsa({
    'GET /painel/producao': () => [200, { dia: '2026-11-03', encomendas: [] }],
    'GET /painel/producao?dia=2026-11-04': () => [200, { dia: '2026-11-04', encomendas: [] }],
    'GET /painel/alertas': () => [200, { amanha: '2026-11-04', encomendas: [] }],
  });
  render(<Producao token="t" />);
  expect(await screen.findByText('Nenhuma Encomenda para este dia.')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Amanhã' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Próximo dia' }));
  expect(await screen.findByRole('heading', { name: /4 de novembro/ })).toBeInTheDocument();
  expect(chamadas.some((c) => c.url.endsWith('/painel/producao?dia=2026-11-04'))).toBe(true);
});

it('produz para a Encomenda e desfaz (respostas 1 e 28)', async () => {
  const comItem = {
    ...ENCOMENDA,
    itens: [
      {
        variante_id: 'lc-g',
        nome: 'Torta de Limão · Inteira',
        quantidade: 2,
        separado: 1,
      },
    ],
  };
  const chamadas = apiFalsa({
    'GET /painel/producao': () => [200, { dia: '2026-11-03', encomendas: [comItem] }],
    'GET /painel/producao?dia=2026-11-03': () => [
      200,
      { dia: '2026-11-03', encomendas: [comItem] },
    ],
    'GET /painel/alertas': () => [200, { amanha: '2026-11-04', encomendas: [] }],
    'POST /painel/pedidos/e1/separacao': () => [200, { separado: { 'lc-g': 2 } }],
  });
  render(<Producao token="t" />);
  const item = await screen.findByRole('listitem', { name: 'Torta de Limão · Inteira' });
  expect(within(item).getByText(/1 de 2 separados/)).toBeInTheDocument();
  await userEvent.click(within(item).getByRole('button', { name: 'Produzi 1' }));
  expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({
    variante_id: 'lc-g',
    quantidade: 1,
    origem: 'producao',
  });
  await userEvent.click(within(item).getByRole('button', { name: 'Desfazer 1' }));
  expect(chamadas.filter((c) => c.metodo === 'POST').at(-1)?.corpo).toMatchObject({
    origem: 'liberar',
  });
});
