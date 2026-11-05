import { useEffect, useState } from 'react';

export const ROTAS = {
  entrar: '/painel/entrar',
  definirSenha: '/painel/criar-senha',
  painel: '/painel',
  estoque: '/painel/estoque',
  pedidos: '/painel/pedidos',
  producao: '/painel/producao',
  vendas: '/painel/vendas',
  resumos: '/painel/resumos',
  configuracao: '/painel/configuracao',
} as const;

export function irPara(caminho: string, substituir = false) {
  if (substituir) window.history.replaceState(null, '', caminho);
  else window.history.pushState(null, '', caminho);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

// Leva o cliente à página de pagamento do gateway, na mesma aba.
export function abrirPagamento(url: string) {
  window.location.assign(url);
}

export function useCaminho(): string {
  const [caminho, setCaminho] = useState(window.location.pathname);
  useEffect(() => {
    const atualizar = () => setCaminho(window.location.pathname);
    window.addEventListener('popstate', atualizar);
    return () => window.removeEventListener('popstate', atualizar);
  }, []);
  return caminho;
}
