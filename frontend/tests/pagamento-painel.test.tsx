import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { bpsDePercentual, Configuracao, percentualDeBps } from '../src/painel/Configuracao';
import { LinkDaVenda } from '../src/painel/LinkDaVenda';
import { destino } from '../src/painel/Painel';
import { Pedidos } from '../src/painel/Pedidos';
import { PendenciasPagamento } from '../src/painel/PendenciasPagamento';
import { Resumos } from '../src/painel/Resumos';
import { Vendas } from '../src/painel/Vendas';
import { ROTAS } from '../src/comum/rotas';
import { apiFalsa, ESTOQUE } from './estoque-fixtures';

vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: { auth: { signOut: vi.fn() } },
}));

afterEach(() => vi.unstubAllGlobals());

const BASE = {
  canal: 'app',
  recebimento: 'entrega',
  tipo_entrega: 'pronta_entrega',
  cliente: { nome: 'Ana Paula', telefone: '11900000001' },
  endereco: { logradouro: 'R. das Acácias', numero: '220', bairro: 'Jardim Azul' },
  itens: [{ nome: 'Bolo de Pote Red Velvet · Individual', quantidade: 2 }],
  total_centavos: 5380,
  diferenca_pagamento_centavos: 0,
  criado_em: '2026-11-02T18:00:00+00:00',
  expira_em: '2026-11-02T18:30:00+00:00',
  entrega_a_partir_de: '2026-11-02T18:40:00+00:00',
  forma_pagamento: 'pix_manual',
};
const cartao = (extra = {}) => ({
  ...BASE,
  id: 'a',
  numero: 42,
  estado: 'pago',
  forma_pagamento: 'cartao',
  parcelas: 3,
  valor_pago_centavos: 5660,
  ...extra,
});
const lista = (...pedidos: object[]) => ({
  'GET /painel/pedidos': (): [number, unknown] => [200, { pedidos }],
});
const semPendencias = {
  'GET /painel/pagamentos/pendencias': (): [number, unknown] => [200, { pendencias: [] }],
};

describe('Pedidos com pagamento online', () => {
  it('mostra forma, parcelas, valor do pedido e valor pago pelo cliente', async () => {
    apiFalsa({ ...lista(cartao()), ...semPendencias });
    render(<Pedidos token="t" />);
    const p = await screen.findByRole('article', { name: /Pedido nº 42/ });
    expect(within(p).getByText('Pagamento: Cartão em 3x')).toBeInTheDocument();
    expect(
      within(p).getByText(/Valor do pedido R\$ 53,80 · pago pelo cliente R\$ 56,60/),
    ).toBeInTheDocument();
  });

  it('Pix pelo gateway mostra a forma e Pix manual não mostra valor pago', async () => {
    apiFalsa({
      ...lista(cartao({ forma_pagamento: 'pix', parcelas: 1, valor_pago_centavos: 5380 }), {
        ...BASE,
        id: 'b',
        numero: 41,
        estado: 'pago',
      }),
      ...semPendencias,
    });
    render(<Pedidos token="t" />);
    const pix = await screen.findByRole('article', { name: /Pedido nº 42/ });
    expect(within(pix).getByText('Pagamento: Pix')).toBeInTheDocument();
    const manual = screen.getByRole('article', { name: /Pedido nº 41/ });
    expect(within(manual).getByText('Pagamento: Pix manual')).toBeInTheDocument();
    expect(within(manual).queryByText(/pago pelo cliente/)).not.toBeInTheDocument();
  });

  it('destaca o pedido pago depois de expirar', async () => {
    apiFalsa({ ...lista(cartao({ pago_apos_expirar: true })), ...semPendencias });
    render(<Pedidos token="t" />);
    expect(await screen.findByText('Pago depois de expirar')).toBeInTheDocument();
  });

  it('pedido com link não oferece "Recebi", só Conferir pagamento', async () => {
    apiFalsa({
      ...lista({
        ...BASE,
        id: 'a',
        numero: 42,
        estado: 'aguardando_pagamento',
        paga_pelo_link: true,
      }),
      ...semPendencias,
    });
    render(<Pedidos token="t" />);
    const p = await screen.findByRole('article', { name: /Pedido nº 42/ });
    expect(within(p).queryByRole('button', { name: /Recebi/ })).not.toBeInTheDocument();
    expect(within(p).getByRole('button', { name: 'Conferir pagamento' })).toBeInTheDocument();
  });

  it.each([
    ['confirmado', /Pagamento confirmado/],
    ['nao_confirmado', /ainda não confirmou/],
    ['valor_recusado', /valor diferente do pedido/],
    ['a_estornar', /para estorno/],
    ['a_decidir', /sem estoque/],
  ])('Conferir pagamento mostra o resultado %s', async (resultado, texto) => {
    const chamadas = apiFalsa({
      ...lista({
        ...BASE,
        id: 'a',
        numero: 42,
        estado: 'aguardando_pagamento',
        paga_pelo_link: true,
      }),
      ...semPendencias,
      'POST /painel/pedidos/a/conferir-pagamento': () => [200, { estado: 'pago', resultado }],
    });
    render(<Pedidos token="t" />);
    const p = await screen.findByRole('article', { name: /Pedido nº 42/ });
    await userEvent.click(within(p).getByRole('button', { name: 'Conferir pagamento' }));
    expect(await within(p).findByRole('status')).toHaveTextContent(texto);
    expect(chamadas.some((c) => c.url.endsWith('/conferir-pagamento'))).toBe(true);
  });

  it('Conferir pagamento sem aviso mostra a orientação do servidor', async () => {
    apiFalsa({
      ...lista({
        ...BASE,
        id: 'a',
        numero: 42,
        estado: 'aguardando_pagamento',
        paga_pelo_link: true,
      }),
      ...semPendencias,
      'POST /painel/pedidos/a/conferir-pagamento': () => [
        409,
        { erro: 'sem_aviso_gateway', mensagem: 'Sem aviso do gateway para este pedido.' },
      ],
    });
    render(<Pedidos token="t" />);
    const p = await screen.findByRole('article', { name: /Pedido nº 42/ });
    await userEvent.click(within(p).getByRole('button', { name: 'Conferir pagamento' }));
    expect(await within(p).findByRole('alert')).toHaveTextContent('Sem aviso do gateway');
  });

  it('cancelar pedido pago pelo gateway mostra o aviso de estorno e não registra devolução', async () => {
    const chamadas = apiFalsa({
      ...lista(cartao({ forma_pagamento: 'pix', parcelas: 1, valor_pago_centavos: 5380 })),
      ...semPendencias,
      'POST /painel/pedidos/a/estado': () => [
        200,
        {
          estado: 'cancelado',
          estorno: {
            valor_centavos: 5380,
            mensagem: 'Faça o estorno de R$ 53,80 no painel do gateway.',
          },
        },
      ],
    });
    render(<Pedidos token="t" />);
    const p = await screen.findByRole('article', { name: /Pedido nº 42/ });
    await userEvent.click(within(p).getByRole('button', { name: 'Cancelar pedido' }));
    expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({ estado: 'cancelado' });
    const aviso = await screen.findByText(/Faça o estorno de R\$ 53,80/);
    expect(aviso).toHaveTextContent('Pedido nº 42 cancelado.');
    await userEvent.click(screen.getByRole('button', { name: 'Entendi' }));
    expect(screen.queryByText(/Faça o estorno/)).not.toBeInTheDocument();
  });

  it('cancelar pedido pago no Pix manual registra a devolução', async () => {
    const chamadas = apiFalsa({
      ...lista({ ...BASE, id: 'a', numero: 42, estado: 'pago' }),
      ...semPendencias,
      'POST /painel/pedidos/a/estado': () => [200, { estado: 'cancelado' }],
    });
    render(<Pedidos token="t" />);
    const p = await screen.findByRole('article', { name: /Pedido nº 42/ });
    await userEvent.click(within(p).getByRole('button', { name: /registrar devolução do Pix/ }));
    expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({
      estado: 'cancelado',
      devolucao_centavos: 5380,
    });
  });

  it('venda lançada no painel mostra o estado do link e pode ser cancelada', async () => {
    const chamadas = apiFalsa({
      ...lista({
        ...BASE,
        canal: 'balcao',
        id: 'v',
        numero: 50,
        estado: 'pago',
        forma_pagamento: 'externo',
        pagamento_link: 'aguardando',
      }),
      ...semPendencias,
      'POST /painel/pedidos/v/estado': () => [200, { estado: 'cancelado' }],
    });
    render(<Pedidos token="t" />);
    const v = await screen.findByRole('article', { name: /Pedido nº 50/ });
    expect(within(v).getByText('Aguardando pagamento do link')).toBeInTheDocument();
    await userEvent.click(within(v).getByRole('button', { name: 'Cancelar venda' }));
    expect(chamadas.find((c) => c.metodo === 'POST')?.corpo).toEqual({ estado: 'cancelado' });
  });

  it('link expirado fica destacado', async () => {
    apiFalsa({
      ...lista({
        ...BASE,
        canal: 'balcao',
        id: 'v',
        numero: 50,
        estado: 'cancelado',
        pagamento_link: 'expirado',
      }),
      ...semPendencias,
    });
    render(<Pedidos token="t" />);
    expect(await screen.findByText('Link expirado sem pagamento')).toHaveClass('pedido__alerta');
  });
});

describe('Pagamentos para conferir', () => {
  const PENDENCIAS = [
    {
      id: 7,
      resultado: 'valor_recusado',
      numero: 42,
      valor_cobrado_centavos: 5000,
      valor_pago_centavos: 5380,
      criado_em: '2026-11-02T18:00:00+00:00',
    },
    {
      id: 8,
      resultado: 'a_estornar',
      numero: null,
      valor_cobrado_centavos: 5380,
      valor_pago_centavos: 5380,
      criado_em: '2026-11-02T18:05:00+00:00',
    },
  ];

  it('lista as pendências e marca como resolvida', async () => {
    let pendencias = PENDENCIAS;
    const chamadas = apiFalsa({
      'GET /painel/pagamentos/pendencias': () => [200, { pendencias }],
      'POST /painel/pagamentos/pendencias/7/resolver': () => {
        pendencias = PENDENCIAS.slice(1);
        return [200, { resolvido: true }];
      },
    });
    render(<PendenciasPagamento token="t" versao={0} />);
    const recusado = await screen.findByRole('listitem', { name: 'Pedido nº 42' });
    expect(recusado).toHaveTextContent('Valor recusado');
    expect(recusado).toHaveTextContent('pago R$ 53,80 · cobrado R$ 50,00');
    expect(screen.getByRole('listitem', { name: 'Pagamento sem pedido' })).toHaveTextContent(
      'A estornar',
    );
    await userEvent.click(within(recusado).getByRole('button', { name: 'Resolvido' }));
    await waitFor(() =>
      expect(screen.queryByRole('listitem', { name: 'Pedido nº 42' })).not.toBeInTheDocument(),
    );
    expect(chamadas.some((c) => c.url.endsWith('/7/resolver') && c.metodo === 'POST')).toBe(true);
  });

  it('sem pendência a seção não aparece', async () => {
    apiFalsa(semPendencias);
    render(<PendenciasPagamento token="t" versao={0} />);
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument());
  });
});

describe('Link da venda', () => {
  it('gera o link, mostra a URL e o botão do WhatsApp', async () => {
    apiFalsa({
      'POST /painel/vendas/v1/link': () => [
        200,
        { url: 'https://pagar.doceatelie.example/v1', whatsapp_url: 'https://wa.me/?text=oi' },
      ],
      'GET /painel/pedidos': () => [200, { pedidos: [{ id: 'v1', pagamento_link: 'aguardando' }] }],
    });
    render(<LinkDaVenda token="t" vendaId="v1" numero={50} />);
    await userEvent.click(screen.getByRole('button', { name: 'Gerar link' }));
    expect(
      await screen.findByDisplayValue('https://pagar.doceatelie.example/v1'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Mandar pelo WhatsApp' })).toHaveAttribute(
      'href',
      'https://wa.me/?text=oi',
    );
    expect(await screen.findByText('Aguardando pagamento do link')).toBeInTheDocument();
  });

  it('mostra o erro quando o gateway está fora do ar', async () => {
    apiFalsa({
      'POST /painel/vendas/v1/link': () => [
        503,
        { erro: 'gateway_indisponivel', mensagem: 'Não deu para gerar o link agora.' },
      ],
    });
    render(<LinkDaVenda token="t" vendaId="v1" numero={50} />);
    await userEvent.click(screen.getByRole('button', { name: 'Gerar link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Não deu para gerar o link agora.');
    expect(screen.getByRole('button', { name: 'Gerar link' })).toBeEnabled();
  });
});

describe('Vendas', () => {
  it('lança a venda com os itens escolhidos e oferece o link', async () => {
    const chamadas = apiFalsa({
      'GET /painel/estoque': () => [200, ESTOQUE],
      'POST /painel/vendas': () => [200, { id: 'v1', numero: 50, total_centavos: 3980 }],
    });
    render(<Vendas token="t" />);
    await userEvent.click(await screen.findByRole('button', { name: /Bolo de Pote Red Velvet/ }));
    expect(screen.getByRole('button', { name: /Lançar venda · R\$ 19,90/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Lançar venda/ }));
    expect(chamadas.find((c) => c.url.endsWith('/painel/vendas'))?.corpo).toEqual({
      itens: [{ variante_id: 'doce-ind', quantidade: 1 }],
    });
    expect(
      await screen.findByRole('region', { name: /Link de pagamento da venda nº 50/ }),
    ).toBeInTheDocument();
  });

  it('item sem saldo na pronta entrega não pode ser escolhido', async () => {
    const sem = {
      variantes: [{ ...ESTOQUE.variantes[1], saldo: { ...ESTOQUE.variantes[1].saldo, pronta: 0 } }],
    };
    apiFalsa({ 'GET /painel/estoque': () => [200, sem] });
    render(<Vendas token="t" />);
    expect(await screen.findByRole('button', { name: /Bolo de Pote Red Velvet/ })).toBeDisabled();
  });
});

describe('Resumos por forma', () => {
  const RESUMO = {
    de: '2026-11-02',
    ate: '2026-11-08',
    por_forma: {
      pix: { pedidos: 1, valor_centavos: 5380, taxa_estimada_centavos: 0 },
      cartao: { pedidos: 2, valor_centavos: 10760, taxa_estimada_centavos: 452 },
      pix_manual: { pedidos: 0, valor_centavos: 0, taxa_estimada_centavos: 0 },
    },
  };

  it('mostra valor e taxa estimada de cada forma com pedidos', async () => {
    apiFalsa({ 'GET /painel/resumos': () => [200, RESUMO] });
    render(<Resumos token="t" />);
    const cartao = await screen.findByRole('article', { name: 'Cartão' });
    expect(cartao).toHaveTextContent('2 pedidos · R$ 107,60');
    expect(cartao).toHaveTextContent('Taxa estimada R$ 4,52');
    expect(screen.getByRole('article', { name: 'Pix' })).toHaveTextContent('1 pedido');
    expect(screen.queryByRole('article', { name: 'Pix manual' })).not.toBeInTheDocument();
    expect(screen.getByText(/Taxa estimada do gateway no período: R\$ 4,52/)).toBeInTheDocument();
    expect(screen.getByText(/De 02\/11\/2026 a 08\/11\/2026/)).toBeInTheDocument();
  });

  it('período sem pagamento avisa', async () => {
    const zero = { pedidos: 0, valor_centavos: 0, taxa_estimada_centavos: 0 };
    apiFalsa({
      'GET /painel/resumos': () => [
        200,
        { ...RESUMO, por_forma: { pix: zero, cartao: zero, pix_manual: zero } },
      ],
    });
    render(<Resumos token="t" />);
    expect(await screen.findByText('Nenhum pagamento no período.')).toBeInTheDocument();
  });
});

describe('Configuração das tarifas', () => {
  it('converte pontos-base em percentual e de volta', () => {
    expect(percentualDeBps(420)).toBe('4,20');
    expect(percentualDeBps(0)).toBe('0,00');
    expect(bpsDePercentual('4,20')).toBe(420);
    expect(bpsDePercentual('5.49')).toBe(549);
    expect(bpsDePercentual('4')).toBe(400);
    expect(bpsDePercentual('100')).toBe(10_000);
    for (const ruim of ['', 'abc', '100,01', '4,205', '-1'])
      expect(bpsDePercentual(ruim)).toBeNull();
  });

  it('carrega as tarifas e salva em pontos-base', async () => {
    const chamadas = apiFalsa({
      'GET /painel/configuracao': () => [200, { tarifa_cartao_bps: 420, tarifa_pix_bps: 0 }],
      'PUT /painel/configuracao': (c) => [200, c],
    });
    render(<Configuracao token="t" />);
    const cartao = await screen.findByLabelText('Tarifa do cartão (%)');
    await waitFor(() => expect(cartao).toHaveValue('4,20'));
    await userEvent.clear(cartao);
    await userEvent.type(cartao, '5,49');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar tarifas' }));
    expect(await screen.findByText('Tarifas salvas.')).toBeInTheDocument();
    expect(chamadas.find((c) => c.metodo === 'PUT')?.corpo).toEqual({
      tarifa_cartao_bps: 549,
      tarifa_pix_bps: 0,
    });
  });

  it('valor inválido bloqueia o botão', async () => {
    apiFalsa({
      'GET /painel/configuracao': () => [200, { tarifa_cartao_bps: 420, tarifa_pix_bps: 0 }],
    });
    render(<Configuracao token="t" />);
    const pix = await screen.findByLabelText('Tarifa do Pix (%)');
    await userEvent.type(pix, 'x');
    expect(screen.getByRole('button', { name: 'Salvar tarifas' })).toBeDisabled();
    expect(pix).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('rotas do painel', () => {
  it('as telas novas exigem login', () => {
    for (const rota of [ROTAS.vendas, ROTAS.resumos, ROTAS.configuracao]) {
      expect(destino(rota, false)).toBe(ROTAS.entrar);
      expect(destino(rota, true)).toBe(rota);
    }
  });
});
