import { createClient } from '@supabase/supabase-js';

// A chave publicável vai no site por desenho; quem protege os dados é a API, que só aceita
// operador cadastrado em doce.operador. Sem as variáveis, o cliente aponta para um endereço
// local inerte e o painel usa VITE_DEV_TOKEN (ver README, "Painel sem Supabase").
const URL = import.meta.env.VITE_SUPABASE_URL ?? 'http://localhost:54321';
const CHAVE = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? 'chave-local-sem-supabase';

// Link de convite ou de nova senha chega com "type=invite" ou "type=recovery" no endereço.
// Lido antes de o cliente consumir o endereço, para mandar a pessoa criar a senha.
export const chegouParaCriarSenha = /type=(invite|recovery)/.test(window.location.hash);

export const supabase = createClient(URL, CHAVE, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
});
