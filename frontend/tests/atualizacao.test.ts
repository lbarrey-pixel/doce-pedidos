import { podeRecarregar } from '../src/comum/atualizacao';

it('versão nova recarrega o painel e o cardápio, nunca no meio do pedido', () => {
  expect(podeRecarregar('/painel/pedidos')).toBe(true);
  expect(podeRecarregar('/painel')).toBe(true);
  expect(podeRecarregar('/')).toBe(true);
  expect(podeRecarregar('/carrinho')).toBe(false);
  expect(podeRecarregar('/pedido/abc-123')).toBe(false);
  expect(podeRecarregar('/painel/criar-senha')).toBe(false);
});
