import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Loja } from '../src/loja/Loja';
import { apiFalsa } from './estoque-fixtures';
import { CARDAPIO } from './loja-fixtures';

vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: { auth: { signOut: vi.fn() } },
}));

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, '', '/');
});
afterEach(() => vi.unstubAllGlobals());

const PEDIDO = {
  id: 'p1',
  numero: 42,
  estado: 'aguardando_pagamento',
  tipo_entrega: 'pronta_entrega',
  recebimento: 'retirada',
  subtotal_centavos: 3980,
  desconto_centavos: 0,
  taxa_entrega_centavos: 0,
  total_centavos: 3980,
  entrega_a_partir_de: '2026-11-02T18:10:00+00:00',
  expira_em: '2026-11-02T18:30:00+00:00',
  pix: { copia_e_cola: '00020126PIXDE39,80' },
  whatsapp_url: 'https://wa.me/5511988887777?text=x',
};

async function adicionarDoce(vezes = 1) {
  await userEvent.click(await screen.findByRole('button', { name: /Bolo de Pote Red Velvet/ }));
  const folha = screen.getByRole('dialog');
  for (let i = 1; i < vezes; i++)
    await userEvent.click(within(folha).getByRole('button', { name: 'Mais um' }));
  await userEvent.click(within(folha).getByRole('button', { name: /Adicionar/ }));
}

it('mostra o cardápio por Categoria, com o que é Pronta entrega e o que é Encomenda', async () => {
  apiFalsa({ 'GET /loja/cardapio': () => [200, CARDAPIO] });
  render(<Loja />);
  expect(await screen.findByRole('heading', { name: 'Bolos de pote' })).toBeInTheDocument();
  expect(screen.getByText('Aberto até meia-noite')).toBeInTheDocument();
  const grande = screen.getByRole('button', { name: /Torta de Limão/ });
  expect(within(grande).getByText('Só por Encomenda')).toBeInTheDocument();
});

it('adiciona ao pedido e mostra o total na barra de baixo', async () => {
  apiFalsa({ 'GET /loja/cardapio': () => [200, CARDAPIO] });
  render(<Loja />);
  await adicionarDoce(2);
  expect(screen.getByRole('button', { name: /Ver pedido/ })).toHaveTextContent('R$ 39,80');
});

it('fecha um pedido de retirada e mostra o Pix', async () => {
  const chamadas = apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'POST /loja/pedidos': () => [201, PEDIDO],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
  render(<Loja />);
  await adicionarDoce(2);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.click(screen.getByRole('radio', { name: /Retirar na loja/ }));
  await userEvent.type(screen.getByLabelText('Seu nome'), 'Ana Paula');
  await userEvent.type(screen.getByLabelText('WhatsApp'), '11999991234');
  await userEvent.click(screen.getByRole('button', { name: /Fazer pedido/ }));
  expect(chamadas.find((c) => c.url.endsWith('/loja/pedidos'))?.corpo).toEqual({
    cliente: { nome: 'Ana Paula', telefone: '11999991234' },
    recebimento: 'retirada',
    endereco: null,
    usar_endereco_anterior: false,
    itens: [{ variante_id: 'doce-ind', quantidade: 2 }],
    tipo_entrega: 'pronta_entrega',
    entrega_em: null,
    observacao: null,
  });
  expect(await screen.findByRole('heading', { name: 'Pedido nº 42' })).toBeInTheDocument();
  expect(screen.getByText('00020126PIXDE39,80')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Enviar no WhatsApp/ })).toHaveAttribute(
    'href',
    PEDIDO.whatsapp_url,
  );
});

it('reconhece quem já pediu e oferece o endereço mascarado', async () => {
  const chamadas = apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [
      200,
      { endereco_mascarado: 'R. Eu••• Lara, 2••, Jardim Azul', taxa_entrega_centavos: 1400 },
    ],
    'POST /loja/pedidos': () => [201, { ...PEDIDO, recebimento: 'entrega' }],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
  render(<Loja />);
  await adicionarDoce();
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.type(screen.getByLabelText('Seu nome'), 'Ana');
  await userEvent.type(screen.getByLabelText('WhatsApp'), '11999991234');
  await userEvent.tab();
  expect(await screen.findByText('R. Eu••• Lara, 2••, Jardim Azul')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('radio', { name: /Entregar no mesmo endereço/ }));
  // a taxa aparece antes de pagar, sem calcular de novo
  expect(screen.getByText('R$ 14,00')).toBeInTheDocument();
  expect(screen.queryByText(/calcule acima/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Fazer pedido/ }));
  expect(chamadas.find((c) => c.url.endsWith('/loja/pedidos'))?.corpo).toMatchObject({
    recebimento: 'entrega',
    endereco: null,
    usar_endereco_anterior: true,
  });
});

it('CEP não encontrado ou serviço fora do ar oferece combinar pelo WhatsApp', async () => {
  apiFalsa({
    'GET /loja/cardapio': () => [
      200,
      { ...CARDAPIO, whatsapp_url: 'https://wa.me/5511912345678?text=Ol%C3%A1' },
    ],
    'GET /loja/cep/99999999': () => [
      422,
      { erro: 'cep_nao_encontrado', mensagem: 'Não achamos esse CEP. Confira os números.' },
    ],
    'GET /loja/cep/90000002': () => [
      503,
      { erro: 'mapa_indisponivel', mensagem: 'O CEP não respondeu. Tente de novo.' },
    ],
  });
  render(<Loja />);
  await adicionarDoce(1);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.type(screen.getByLabelText('CEP'), '99999999');
  expect(await screen.findByText(/Não achamos esse CEP/)).toBeInTheDocument();
  const link = screen.getByRole('link', { name: /Combinar pelo WhatsApp/ });
  const texto = new URL(link.getAttribute('href')!).searchParams.get('text')!;
  expect(link.getAttribute('href')).toMatch(/^https:\/\/wa\.me\/5511912345678/);
  expect(texto).toContain('99999-999');
  expect(texto).toContain('Bolo de Pote Red Velvet');
  await userEvent.clear(screen.getByLabelText('CEP'));
  await userEvent.type(screen.getByLabelText('CEP'), '90000002');
  expect(await screen.findByText(/O CEP não respondeu/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Combinar pelo WhatsApp/ })).toBeInTheDocument();
});

it('mostra a recusa da API com a saída que ela oferece', async () => {
  apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'GET /loja/cep/13010100': () => [
      200,
      {
        cep: '13010100',
        logradouro: 'Av. Longe',
        bairro: 'Centro',
        cidade: 'Campinas',
        uf: 'SP',
      },
    ],
    'POST /loja/entrega/cotacao': () => [
      422,
      {
        erro: 'sob_consulta',
        mensagem: 'Para essa distância a entrega é combinada pelo WhatsApp.',
        whatsapp_url: 'https://wa.me/55?text=oi',
      },
    ],
  });
  render(<Loja />);
  await adicionarDoce();
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.type(screen.getByLabelText('CEP'), '13010100');
  await userEvent.type(await screen.findByLabelText('Número'), '1');
  await userEvent.click(screen.getByRole('button', { name: 'Calcular entrega' }));
  expect(await screen.findByText(/combinada pelo WhatsApp/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Combinar pelo WhatsApp/ })).toHaveAttribute(
    'href',
    'https://wa.me/55?text=oi',
  );
});

it('avisa quanto falta para o Pedido mínimo antes de enviar', async () => {
  apiFalsa({ 'GET /loja/cardapio': () => [200, CARDAPIO] });
  render(<Loja />);
  await userEvent.click(await screen.findByRole('button', { name: /Palha Italiana/ }));
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /Adicionar/ }),
  );
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  expect(screen.getByText('Faltam R$ 3,10 para o pedido mínimo de R$ 8,00.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Fazer pedido/ })).toBeDisabled();
});

async function agendarDoce(chamadas: { url: string; corpo?: unknown }[], indice: number) {
  render(<Loja />);
  await adicionarDoce(1);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.click(screen.getByRole('radio', { name: /Retirar na loja/ }));
  await userEvent.type(screen.getByLabelText('Seu nome'), 'Ana Paula');
  await userEvent.type(screen.getByLabelText('WhatsApp'), '11999991234');
  expect(screen.getByRole('radio', { name: /Agora/ })).toBeChecked();
  await userEvent.click(screen.getByRole('radio', { name: 'Agendar dia e hora' }));
  const quando = screen.getByLabelText('Escolha quando receber');
  expect(screen.getByRole('button', { name: /Fazer pedido/ })).toBeDisabled();
  const opcoes = within(quando).getAllByRole('option');
  await userEvent.selectOptions(quando, opcoes[indice]);
  await userEvent.click(screen.getByRole('button', { name: /Fazer pedido/ }));
  return {
    opcoes: opcoes.map((o) => (o as HTMLOptionElement).value),
    corpo: chamadas.find((c) => c.url.endsWith('/loja/pedidos'))?.corpo as {
      tipo_entrega: string;
      entrega_em: string;
    },
  };
}

function apiDoAgendamento() {
  return apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'POST /loja/pedidos': () => [201, PEDIDO],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
}

it('com pronta entrega, agenda hoje a partir de agora + Tempo de preparo', async () => {
  const { opcoes, corpo } = await agendarDoce(apiDoAgendamento(), 2);
  // hoje 23h00 e 23h30 (Pronta entrega agendada), depois amanhã como Encomenda
  expect(opcoes.slice(1, 4)).toEqual([
    new Date('2026-11-02T23:00:00-03:00').toISOString(),
    new Date('2026-11-02T23:30:00-03:00').toISOString(),
    new Date('2026-11-03T12:00:00-03:00').toISOString(),
  ]);
  expect(corpo.tipo_entrega).toBe('pronta_entrega');
  expect(corpo.entrega_em).toBe(new Date('2026-11-02T23:30:00-03:00').toISOString());
});

it('com pronta entrega, horário de outro dia segue como Encomenda', async () => {
  const { corpo } = await agendarDoce(apiDoAgendamento(), 3);
  expect(corpo.tipo_entrega).toBe('encomenda');
  expect(corpo.entrega_em).toBe(new Date('2026-11-03T12:00:00-03:00').toISOString());
});

it('loja fechada com pronta entrega: agenda hoje a partir da abertura', async () => {
  const fechada = {
    ...CARDAPIO,
    loja_aberta: false,
    abre_as_hora: '08:00',
    primeiro_agendamento: '2026-11-02T08:30:00-03:00',
  };
  const chamadas = apiFalsa({
    'GET /loja/cardapio': () => [200, fechada],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'POST /loja/pedidos': () => [201, PEDIDO],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
  render(<Loja />);
  await adicionarDoce(1);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.click(screen.getByRole('radio', { name: /Retirar na loja/ }));
  await userEvent.type(screen.getByLabelText('Seu nome'), 'Ana Paula');
  await userEvent.type(screen.getByLabelText('WhatsApp'), '11999991234');
  expect(screen.queryByRole('radio', { name: /Agora/ })).not.toBeInTheDocument();
  const quando = screen.getByLabelText('Escolha quando receber');
  const opcoes = within(quando).getAllByRole('option');
  expect((opcoes[1] as HTMLOptionElement).value).toBe(
    new Date('2026-11-02T08:30:00-03:00').toISOString(),
  );
  await userEvent.selectOptions(quando, opcoes[1]);
  await userEvent.click(screen.getByRole('button', { name: /Fazer pedido/ }));
  const corpo = chamadas.find((c) => c.url.endsWith('/loja/pedidos'))?.corpo as {
    tipo_entrega: string;
  };
  expect(corpo.tipo_entrega).toBe('pronta_entrega');
});

it('botão para falar com a loja no WhatsApp, no cardápio e no carrinho', async () => {
  const url = 'https://wa.me/5511912345678?text=Ol%C3%A1';
  apiFalsa({ 'GET /loja/cardapio': () => [200, { ...CARDAPIO, whatsapp_url: url }] });
  render(<Loja />);
  const botao = await screen.findByRole('link', { name: /Falar com a loja no WhatsApp/ });
  expect(botao).toHaveAttribute('href', url);
  expect(botao).toHaveAttribute('target', '_blank');
  await adicionarDoce(1);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  expect(screen.getByRole('link', { name: /Falar com a loja no WhatsApp/ })).toBeInTheDocument();
});

it('sem WhatsApp cadastrado, não mostra o botão', async () => {
  apiFalsa({ 'GET /loja/cardapio': () => [200, { ...CARDAPIO, whatsapp_url: null }] });
  render(<Loja />);
  await screen.findByRole('button', { name: /Bolo de Pote Red Velvet/ });
  expect(screen.queryByRole('link', { name: /WhatsApp/ })).not.toBeInTheDocument();
});

it('CEP mostra a rua antes do número, e o pedido leva a observação', async () => {
  const chamadas = apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'POST /loja/cliente/reconhecer': () => [200, {}],
    'GET /loja/cep/12345678': () => [
      200,
      {
        cep: '12345678',
        logradouro: 'R. das Acácias',
        bairro: 'Jardim Azul',
        cidade: 'Campinas',
        uf: 'SP',
      },
    ],
    'POST /loja/entrega/cotacao': () => [
      200,
      {
        taxa_entrega_centavos: 1400,
        endereco: { logradouro: 'R. das Acácias', numero: '220', bairro: 'Jardim Azul' },
      },
    ],
    'POST /loja/pedidos': () => [201, { ...PEDIDO, recebimento: 'entrega' }],
    'GET /loja/pedidos/p1': () => [200, PEDIDO],
  });
  render(<Loja />);
  await adicionarDoce(1);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.type(screen.getByLabelText('Seu nome'), 'Ana Paula');
  await userEvent.type(screen.getByLabelText('WhatsApp'), '11999991234');
  expect(screen.queryByLabelText('Número')).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText('CEP'), '12345-678');
  expect(await screen.findByText('R. das Acácias')).toBeInTheDocument();
  expect(screen.getByText('Jardim Azul, Campinas')).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText('Número'), '220');
  await userEvent.type(screen.getByLabelText(/Complemento/), 'apto 3');
  await userEvent.click(screen.getByRole('button', { name: 'Calcular entrega' }));
  await screen.findByText(/entrega R\$ 14,00/);
  await userEvent.type(
    screen.getByLabelText(/Observação/),
    'Presente para Maria, entregar na recepção do hospital',
  );
  await userEvent.click(screen.getByRole('button', { name: /Fazer pedido/ }));
  expect(chamadas.find((c) => c.url.endsWith('/loja/pedidos'))?.corpo).toMatchObject({
    endereco: { cep: '12345-678', numero: '220', complemento: 'apto 3' },
    observacao: 'Presente para Maria, entregar na recepção do hospital',
  });
});

it('CEP que não existe avisa e não pede o número', async () => {
  apiFalsa({
    'GET /loja/cardapio': () => [200, CARDAPIO],
    'GET /loja/cep/99999999': () => [
      422,
      { erro: 'cep_nao_encontrado', mensagem: 'Não achamos esse CEP. Confira os números.' },
    ],
  });
  render(<Loja />);
  await adicionarDoce(1);
  await userEvent.click(screen.getByRole('button', { name: /Ver pedido/ }));
  await userEvent.type(screen.getByLabelText('CEP'), '99999999');
  expect(await screen.findByText(/Não achamos esse CEP/)).toBeInTheDocument();
  expect(screen.queryByLabelText('Número')).not.toBeInTheDocument();
});
