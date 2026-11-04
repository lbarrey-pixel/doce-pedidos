// Versão nova no ar aparece sem fechar o app.
// O service worker (autoUpdate) baixa a versão nova em segundo plano; quando ela assume, a página
// recarrega sozinha, menos onde a pessoa está no meio de algo (carrinho, pagamento, nova senha).
const NAO_RECARREGAR = ['/carrinho', '/pedido/', '/painel/criar-senha'];

export function podeRecarregar(caminho: string): boolean {
  return !NAO_RECARREGAR.some((c) => caminho === c || caminho.startsWith(c));
}

export function recarregarComVersaoNova(): void {
  const sw = typeof navigator !== 'undefined' ? navigator.serviceWorker : undefined;
  if (!sw) return;
  let pendente = false;
  let controlado = Boolean(sw.controller); // primeira visita: não há versão anterior a trocar
  const aplicar = () => {
    if (!controlado) {
      controlado = true;
      return;
    }
    if (podeRecarregar(window.location.pathname)) window.location.reload();
    else pendente = true; // recarrega na próxima troca de tela permitida
  };
  sw.addEventListener('controllerchange', aplicar);
  window.addEventListener('popstate', () => {
    if (pendente && podeRecarregar(window.location.pathname)) window.location.reload();
  });
  // Procura versão nova a cada 10 min com o app aberto (o padrão só procura ao abrir).
  window.setInterval(() => sw.getRegistration().then((r) => r?.update()), 10 * 60 * 1000);
}
