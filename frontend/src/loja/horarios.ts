// Horários de Encomenda e de Pronta entrega agendada, em hora de Brasília.

export const FUSO = { timeZone: 'America/Sao_Paulo' } as const;

// Horários de Encomenda de meia em meia hora, da abertura até antes do fechamento (00:00 é
// meia-noite), nos próximos 14 dias. Abertura e fechamento vêm da configuração da loja.
export function horarios(primeira: string, abre = '12:00', fecha = '00:00'): Date[] {
  const minutos = (hhmm: string) => {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  };
  const abertura = minutos(abre);
  const fechamento = fecha === '00:00' ? 24 * 60 : minutos(fecha);
  const lista: Date[] = [];
  let t = new Date(primeira);
  for (let i = 0; i < 14 * 48; i++) {
    const [h, m] = t
      .toLocaleTimeString('en-GB', { ...FUSO, hour: '2-digit', minute: '2-digit', hour12: false })
      .split(':')
      .map(Number);
    const agora = (h % 24) * 60 + m;
    if (agora >= abertura && agora < fechamento) lista.push(t);
    t = new Date(t.getTime() + 30 * 60 * 1000);
  }
  return lista;
}

export const diaLocal = (d: Date) => d.toLocaleDateString('en-CA', FUSO);

// Pronta entrega agendada: hoje, de meia em meia hora, do primeiro horário (agora +
// Tempo de preparo, calculado pela API) até antes do fechamento. Outros dias são Encomenda.
export function horariosDeHoje(primeiro: string | null | undefined, fecha = '00:00'): Date[] {
  if (!primeiro) return [];
  const dia = diaLocal(new Date(primeiro));
  return horarios(primeiro, '00:00', fecha).filter((d) => diaLocal(d) === dia);
}

export function rotuloHorario(d: Date): string {
  return d.toLocaleString('pt-BR', {
    ...FUSO,
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
