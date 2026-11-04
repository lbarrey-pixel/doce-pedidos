import { render } from '@testing-library/react';
import { App } from '../src/App';
import { apiFalsa } from './estoque-fixtures';
import { CARDAPIO } from './loja-fixtures';

vi.mock('../src/comum/supabase', () => ({
  chegouParaCriarSenha: false,
  supabase: {
    auth: {
      getSession: () => Promise.resolve({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
      signOut: vi.fn(),
    },
  },
}));

afterEach(() => vi.unstubAllGlobals());

it('a aba da loja se chama Doce Ateliê, e a do painel, Painel da Doce Ateliê', async () => {
  apiFalsa({ 'GET /loja/cardapio': () => [200, CARDAPIO] });
  window.history.replaceState(null, '', '/');
  const { unmount } = render(<App />);
  expect(document.title).toBe('Doce Ateliê');
  unmount();
  window.history.replaceState(null, '', '/painel/entrar');
  render(<App />);
  expect(document.title).toBe('Painel da Doce Ateliê');
});
