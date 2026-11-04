import { useCallback, useEffect, useState } from 'react';

// Carrinho do cliente: só neste aparelho (conveniência; a fonte é o Pedido no servidor).
const CHAVE = 'doce-carrinho';
export type Carrinho = Record<string, number>;

function ler(): Carrinho {
  try {
    const bruto = localStorage.getItem(CHAVE);
    const dados = bruto ? JSON.parse(bruto) : {};
    return typeof dados === 'object' && dados ? dados : {};
  } catch {
    return {};
  }
}

function gravar(c: Carrinho) {
  try {
    localStorage.setItem(CHAVE, JSON.stringify(c));
  } catch {
    // navegador sem armazenamento: o carrinho vive só nesta página
  }
}

export function useCarrinho() {
  const [itens, setItens] = useState<Carrinho>(ler);
  useEffect(() => gravar(itens), [itens]);
  const mudar = useCallback((id: string, quantidade: number) => {
    setItens((atual) => {
      const novo = { ...atual };
      if (quantidade <= 0) delete novo[id];
      else novo[id] = quantidade;
      return novo;
    });
  }, []);
  const somar = useCallback(
    (id: string, mais: number) => setItens((a) => ({ ...a, [id]: (a[id] ?? 0) + mais })),
    [],
  );
  const esvaziar = useCallback(() => setItens({}), []);
  return { itens, mudar, somar, esvaziar };
}

export function guardarPedido(id: string, dados: unknown) {
  try {
    localStorage.setItem(`doce-pedido-${id}`, JSON.stringify(dados));
  } catch {
    /* sem armazenamento */
  }
}

export function lerPedido<T>(id: string): T | null {
  try {
    const bruto = localStorage.getItem(`doce-pedido-${id}`);
    return bruto ? (JSON.parse(bruto) as T) : null;
  } catch {
    return null;
  }
}
