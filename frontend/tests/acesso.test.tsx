import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Acesso } from '../src/painel/Acesso';
import { destino } from '../src/painel/Painel';
import { mensagemDeErroDeLogin } from '../src/comum/mensagens';
import { ROTAS } from '../src/comum/rotas';

const updateUser = vi.fn();
const signOut = vi.fn();
vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: {
    auth: {
      signOut: (...a: unknown[]) => signOut(...a),
      updateUser: (...a: unknown[]) => updateUser(...a),
    },
  },
}));

describe('para onde cada caminho leva', () => {
  it('sem login, tudo leva a entrar', () => {
    expect(destino('/painel', false)).toBe(ROTAS.entrar);
    expect(destino('/qualquer', false)).toBe(ROTAS.entrar);
    expect(destino(ROTAS.definirSenha, false)).toBe(ROTAS.entrar);
    expect(destino(ROTAS.estoque, false)).toBe(ROTAS.entrar);
  });
  it('com login, abre os pedidos, ou a criar senha quando veio do link', () => {
    expect(destino(ROTAS.entrar, true)).toBe(ROTAS.pedidos);
    expect(destino('/', true)).toBe(ROTAS.pedidos);
    expect(destino(ROTAS.definirSenha, true)).toBe(ROTAS.definirSenha);
    expect(destino(ROTAS.producao, true)).toBe(ROTAS.producao);
  });
});

describe('mensagens de erro do login', () => {
  it.each([
    [{ message: 'Invalid login credentials' }, 'E-mail ou senha não conferem.'],
    [
      { message: 'Email not confirmed' },
      'Confirme o e-mail pelo link que enviamos antes de entrar.',
    ],
    [
      { message: 'x', status: 429 },
      'Muitas tentativas seguidas. Espere um minuto e tente de novo.',
    ],
    [{ message: 'Failed to fetch' }, 'Sem conexão. Confira a internet e tente de novo.'],
    [{ message: 'algo novo' }, 'Não deu para concluir agora. Tente de novo em instantes.'],
  ])('%o', (erro, texto) => {
    expect(mensagemDeErroDeLogin(erro)).toBe(texto);
  });
});

describe('porta do painel', () => {
  afterEach(() => vi.unstubAllGlobals());

  function responder(status: number, corpo: unknown) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(corpo), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
  }

  it('operador ativo vê a tela pedida', async () => {
    responder(200, { id: 'x', nome: 'Marina Souza' });
    render(
      <Acesso token="t">
        <p>conteúdo do painel</p>
      </Acesso>,
    );
    expect(await screen.findByText('conteúdo do painel')).toBeInTheDocument();
  });

  it('Sair desconecta só este aparelho', async () => {
    // sair num celular não pode derrubar o painel aberto no computador
    responder(403, { erro: 'sem_acesso', mensagem: 'Sem acesso ao painel.' });
    render(<Acesso token="t">x</Acesso>);
    await userEvent.click(await screen.findByRole('button', { name: 'Sair' }));
    expect(signOut).toHaveBeenCalledWith({ scope: 'local' });
  });

  it('quem tem login mas não é operador vê que o acesso não foi liberado', async () => {
    responder(403, { erro: 'sem_acesso', mensagem: 'Sem acesso ao painel.' });
    render(<Acesso token="t">x</Acesso>);
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Seu acesso ainda não foi liberado' }),
      ).toBeInTheDocument(),
    );
  });

  it('com senha provisória, só abre a troca de senha e depois o painel', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const corpo =
        init?.method === 'POST'
          ? { trocar_senha: false }
          : { id: 'x', nome: 'Marina Souza', trocar_senha: true };
      expect(String(url)).toMatch(init?.method === 'POST' ? /senha-trocada$/ : /painel\/eu$/);
      return Promise.resolve(
        new Response(JSON.stringify(corpo), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    });
    vi.stubGlobal('fetch', fetchMock);
    updateUser.mockResolvedValue({ error: null });
    render(
      <Acesso token="t">
        <p>conteúdo do painel</p>
      </Acesso>,
    );
    expect(
      await screen.findByRole('heading', { name: 'Troque a senha provisória' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('conteúdo do painel')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/^Senha nova/), 'doce-da-marina');
    await userEvent.type(screen.getByLabelText(/^Repita a senha/), 'doce-da-marina');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar senha' }));
    expect(updateUser).toHaveBeenCalledWith({ password: 'doce-da-marina' });
    expect(await screen.findByText('conteúdo do painel')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
