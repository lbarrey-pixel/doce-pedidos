import type { Session } from '@supabase/supabase-js';
import { useEffect, useState } from 'react';
import { irPara, ROTAS } from '../comum/rotas';
import { chegouParaCriarSenha, supabase } from '../comum/supabase';
import { Acesso } from './Acesso';
import { CriarSenha } from './CriarSenha';
import { Entrar } from './Entrar';
import { Estoque } from './Estoque';
import { Pedidos } from './Pedidos';
import { Producao } from './Producao';

// Desenvolvimento sem Supabase: um JWT gerado por `python -m scripts.token_dev`.
const TOKEN_DEV: string | undefined = import.meta.env.VITE_DEV_TOKEN;

const INTERNAS: string[] = [ROTAS.estoque, ROTAS.pedidos, ROTAS.producao];

// Para onde cada caminho leva, conforme haja login ou não.
export function destino(caminho: string, logado: boolean): string {
  if (caminho === ROTAS.definirSenha) return logado ? ROTAS.definirSenha : ROTAS.entrar;
  if (INTERNAS.includes(caminho)) return logado ? caminho : ROTAS.entrar;
  return logado ? ROTAS.pedidos : ROTAS.entrar;
}

export function Painel({ caminho }: { caminho: string }) {
  const [sessao, setSessao] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    if (TOKEN_DEV) return;
    if (chegouParaCriarSenha) irPara(ROTAS.definirSenha, true);
    supabase.auth.getSession().then(({ data }) => setSessao(data.session));
    const { data } = supabase.auth.onAuthStateChange((evento, s) => {
      setSessao(s);
      if (evento === 'PASSWORD_RECOVERY') irPara(ROTAS.definirSenha, true);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const token = TOKEN_DEV ?? sessao?.access_token;
  const logado = TOKEN_DEV ? true : sessao === undefined ? undefined : Boolean(sessao);
  const alvo = logado === undefined ? caminho : destino(caminho, logado);
  useEffect(() => {
    if (alvo !== caminho) irPara(alvo, true);
  }, [alvo, caminho]);

  if (logado === undefined) return null;
  if (alvo === ROTAS.definirSenha) return <CriarSenha />;
  if (alvo === ROTAS.entrar || !token) return <Entrar />;
  const telas: Record<string, JSX.Element> = {
    [ROTAS.estoque]: <Estoque token={token} />,
    [ROTAS.pedidos]: <Pedidos token={token} />,
    [ROTAS.producao]: <Producao token={token} />,
  };
  return <Acesso token={token}>{telas[alvo] ?? telas[ROTAS.pedidos]}</Acesso>;
}
