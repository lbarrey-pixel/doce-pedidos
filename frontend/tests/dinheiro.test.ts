import { formatarCentavos } from '../src/comum/dinheiro';

describe('formatarCentavos', () => {
  it('formata o total de um pedido', () => {
    expect(formatarCentavos(5380)).toBe('R$ 53,80');
  });
  it('formata centavos menores que um real', () => {
    expect(formatarCentavos(10)).toBe('R$ 0,10');
  });
  it('separa milhar', () => {
    expect(formatarCentavos(123456)).toBe('R$ 1.234,56');
  });
  it('mostra negativo com sinal (desconto)', () => {
    expect(formatarCentavos(-1058)).toBe('−R$ 10,58');
  });
  it('recusa valor que não é inteiro', () => {
    expect(() => formatarCentavos(10.5)).toThrow();
  });
});

describe('valor digitado em reais', () => {
  it.each([
    ['35', 3500],
    ['35,5', 3550],
    ['R$ 1.234,56', 123456],
    ['0,90', 90],
    ['19.90', 1990],
  ])('%s → %i centavos', async (texto, centavos) => {
    const { centavosDeTexto } = await import('../src/comum/dinheiro');
    expect(centavosDeTexto(texto)).toBe(centavos);
  });
  it.each(['', 'abc', '1,234', '-5'])('recusa %s', async (texto) => {
    const { centavosDeTexto } = await import('../src/comum/dinheiro');
    expect(centavosDeTexto(texto)).toBeNull();
  });
});
