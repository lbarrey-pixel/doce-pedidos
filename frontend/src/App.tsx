import { lazy, Suspense, useEffect } from 'react';
import { useCaminho } from './comum/rotas';
import { Loja } from './loja/Loja';

// O painel (e o cliente do Supabase Auth) só baixa quem abre /painel: a loja fica mais leve
// no celular.
const Painel = lazy(() => import('./painel/Painel').then((m) => ({ default: m.Painel })));

export function App() {
  const caminho = useCaminho();
  const painel = caminho.startsWith('/painel');
  // Nome da aba: o cliente vê "Doce Ateliê"; o operador, o painel.
  useEffect(() => {
    document.title = painel ? 'Painel da Doce Ateliê' : 'Doce Ateliê';
  }, [painel]);
  return painel ? (
    <Suspense fallback={null}>
      <Painel caminho={caminho} />
    </Suspense>
  ) : (
    <Loja />
  );
}
