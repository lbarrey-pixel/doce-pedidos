import { horarios } from '../src/loja/horarios';
import { urlDaFoto } from '../src/loja/tipos';

const hora = (d: Date) =>
  d.toLocaleTimeString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    hour: '2-digit',
    minute: '2-digit',
  });

it('Encomenda de meia em meia hora, da abertura às 23h30', () => {
  const lista = horarios('2026-11-03T12:00:00-03:00');
  expect(lista.slice(0, 3).map(hora)).toEqual(['12:00', '12:30', '13:00']);
  expect(hora(lista[23])).toBe('23:30');
  expect(hora(lista[24])).toBe('12:00'); // pula a madrugada
});

it('respeita a abertura configurada', () => {
  const lista = horarios('2026-11-03T11:30:00-03:00', '11:30');
  expect(hora(lista[0])).toBe('11:30');
  expect(lista.map(hora)).not.toContain('11:00');
});

it('URL absoluta da foto vale como veio; caminho relativo vira WebP do site', () => {
  expect(urlDaFoto('https://cdn.example.com/fotos/a.png')).toBe(
    'https://cdn.example.com/fotos/a.png',
  );
  expect(urlDaFoto('fotos/doce.jpg')).toBe('/fotos/doce.webp');
  expect(urlDaFoto('')).toBeNull();
});

it('para antes do fechamento editado', () => {
  const lista = horarios('2026-11-03T11:00:00-03:00', '11:00', '20:00');
  expect(hora(lista[0])).toBe('11:00');
  expect(lista.map(hora)).toContain('19:30');
  expect(lista.map(hora)).not.toContain('20:00');
});
