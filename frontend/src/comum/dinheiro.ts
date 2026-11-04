// Dinheiro sempre em centavos inteiros; só a tela vira "R$ 0,00".
export function formatarCentavos(centavos: number): string {
  if (!Number.isInteger(centavos)) throw new Error(`centavos não inteiro: ${centavos}`);
  const abs = Math.abs(centavos);
  const reais = Math.floor(abs / 100)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const texto = `R$ ${reais},${String(abs % 100).padStart(2, '0')}`;
  return centavos < 0 ? `−${texto}` : texto;
}

// "35", "35,5", "R$ 1.234,56", "19.90" → centavos; null se não for um valor de dinheiro.
export function centavosDeTexto(texto: string): number | null {
  const limpo = texto.replace(/R\$\s?/, '').trim();
  const m =
    limpo.match(/^(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?$/) ?? limpo.match(/^(\d+)\.(\d{1,2})$/);
  if (!m) return null;
  const reais = Number(m[1].replace(/\./g, ''));
  const centavos = Number((m[2] ?? '0').padEnd(2, '0'));
  return reais * 100 + centavos;
}
